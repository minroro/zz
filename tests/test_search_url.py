import pytest

from youtube_finder.search import parse_channel_url


def test_parse_bare_channel_id():
    cid = "UC" + "x" * 22
    assert parse_channel_url(cid) == ("id", cid)


def test_parse_channel_url():
    cid = "UC" + "a" * 22
    assert parse_channel_url(f"https://www.youtube.com/channel/{cid}") == ("id", cid)


def test_parse_handle_url():
    assert parse_channel_url("https://www.youtube.com/@cookingwithanna") == (
        "handle",
        "cookingwithanna",
    )


def test_parse_bare_handle():
    assert parse_channel_url("@chefkim") == ("handle", "chefkim")


def test_parse_legacy_user_url():
    assert parse_channel_url("https://www.youtube.com/user/oldschool") == (
        "username",
        "oldschool",
    )


def test_parse_custom_url():
    assert parse_channel_url("https://www.youtube.com/c/SomeChannel") == (
        "custom",
        "SomeChannel",
    )


def test_parse_lone_path_falls_back_to_handle():
    assert parse_channel_url("youtube.com/somechan") == ("handle", "somechan")


def test_parse_invalid():
    with pytest.raises(ValueError):
        parse_channel_url("https://youtube.com/")
