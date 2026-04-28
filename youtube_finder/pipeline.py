"""End-to-end pipeline: search → filter → extract contacts."""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from .contact import ContactInfo, extract_contacts
from .criteria import ChannelCriteria
from .models import ChannelInfo

if TYPE_CHECKING:
    from .search import ChannelSearcher


@dataclass
class ChannelMatch:
    channel: ChannelInfo
    contact: ContactInfo
    failed_checks: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failed_checks


def find_channels(
    queries: list[str],
    criteria: ChannelCriteria,
    *,
    searcher: "ChannelSearcher",
    max_results_per_query: int = 50,
    region_code: str | None = None,
    relevance_language: str | None = None,
    fetch_recent_videos: bool = False,
    require_contact: bool = False,
) -> list[ChannelMatch]:
    """Run the full discovery pipeline for the supplied queries.

    ``fetch_recent_videos`` makes one extra API call per matched channel to pull
    in recent video descriptions when the channel description has no contact
    info. ``require_contact`` drops matches that yield zero contact channels.
    """
    seen: set[str] = set()
    channels: list[ChannelInfo] = []
    for query in queries:
        for channel in searcher.search(
            query,
            max_results=max_results_per_query,
            region_code=region_code,
            relevance_language=relevance_language,
        ):
            if channel.channel_id in seen:
                continue
            seen.add(channel.channel_id)
            channels.append(channel)

    matches: list[ChannelMatch] = []
    for channel in channels:
        ok, reasons = criteria.matches(channel)
        if not ok:
            continue

        contact = extract_contacts(channel)
        if fetch_recent_videos and not contact.has_any:
            try:
                extra_texts = searcher.recent_video_descriptions(channel)
            except Exception:
                extra_texts = []
            contact = extract_contacts(channel, extra_texts=extra_texts)

        if require_contact and not contact.has_any:
            continue

        matches.append(ChannelMatch(channel=channel, contact=contact, failed_checks=reasons))

    return matches
