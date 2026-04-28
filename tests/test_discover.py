from youtube_finder.discover import discover_channels
from youtube_finder.llm import IntentPlan, JudgeVerdict
from youtube_finder.models import ChannelInfo


def make(channel_id: str, **overrides) -> ChannelInfo:
    base = dict(
        channel_id=channel_id,
        title=f"Channel {channel_id}",
        description=f"Cooking channel {channel_id}, contact: {channel_id.lower()}@mail.com",
        custom_url=f"@{channel_id.lower()}",
        country="US",
        published_at="2020-01-01T00:00:00Z",
        subscriber_count=80_000,
        view_count=2_000_000,
        video_count=120,
        uploads_playlist=None,
        keywords=None,
        thumbnail_url=None,
    )
    base.update(overrides)
    return ChannelInfo(**base)


class FakeSearcher:
    def __init__(self):
        self.search_results: dict[str, list[ChannelInfo]] = {}
        self.seed: ChannelInfo | None = None

    def resolve_channel(self, url: str):
        return self.seed

    def search(self, query, *, max_results, region_code=None, relevance_language=None):
        return list(self.search_results.get(query, []))

    def recent_video_descriptions(self, channel, limit=5):
        return []


def make_fake_anthropic(plan: IntentPlan, verdicts: dict[str, JudgeVerdict]):
    """Stub the calls the discover pipeline makes to the real Claude client."""

    def parse_intent_stub(description, seed, *, client):
        return plan

    def judge_channel_stub(candidate, plan_arg, *, description, client, seed=None):
        return verdicts.get(
            candidate.channel_id,
            JudgeVerdict(matches=False, score=0, reason="no verdict configured"),
        )

    return parse_intent_stub, judge_channel_stub


def test_discover_returns_only_matches_above_threshold(monkeypatch):
    seed = make("SEED", title="Seed Channel")
    fake = FakeSearcher()
    fake.seed = seed
    fake.search_results = {
        "vegan recipes": [make("AAA"), make("BBB")],
        "plant based cooking": [make("CCC", subscriber_count=500)],
    }

    plan = IntentPlan(
        search_queries=["vegan recipes", "plant based cooking"],
        judge_criteria="vegan cooking, US-based",
        min_subscribers=10_000,
        countries=["US"],
    )
    verdicts = {
        "AAA": JudgeVerdict(matches=True, score=9, reason="strong fit"),
        "BBB": JudgeVerdict(matches=True, score=5, reason="weak fit"),
    }
    parse_stub, judge_stub = make_fake_anthropic(plan, verdicts)
    monkeypatch.setattr("youtube_finder.discover.parse_intent", parse_stub)
    monkeypatch.setattr("youtube_finder.discover.judge_channel", judge_stub)

    result = discover_channels(
        "https://youtube.com/@seed",
        "Find vegan cooking channels in the US, mid-size.",
        searcher=fake,
        anthropic_client=object(),
        min_score=7,
        fetch_recent_videos=False,
    )

    assert result.seed is seed
    assert [m.channel.channel_id for m in result.matches] == ["AAA"]
    rejected_ids = {m.channel.channel_id for m in result.rejected}
    # CCC dropped by hard subscriber filter, never reaches the judge.
    assert "BBB" in rejected_ids
    assert "CCC" not in rejected_ids
    # AAA's contact was extracted from its description.
    assert result.matches[0].contact.emails == ["aaa@mail.com"]


def test_discover_skips_seed_channel(monkeypatch):
    seed = make("SEED")
    fake = FakeSearcher()
    fake.seed = seed
    # The seed pops up in the search results — pipeline must skip it.
    fake.search_results = {"vegan": [seed, make("OTHER")]}

    plan = IntentPlan(search_queries=["vegan"], judge_criteria="vegan")
    verdicts = {"OTHER": JudgeVerdict(matches=True, score=8, reason="good")}
    parse_stub, judge_stub = make_fake_anthropic(plan, verdicts)
    monkeypatch.setattr("youtube_finder.discover.parse_intent", parse_stub)
    monkeypatch.setattr("youtube_finder.discover.judge_channel", judge_stub)

    result = discover_channels(
        "@seed",
        "vegan",
        searcher=fake,
        anthropic_client=object(),
        fetch_recent_videos=False,
    )

    ids = [m.channel.channel_id for m in result.matches]
    assert "SEED" not in ids
    assert ids == ["OTHER"]


def test_discover_works_without_seed(monkeypatch):
    fake = FakeSearcher()
    fake.search_results = {"q1": [make("X")]}

    plan = IntentPlan(search_queries=["q1"], judge_criteria="anything")
    parse_stub, judge_stub = make_fake_anthropic(
        plan,
        {"X": JudgeVerdict(matches=True, score=10, reason="perfect")},
    )
    monkeypatch.setattr("youtube_finder.discover.parse_intent", parse_stub)
    monkeypatch.setattr("youtube_finder.discover.judge_channel", judge_stub)

    result = discover_channels(
        None,
        "anything",
        searcher=fake,
        anthropic_client=object(),
        fetch_recent_videos=False,
    )
    assert result.seed is None
    assert [m.channel.channel_id for m in result.matches] == ["X"]
