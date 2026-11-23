"""T006 [US1]: валидация ссылки и HLS-эвристика."""

import pytest

from mpv_launcher import url


@pytest.mark.parametrize(
    "value",
    [
        "https://cdn.example/path/hls-v1-a4.m3u8",
        "http://host/stream",
        "  https://host/x  ",  # пробелы обрезаются
    ],
)
def test_valid_urls(value):
    assert url.validate(value) is True


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "not a url", "ftp://host/x", "/local/path.m3u8", "host/x"],
)
def test_invalid_urls(value):
    assert url.validate(value) is False


def test_looks_like_hls():
    assert url.looks_like_hls("https://x/a/hls-v1.m3u8") is True
    assert url.looks_like_hls("https://x/HLS/master") is True
    assert url.looks_like_hls("https://x/video.mp4") is False
