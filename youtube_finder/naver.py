"""Search Naver (blogs, news, web pages, ...) via the Naver Open API.

Requires application credentials from https://developers.naver.com
(``NAVER_CLIENT_ID`` / ``NAVER_CLIENT_SECRET``).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import requests

API_BASE = "https://openapi.naver.com/v1/search"

#: Search verticals supported by the Naver Open API search endpoints.
SEARCH_TYPES = (
    "blog",
    "news",
    "webkr",
    "cafearticle",
    "kin",
    "book",
    "encyc",
    "doc",
    "image",
    "shop",
    "local",
)

_TAG_RE = re.compile(r"</?b>", re.IGNORECASE)

# Per-request/display and start-offset caps documented by the API.
_MAX_DISPLAY = 100
_MAX_START = 1000


class NaverApiError(RuntimeError):
    """Raised when the Naver Open API returns an error response."""


def _clean(text: str) -> str:
    """Strip the API's ``<b>`` highlight tags and unescape HTML entities."""
    return html.unescape(_TAG_RE.sub("", text or ""))


@dataclass
class NaverSearchResult:
    """A single item from a Naver search response."""

    title: str
    link: str
    description: str
    raw: dict = field(default_factory=dict, repr=False)


class NaverSearcher:
    """Thin wrapper over the Naver Open API search endpoints."""

    def __init__(self, client_id: str, client_secret: str, session: requests.Session | None = None):
        if not client_id or not client_secret:
            raise ValueError(
                "Naver Open API credentials are required "
                "(set NAVER_CLIENT_ID and NAVER_CLIENT_SECRET)"
            )
        self._session = session or requests.Session()
        self._session.headers.update({
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        })

    def search(
        self,
        query: str,
        *,
        search_type: str = "webkr",
        max_results: int = 10,
        sort: str | None = None,
    ) -> list[NaverSearchResult]:
        """Return up to ``max_results`` results for ``query``.

        ``search_type`` selects the vertical (see :data:`SEARCH_TYPES`).
        ``sort`` is ``"sim"`` (relevance, default) or ``"date"`` where the
        vertical supports it.
        """
        if search_type not in SEARCH_TYPES:
            raise ValueError(
                f"unknown search type {search_type!r}; expected one of {', '.join(SEARCH_TYPES)}"
            )
        if not query.strip():
            raise ValueError("query must not be empty")

        results: list[NaverSearchResult] = []
        start = 1
        while len(results) < max_results and start <= _MAX_START:
            display = min(_MAX_DISPLAY, max_results - len(results))
            params: dict[str, str | int] = {"query": query, "display": display, "start": start}
            if sort:
                params["sort"] = sort
            payload = self._request(search_type, params)
            items = payload.get("items", [])
            for item in items:
                results.append(
                    NaverSearchResult(
                        title=_clean(item.get("title", "")),
                        link=item.get("link", ""),
                        description=_clean(item.get("description", "")),
                        raw=item,
                    )
                )
                if len(results) >= max_results:
                    return results
            if len(items) < display:
                break
            start += len(items)
        return results

    def _request(self, search_type: str, params: dict) -> dict:
        response = self._session.get(f"{API_BASE}/{search_type}.json", params=params, timeout=15)
        if response.status_code != 200:
            try:
                detail = response.json()
                message = detail.get("errorMessage") or detail.get("message") or response.text
            except ValueError:
                message = response.text
            raise NaverApiError(f"Naver API error {response.status_code}: {message}")
        return response.json()
