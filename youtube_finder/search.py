"""Search YouTube channels and fetch their public metadata."""

from __future__ import annotations

from typing import Iterable, Iterator

from googleapiclient.discovery import build

from .models import ChannelInfo


class ChannelSearcher:
    """Thin wrapper over the YouTube Data API v3 for channel discovery."""

    SEARCH_PAGE_SIZE = 50
    DETAIL_BATCH_SIZE = 50

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("YouTube Data API key is required")
        self._client = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def search_channel_ids(
        self,
        query: str,
        *,
        max_results: int = 50,
        region_code: str | None = None,
        relevance_language: str | None = None,
    ) -> Iterator[str]:
        """Yield channel IDs matching ``query`` until ``max_results`` are returned."""
        remaining = max_results
        page_token: str | None = None
        while remaining > 0:
            request = self._client.search().list(
                q=query,
                part="snippet",
                type="channel",
                maxResults=min(self.SEARCH_PAGE_SIZE, remaining),
                pageToken=page_token,
                regionCode=region_code,
                relevanceLanguage=relevance_language,
            )
            response = request.execute()
            for item in response.get("items", []):
                channel_id = item["snippet"].get("channelId") or item["id"].get("channelId")
                if channel_id:
                    yield channel_id
                    remaining -= 1
                    if remaining <= 0:
                        return
            page_token = response.get("nextPageToken")
            if not page_token:
                return

    def fetch_channels(self, channel_ids: Iterable[str]) -> list[ChannelInfo]:
        """Fetch full metadata for the supplied channel IDs."""
        ids = [c for c in dict.fromkeys(channel_ids) if c]
        results: list[ChannelInfo] = []
        for start in range(0, len(ids), self.DETAIL_BATCH_SIZE):
            chunk = ids[start : start + self.DETAIL_BATCH_SIZE]
            response = self._client.channels().list(
                id=",".join(chunk),
                part="snippet,statistics,brandingSettings,contentDetails",
                maxResults=self.DETAIL_BATCH_SIZE,
            ).execute()
            for item in response.get("items", []):
                results.append(_parse_channel(item))
        return results

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        region_code: str | None = None,
        relevance_language: str | None = None,
    ) -> list[ChannelInfo]:
        ids = list(
            self.search_channel_ids(
                query,
                max_results=max_results,
                region_code=region_code,
                relevance_language=relevance_language,
            )
        )
        return self.fetch_channels(ids)

    def recent_video_descriptions(self, channel: ChannelInfo, limit: int = 5) -> list[str]:
        """Return descriptions of the channel's most recent uploads (best-effort)."""
        if not channel.uploads_playlist:
            return []
        response = self._client.playlistItems().list(
            playlistId=channel.uploads_playlist,
            part="snippet",
            maxResults=min(limit, 50),
        ).execute()
        descriptions: list[str] = []
        for item in response.get("items", []):
            description = item.get("snippet", {}).get("description") or ""
            if description:
                descriptions.append(description)
        return descriptions


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_channel(item: dict) -> ChannelInfo:
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    branding = item.get("brandingSettings", {}).get("channel", {})
    content = item.get("contentDetails", {}).get("relatedPlaylists", {})
    thumbnails = snippet.get("thumbnails", {}) or {}
    thumb = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default") or {}

    return ChannelInfo(
        channel_id=item["id"],
        title=snippet.get("title", ""),
        description=snippet.get("description", "") or branding.get("description", ""),
        custom_url=snippet.get("customUrl"),
        country=snippet.get("country") or branding.get("country"),
        published_at=snippet.get("publishedAt", ""),
        subscriber_count=_to_int(statistics.get("subscriberCount")),
        view_count=_to_int(statistics.get("viewCount")),
        video_count=_to_int(statistics.get("videoCount")),
        uploads_playlist=content.get("uploads"),
        keywords=branding.get("keywords"),
        thumbnail_url=thumb.get("url"),
        raw=item,
    )
