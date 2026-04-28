"""Claude API helpers: parse a natural-language brief into a search plan, then
score candidate channels against it.

Uses ``claude-opus-4-7`` with adaptive thinking and JSON-schema structured
outputs so the responses are guaranteed-parseable. The judge's system prompt is
cached because it stays identical across many candidate evaluations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .models import ChannelInfo

if TYPE_CHECKING:
    import anthropic

MODEL = "claude-opus-4-7"

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "search_queries": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "3-6 short YouTube search queries that would surface channels "
                "matching the user's brief. Mix English with the channel's "
                "likely native language when relevant."
            ),
        },
        "min_subscribers": {"type": "integer", "minimum": 0},
        "max_subscribers": {"type": "integer", "minimum": 0},
        "countries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ISO country codes (e.g. US, KR) if the user specified a region.",
        },
        "language": {"type": "string", "description": "ISO 639-1 language code if specified."},
        "must_have": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Aspects the channel MUST have (free-form bullets).",
        },
        "must_not_have": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Aspects the channel MUST NOT have.",
        },
        "judge_criteria": {
            "type": "string",
            "description": (
                "A 2-4 sentence rubric used to judge whether an individual "
                "candidate channel fits the brief."
            ),
        },
    },
    "required": [
        "search_queries",
        "countries",
        "must_have",
        "must_not_have",
        "judge_criteria",
    ],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {"type": "boolean"},
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
            "description": "How well the channel fits the brief (0=not at all, 10=perfect).",
        },
        "reason": {"type": "string", "description": "One-sentence justification."},
    },
    "required": ["matches", "score", "reason"],
    "additionalProperties": False,
}


@dataclass
class IntentPlan:
    search_queries: list[str]
    judge_criteria: str
    min_subscribers: int | None = None
    max_subscribers: int | None = None
    countries: list[str] = field(default_factory=list)
    language: str | None = None
    must_have: list[str] = field(default_factory=list)
    must_not_have: list[str] = field(default_factory=list)


@dataclass
class JudgeVerdict:
    matches: bool
    score: int
    reason: str


def _seed_summary(seed: ChannelInfo | None) -> str:
    if seed is None:
        return "(no seed channel provided)"
    description = (seed.description or "").strip()[:600]
    return (
        f"- Title: {seed.title}\n"
        f"- Country: {seed.country or 'unknown'}\n"
        f"- Subscribers: {seed.subscriber_count:,}\n"
        f"- Videos: {seed.video_count:,}\n"
        f"- Description: {description or '(empty)'}\n"
        f"- Keywords: {seed.keywords or '(none)'}"
    )


def _candidate_summary(candidate: ChannelInfo) -> str:
    description = (candidate.description or "").strip()[:800]
    return (
        f"Channel title: {candidate.title}\n"
        f"Handle: {candidate.custom_url or '(none)'}\n"
        f"Country: {candidate.country or 'unknown'}\n"
        f"Subscribers: {candidate.subscriber_count:,}  "
        f"Views: {candidate.view_count:,}  Videos: {candidate.video_count:,}\n"
        f"Description:\n{description or '(empty)'}\n"
        f"Keywords: {candidate.keywords or '(none)'}"
    )


def parse_intent(
    description: str,
    seed: ChannelInfo | None,
    *,
    client: "anthropic.Anthropic",
) -> IntentPlan:
    """Translate the user's free-text brief into a structured search plan."""
    user_msg = (
        "The user wants to find YouTube channels matching this brief:\n"
        f"<<<\n{description.strip()}\n>>>\n\n"
        "Reference (seed) channel they pointed at as a similar example:\n"
        f"{_seed_summary(seed)}\n\n"
        "Output a JSON search plan that another system will use to (1) run "
        "YouTube searches and (2) judge each candidate channel one by one. "
        "Be conservative with hard filters - only set min/max subscribers or "
        "country codes when the user explicitly asked for them."
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": INTENT_SCHEMA}},
        messages=[{"role": "user", "content": user_msg}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return IntentPlan(
        search_queries=data["search_queries"],
        judge_criteria=data["judge_criteria"],
        min_subscribers=data.get("min_subscribers"),
        max_subscribers=data.get("max_subscribers"),
        countries=data.get("countries", []),
        language=data.get("language"),
        must_have=data.get("must_have", []),
        must_not_have=data.get("must_not_have", []),
    )


def _judge_system(plan: IntentPlan, description: str, seed: ChannelInfo | None) -> str:
    must_have = "\n".join(f"  - {x}" for x in plan.must_have) or "  (none)"
    must_not = "\n".join(f"  - {x}" for x in plan.must_not_have) or "  (none)"
    return (
        "You decide whether a candidate YouTube channel matches a user's brief.\n"
        "Be strict: only set `matches: true` when the candidate clearly fits.\n\n"
        f"User brief:\n<<<\n{description.strip()}\n>>>\n\n"
        f"Reference channel they like:\n{_seed_summary(seed)}\n\n"
        f"Judging rubric:\n{plan.judge_criteria}\n\n"
        f"Must have:\n{must_have}\n\n"
        f"Must NOT have:\n{must_not}\n\n"
        "Score 0-10. 7+ usually means matches=true. Justify in one sentence."
    )


def judge_channel(
    candidate: ChannelInfo,
    plan: IntentPlan,
    *,
    description: str,
    client: "anthropic.Anthropic",
    seed: ChannelInfo | None = None,
) -> JudgeVerdict:
    """Use Claude to score a single candidate against the user's brief."""
    system = _judge_system(plan, description, seed)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        messages=[{"role": "user", "content": _candidate_summary(candidate)}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return JudgeVerdict(matches=data["matches"], score=data["score"], reason=data["reason"])
