from datetime import datetime, timedelta, timezone

from youtube_finder.criteria import ChannelCriteria
from youtube_finder.models import ChannelInfo


def make_channel(**overrides) -> ChannelInfo:
    base = dict(
        channel_id="UC123",
        title="Cooking with Anna",
        description="Healthy recipes. Contact: anna@example.com",
        custom_url="@cookingwithanna",
        country="US",
        published_at="2020-01-01T00:00:00Z",
        subscriber_count=120_000,
        view_count=5_000_000,
        video_count=180,
        uploads_playlist="UU123",
        keywords="cooking healthy",
        thumbnail_url=None,
    )
    base.update(overrides)
    return ChannelInfo(**base)


def test_meets_all_criteria():
    criteria = ChannelCriteria(
        min_subscribers=10_000,
        max_subscribers=500_000,
        min_views=100_000,
        min_videos=10,
        countries=["US", "CA"],
        required_keywords=["cooking"],
        excluded_keywords=["politics"],
    )
    ok, reasons = criteria.matches(make_channel())
    assert ok, reasons
    assert reasons == []


def test_subscriber_bounds():
    criteria = ChannelCriteria(min_subscribers=200_000)
    ok, reasons = criteria.matches(make_channel(subscriber_count=120_000))
    assert not ok
    assert any("subscribers" in r for r in reasons)

    criteria = ChannelCriteria(max_subscribers=50_000)
    ok, reasons = criteria.matches(make_channel(subscriber_count=120_000))
    assert not ok


def test_country_filter_case_insensitive():
    criteria = ChannelCriteria(countries=["us"])
    assert criteria.matches(make_channel(country="US"))[0]
    assert not criteria.matches(make_channel(country="JP"))[0]
    assert not criteria.matches(make_channel(country=None))[0]


def test_required_and_excluded_keywords():
    criteria = ChannelCriteria(required_keywords=["healthy"])
    assert criteria.matches(make_channel())[0]
    assert not criteria.matches(make_channel(description="just snacks", keywords=""))[0]

    criteria = ChannelCriteria(excluded_keywords=["politics"])
    assert criteria.matches(make_channel())[0]
    assert not criteria.matches(make_channel(description="we love politics here"))[0]


def test_max_age_days():
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat().replace("+00:00", "Z")

    criteria = ChannelCriteria(max_age_days=30)
    assert criteria.matches(make_channel(published_at=recent))[0]
    ok, reasons = criteria.matches(make_channel(published_at=old))
    assert not ok
    assert any("age" in r for r in reasons)
