"""Extract contact information from channel metadata.

The YouTube "About" page hides the business email behind a CAPTCHA, so this
module pulls everything that is publicly visible: emails embedded in the
channel description, declared external links from ``brandingSettings``, and as
a fallback the descriptions of recent uploads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlparse

from .models import ChannelInfo

EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"
)
# Many creators write "biz [at] domain dot com" to dodge scrapers.
OBFUSCATED_EMAIL_RE = re.compile(
    r"([A-Za-z0-9._%+-]+)\s*[\(\[]?\s*(?:at|@)\s*[\)\]]?\s*"
    r"([A-Za-z0-9.-]+)\s*[\(\[]?\s*(?:dot|\.)\s*[\)\]]?\s*([A-Za-z]{2,})",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)

SOCIAL_DOMAINS = {
    "instagram.com": "instagram",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "tiktok.com": "tiktok",
    "linkedin.com": "linkedin",
    "discord.gg": "discord",
    "discord.com": "discord",
    "t.me": "telegram",
    "telegram.me": "telegram",
    "twitch.tv": "twitch",
    "github.com": "github",
    "patreon.com": "patreon",
    "ko-fi.com": "kofi",
    "buymeacoffee.com": "buymeacoffee",
    "linktr.ee": "linktree",
    "beacons.ai": "beacons",
    "threads.net": "threads",
    "reddit.com": "reddit",
}


@dataclass
class ContactInfo:
    channel_id: str
    channel_url: str
    emails: list[str] = field(default_factory=list)
    socials: dict[str, list[str]] = field(default_factory=dict)
    websites: list[str] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        return bool(self.emails or self.socials or self.websites)


def _find_emails(text: str) -> list[str]:
    found = set(m.group(0).lower() for m in EMAIL_RE.finditer(text))
    for m in OBFUSCATED_EMAIL_RE.finditer(text):
        local, domain, tld = m.group(1), m.group(2), m.group(3)
        # Skip noise like "1 at 2 dot 3" by requiring a plausible TLD length.
        if 2 <= len(tld) <= 6 and "." not in local:
            found.add(f"{local}@{domain}.{tld}".lower())
    return sorted(found)


def _classify_url(url: str) -> tuple[str, str]:
    """Return ``(category, normalized_url)`` where category is a social key or 'website'."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "website", url
    host = (parsed.netloc or "").lower().lstrip("www.")
    for domain, name in SOCIAL_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return name, url.rstrip("/.,);]")
    if host.endswith("youtube.com") or host.endswith("youtu.be"):
        return "youtube", url.rstrip("/.,);]")
    return "website", url.rstrip("/.,);]")


def _branding_links(channel: ChannelInfo) -> list[str]:
    branding = channel.raw.get("brandingSettings", {}) or {}
    raw_links: Iterable[dict] = (
        branding.get("channel", {}).get("links")
        or branding.get("channel", {}).get("featuredChannelsUrls")
        or []
    )
    urls: list[str] = []
    for link in raw_links:
        if isinstance(link, dict):
            url = link.get("url") or link.get("href")
            if url:
                urls.append(url)
        elif isinstance(link, str):
            urls.append(link)
    return urls


def extract_contacts(
    channel: ChannelInfo,
    *,
    extra_texts: Iterable[str] = (),
) -> ContactInfo:
    """Collect emails, social handles, and websites for ``channel``.

    ``extra_texts`` lets callers pass additional sources such as recent video
    descriptions when the channel description itself yielded nothing.
    """
    info = ContactInfo(channel_id=channel.channel_id, channel_url=channel.url)

    text_blobs: list[str] = [channel.description or "", channel.keywords or ""]
    text_blobs.extend(t for t in extra_texts if t)
    combined_text = "\n".join(text_blobs)

    emails = _find_emails(combined_text)

    urls: list[str] = list(_branding_links(channel))
    urls.extend(URL_RE.findall(combined_text))

    seen_urls: set[str] = set()
    for url in urls:
        category, normalized = _classify_url(url)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        if category == "youtube":
            continue
        if category == "website":
            info.websites.append(normalized)
        else:
            info.socials.setdefault(category, []).append(normalized)

    info.emails = emails
    info.websites = sorted(set(info.websites))
    for key in info.socials:
        info.socials[key] = sorted(set(info.socials[key]))
    return info
