"""High-level "find me channels like this" workflow.

Glue between :mod:`youtube_finder.search`, :mod:`youtube_finder.llm`,
:mod:`youtube_finder.criteria`, and :mod:`youtube_finder.contact`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .contact import ContactInfo, extract_contacts
from .criteria import ChannelCriteria
from .llm import IntentPlan, JudgeVerdict, judge_channel, parse_intent
from .models import ChannelInfo

if TYPE_CHECKING:
    import anthropic
    from .search import ChannelSearcher


@dataclass
class DiscoveredChannel:
    channel: ChannelInfo
    contact: ContactInfo
    verdict: JudgeVerdict


@dataclass
class DiscoveryResult:
    plan: IntentPlan
    seed: ChannelInfo | None
    matches: list[DiscoveredChannel] = field(default_factory=list)
    rejected: list[DiscoveredChannel] = field(default_factory=list)


def _to_criteria(plan: IntentPlan) -> ChannelCriteria:
    return ChannelCriteria(
        min_subscribers=plan.min_subscribers or 0,
        max_subscribers=plan.max_subscribers,
        countries=list(plan.countries),
    )


def discover_channels(
    seed_url: str | None,
    description: str,
    *,
    searcher: "ChannelSearcher",
    anthropic_client: "anthropic.Anthropic",
    max_per_query: int = 15,
    max_candidates: int = 60,
    min_score: int = 7,
    fetch_recent_videos: bool = True,
    progress=None,
) -> DiscoveryResult:
    """Find channels similar to ``seed_url`` matching ``description``.

    The pipeline is:

    1. Resolve the seed URL (optional) into a :class:`ChannelInfo`.
    2. Ask Claude to turn ``description`` + seed into a structured plan.
    3. Run each search query against YouTube, dedupe, cap to ``max_candidates``.
    4. Apply hard filters from the plan (subs range, country).
    5. Have Claude judge each remaining candidate; keep ones with
       ``score >= min_score`` or ``matches=True``.
    6. Extract contact info for accepted matches.

    ``progress`` is an optional callable ``(stage, info)`` used by the CLI to
    print status updates without polluting the library API.
    """

    def _emit(stage: str, info: object = "") -> None:
        if progress is not None:
            progress(stage, info)

    seed: ChannelInfo | None = None
    if seed_url:
        _emit("seed", seed_url)
        seed = searcher.resolve_channel(seed_url)
        if seed is None:
            raise ValueError(f"could not resolve seed channel: {seed_url!r}")
        _emit("seed_resolved", seed)

    _emit("plan_start")
    plan = parse_intent(description, seed, client=anthropic_client)
    _emit("plan", plan)

    seen: set[str] = set()
    if seed is not None:
        seen.add(seed.channel_id)

    candidates: list[ChannelInfo] = []
    for query in plan.search_queries:
        if len(candidates) >= max_candidates:
            break
        _emit("query", query)
        for channel in searcher.search(
            query,
            max_results=max_per_query,
            relevance_language=plan.language,
        ):
            if channel.channel_id in seen:
                continue
            seen.add(channel.channel_id)
            candidates.append(channel)
            if len(candidates) >= max_candidates:
                break
    _emit("candidates", candidates)

    hard = _to_criteria(plan)
    filtered: list[ChannelInfo] = []
    for channel in candidates:
        ok, _ = hard.matches(channel)
        if ok:
            filtered.append(channel)
    _emit("filtered", filtered)

    matches: list[DiscoveredChannel] = []
    rejected: list[DiscoveredChannel] = []
    for channel in filtered:
        _emit("judging", channel)
        verdict = judge_channel(
            channel,
            plan,
            description=description,
            client=anthropic_client,
            seed=seed,
        )
        contact = extract_contacts(channel)
        if fetch_recent_videos and not contact.has_any:
            try:
                extras = searcher.recent_video_descriptions(channel)
            except Exception:
                extras = []
            contact = extract_contacts(channel, extra_texts=extras)

        record = DiscoveredChannel(channel=channel, contact=contact, verdict=verdict)
        if verdict.matches and verdict.score >= min_score:
            matches.append(record)
        else:
            rejected.append(record)
        _emit("verdict", record)

    matches.sort(key=lambda r: r.verdict.score, reverse=True)
    return DiscoveryResult(plan=plan, seed=seed, matches=matches, rejected=rejected)
