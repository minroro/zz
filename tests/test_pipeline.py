from youtube_finder.criteria import ChannelCriteria
from youtube_finder.models import ChannelInfo
from youtube_finder.pipeline import find_channels


class FakeSearcher:
    def __init__(self, channels: list[ChannelInfo]):
        self._by_query = {"cooking": channels}
        self.recent_calls = 0

    def search(self, query, *, max_results, region_code=None, relevance_language=None):
        return list(self._by_query.get(query, []))

    def recent_video_descriptions(self, channel, limit=5):
        self.recent_calls += 1
        return ["Sponsorships: hello@brand.tv"]


def make(channel_id: str, **overrides) -> ChannelInfo:
    base = dict(
        channel_id=channel_id,
        title="Channel " + channel_id,
        description="",
        custom_url=None,
        country="US",
        published_at="2020-01-01T00:00:00Z",
        subscriber_count=50_000,
        view_count=1_000_000,
        video_count=100,
        uploads_playlist="UU" + channel_id,
        keywords=None,
        thumbnail_url=None,
    )
    base.update(overrides)
    return ChannelInfo(**base)


def test_pipeline_filters_and_extracts():
    channels = [
        make("A", description="Reach me at hello@a.tv"),
        make("B", subscriber_count=100, description="too small"),
        make("C", description=""),
    ]
    fake = FakeSearcher(channels)

    matches = find_channels(
        ["cooking"],
        ChannelCriteria(min_subscribers=10_000),
        searcher=fake,
        fetch_recent_videos=True,
    )

    by_id = {m.channel.channel_id: m for m in matches}
    assert set(by_id) == {"A", "C"}
    assert by_id["A"].contact.emails == ["hello@a.tv"]
    # C had empty description, so the recent-video fallback kicked in.
    assert by_id["C"].contact.emails == ["hello@brand.tv"]
    assert fake.recent_calls == 1


def test_pipeline_dedupes_across_queries():
    channels = [make("A")]
    fake = FakeSearcher(channels)
    fake._by_query = {"q1": channels, "q2": channels}

    matches = find_channels(
        ["q1", "q2"],
        ChannelCriteria(),
        searcher=fake,
    )
    assert len(matches) == 1


def test_require_contact_drops_empty():
    channels = [make("A", description="no contacts here")]
    fake = FakeSearcher(channels)
    fake._by_query = {"q": channels}

    matches = find_channels(
        ["q"],
        ChannelCriteria(),
        searcher=fake,
        require_contact=True,
        fetch_recent_videos=False,
    )
    assert matches == []
