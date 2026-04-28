from youtube_finder.contact import _classify_url, _find_emails, extract_contacts
from youtube_finder.models import ChannelInfo


def make_channel(description: str = "", *, links=None, keywords: str = "") -> ChannelInfo:
    raw = {"brandingSettings": {"channel": {"links": links or []}}}
    return ChannelInfo(
        channel_id="UCabc",
        title="Test",
        description=description,
        custom_url="@test",
        country="US",
        published_at="2020-01-01T00:00:00Z",
        subscriber_count=1,
        view_count=1,
        video_count=1,
        uploads_playlist=None,
        keywords=keywords,
        thumbnail_url=None,
        raw=raw,
    )


def test_finds_plain_email():
    assert _find_emails("Contact me at hello@brand.io for collabs.") == ["hello@brand.io"]


def test_finds_obfuscated_email():
    text = "Business: hello [at] brand [dot] com"
    assert "hello@brand.com" in _find_emails(text)


def test_ignores_email_like_noise():
    # 'v2.5@stable' and version strings should not register.
    assert _find_emails("python v3.11.5") == []


def test_classify_socials():
    assert _classify_url("https://www.instagram.com/foo")[0] == "instagram"
    assert _classify_url("https://x.com/bar")[0] == "twitter"
    assert _classify_url("https://discord.gg/baz")[0] == "discord"
    assert _classify_url("https://youtube.com/@thing")[0] == "youtube"
    assert _classify_url("https://example.com/landing")[0] == "website"


def test_extract_contacts_full():
    description = (
        "Subscribe! Business inquiries: biz@studio.tv\n"
        "IG: https://instagram.com/studio\n"
        "Site: https://studio.tv"
    )
    branding_links = [
        {"url": "https://twitter.com/studio"},
        {"url": "https://discord.gg/abc"},
    ]
    channel = make_channel(description=description, links=branding_links)
    contact = extract_contacts(channel)

    assert contact.emails == ["biz@studio.tv"]
    assert "instagram" in contact.socials
    assert "twitter" in contact.socials
    assert "discord" in contact.socials
    assert any("studio.tv" in w for w in contact.websites)
    assert contact.has_any


def test_extract_contacts_with_extra_texts():
    channel = make_channel(description="No contact here.")
    contact = extract_contacts(
        channel,
        extra_texts=["Sponsorships: collabs@later.co"],
    )
    assert contact.emails == ["collabs@later.co"]


def test_no_contact_returns_empty():
    contact = extract_contacts(make_channel(description="just words"))
    assert not contact.has_any
