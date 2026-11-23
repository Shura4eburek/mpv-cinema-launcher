"""Валидация ссылки на поток."""

from __future__ import annotations

from urllib.parse import urlparse


def validate(url: str | None) -> bool:
    """True, если это http(s)-URL с непустым host."""
    if not url:
        return False
    candidate = url.strip()
    if not candidate:
        return False
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def looks_like_hls(url: str) -> bool:
    """Эвристика: ссылка похожа на HLS (встречается .m3u8 или hls)."""
    lowered = url.lower()
    return ".m3u8" in lowered or "hls" in lowered
