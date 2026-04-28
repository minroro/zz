"""Search YouTube channels and fetch their public metadata."""

from __future__ import annotations

import os
import re
from typing import Iterable, Iterator
from urllib.parse import urlparse

import httplib2
from googleapiclient.discovery import build

from .models import ChannelInfo


_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def parse_channel_url(url_or_id: str) -> tuple[str, str]:
    """Return ``(kind, value)`` describing how to resolve a YouTube channel reference.

    ``kind`` is one of ``"id"`` (UC... channel ID), ``"handle"`` (``@name``),
    ``"username"`` (legacy ``/user/name``), or ``"custom"`` (legacy ``/c/name``).
    Accepts bare IDs/handles too, not just full URLs.
    """
    raw = url_or_id.strip()
    if _CHANNEL_ID_RE.match(raw):
        return ("id", raw)
    if raw.startswith("@"):
        return ("handle", raw[1:])

    parsed = urlparse(raw if "://" in raw else "https://" + raw)
    parts = [p for p in (parsed.path or "").split("/") if p]
    if not parts:
        raise ValueError(f"could not parse channel reference: {url_or_id!r}")

    if parts[0] == "channel" and len(parts) >= 2 and _CHANNEL_ID_RE.match(parts[1]):
        return ("id", parts[1])
    if parts[0].startswith("@"):
        return ("handle", parts[0][1:])
    if parts[0] == "user" and len(parts) >= 2:
        return ("username", parts[1])
    if parts[0] == "c" and len(parts) >= 2:
        return ("custom", parts[1])
    if len(parts) == 1:
        # Fall-back: treat lone path segment as a handle.
        return ("handle", parts[0])
    raise ValueError(f"unrecognized YouTube channel URL: {url_or_id!r}")


class ChannelSearcher:
    """Thin wrapper over the YouTube Data API v3 for channel discovery."""

    SEARCH_PAGE_SIZE = 50
    DETAIL_BATCH_SIZE = 50

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("YouTube Data API key is required")
        # ``httplib2`` ships its own CA bundle and ignores ``SSL_CERT_FILE``.
        # Honor the standard env var so corporate / sandbox proxies with custom
        # roots can be trusted.
        ca_bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        http = httplib2.Http(ca_certs=ca_bundle) if ca_bundle else None
        self._client = build(
            "youtube",
            "v3",
            developerKey=api_key,
            http=http,
            cache_discovery=False,
        )

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

    def resolve_channel(self, url_or_id: str) -> ChannelInfo | None:
        """Resolve a channel URL/handle/ID into a :class:`ChannelInfo` object."""
        kind, value = parse_channel_url(url_or_id)
        params: dict[str, str] = {
            "part": "snippet,statistics,brandingSettings,contentDetails",
            "maxResults": "1",
        }
        if kind == "id":
            params["id"] = value
        elif kind == "handle":
            params["forHandle"] = "@" + value
        elif kind == "username":
            params["forUsername"] = value
        else:
            # /c/<custom> URLs aren't directly addressable via channels.list,
            # so fall back to a search-by-name lookup and pick the top hit.
            for cid in self.search_channel_ids(value, max_results=1):
                results = self.fetch_channels([cid])
                return results[0] if results else None
            return None

        response = self._client.channels().list(**params).execute()
        items = response.get("items", [])
        if not items:
            return None
        return _parse_channel(items[0])

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
