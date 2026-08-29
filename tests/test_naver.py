import json

import pytest

from youtube_finder.naver import NaverApiError, NaverSearcher, _clean


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self._responses.pop(0)


def _item(n):
    return {
        "title": f"<b>결과</b> {n}",
        "link": f"https://example.com/{n}",
        "description": f"설명 &amp; {n}",
    }


def test_clean_strips_highlight_tags_and_entities():
    assert _clean("<b>네이버</b> 검색 &amp; 테스트") == "네이버 검색 & 테스트"


def test_requires_credentials():
    with pytest.raises(ValueError):
        NaverSearcher("", "")


def test_search_parses_items():
    session = FakeSession([FakeResponse({"items": [_item(1), _item(2)]})])
    searcher = NaverSearcher("id", "secret", session=session)
    results = searcher.search("테스트", search_type="blog", max_results=5)

    assert [r.title for r in results] == ["결과 1", "결과 2"]
    assert results[0].link == "https://example.com/1"
    assert results[0].description == "설명 & 1"

    url, params = session.calls[0]
    assert url.endswith("/blog.json")
    assert params == {"query": "테스트", "display": 5, "start": 1}
    assert session.headers["X-Naver-Client-Id"] == "id"
    assert session.headers["X-Naver-Client-Secret"] == "secret"


def test_search_paginates_until_max_results():
    first_page = {"items": [_item(n) for n in range(1, 101)]}
    second_page = {"items": [_item(n) for n in range(101, 121)]}
    session = FakeSession([FakeResponse(first_page), FakeResponse(second_page)])
    searcher = NaverSearcher("id", "secret", session=session)

    results = searcher.search("테스트", max_results=110)

    assert len(results) == 110
    assert session.calls[0][1]["start"] == 1
    assert session.calls[1][1] == {"query": "테스트", "display": 10, "start": 101}


def test_search_stops_on_short_page():
    session = FakeSession([FakeResponse({"items": [_item(1)]})])
    searcher = NaverSearcher("id", "secret", session=session)
    results = searcher.search("테스트", max_results=50)
    assert len(results) == 1
    assert len(session.calls) == 1


def test_search_rejects_unknown_type():
    searcher = NaverSearcher("id", "secret", session=FakeSession([]))
    with pytest.raises(ValueError):
        searcher.search("테스트", search_type="nope")


def test_search_rejects_empty_query():
    searcher = NaverSearcher("id", "secret", session=FakeSession([]))
    with pytest.raises(ValueError):
        searcher.search("   ")


def test_api_error_raises():
    session = FakeSession([
        FakeResponse({"errorMessage": "Not Exist Client ID", "errorCode": "024"}, status_code=401)
    ])
    searcher = NaverSearcher("id", "secret", session=session)
    with pytest.raises(NaverApiError, match="401.*Not Exist Client ID"):
        searcher.search("테스트")


def test_sort_passed_through():
    session = FakeSession([FakeResponse({"items": []})])
    searcher = NaverSearcher("id", "secret", session=session)
    searcher.search("테스트", search_type="news", sort="date")
    assert session.calls[0][1]["sort"] == "date"
