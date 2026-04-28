"""Filter YouTube channels against user-defined criteria."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import ChannelInfo


@dataclass
class ChannelCriteria:
    min_subscribers: int = 0
    max_subscribers: int | None = None
    min_views: int = 0
    min_videos: int = 0
    countries: list[str] = field(default_factory=list)
    required_keywords: list[str] = field(default_factory=list)
    excluded_keywords: list[str] = field(default_factory=list)
    max_age_days: int | None = None

    def matches(self, channel: ChannelInfo) -> tuple[bool, list[str]]:
        """Return ``(ok, reasons)`` where ``reasons`` lists the failed checks."""
        reasons: list[str] = []

        if channel.subscriber_count < self.min_subscribers:
            reasons.append(
                f"subscribers {channel.subscriber_count} < min {self.min_subscribers}"
            )
        if self.max_subscribers is not None and channel.subscriber_count > self.max_subscribers:
            reasons.append(
                f"subscribers {channel.subscriber_count} > max {self.max_subscribers}"
            )
        if channel.view_count < self.min_views:
            reasons.append(f"views {channel.view_count} < min {self.min_views}")
        if channel.video_count < self.min_videos:
            reasons.append(f"videos {channel.video_count} < min {self.min_videos}")

        if self.countries:
            wanted = {c.upper() for c in self.countries}
            country = (channel.country or "").upper()
            if country not in wanted:
                reasons.append(f"country '{country or 'unknown'}' not in {sorted(wanted)}")

        haystack = " ".join(
            filter(
                None,
                [channel.title, channel.description, channel.keywords or ""],
            )
        ).lower()

        for keyword in self.required_keywords:
            if keyword.lower() not in haystack:
                reasons.append(f"missing required keyword '{keyword}'")
        for keyword in self.excluded_keywords:
            if keyword.lower() in haystack:
                reasons.append(f"contains excluded keyword '{keyword}'")

        if self.max_age_days is not None and channel.published_at:
            try:
                created = datetime.fromisoformat(channel.published_at.replace("Z", "+00:00"))
            except ValueError:
                created = None
            if created is not None:
                age_days = (datetime.now(timezone.utc) - created).days
                if age_days > self.max_age_days:
                    reasons.append(f"channel age {age_days}d > {self.max_age_days}d")

        return (not reasons, reasons)
