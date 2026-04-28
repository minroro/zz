"""Plain data containers shared across modules (no third-party imports)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChannelInfo:
    channel_id: str
    title: str
    description: str
    custom_url: str | None
    country: str | None
    published_at: str
    subscriber_count: int
    view_count: int
    video_count: int
    uploads_playlist: str | None
    keywords: str | None
    thumbnail_url: str | None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def url(self) -> str:
        if self.custom_url:
            handle = self.custom_url.lstrip("@")
            return f"https://www.youtube.com/@{handle}"
        return f"https://www.youtube.com/channel/{self.channel_id}"
