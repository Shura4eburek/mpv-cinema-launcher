"""Поиск id IMDb по названию, году и типу через открытый сервис подсказок IMDb (research.md R1).

id принимается только при однозначном совпадении: ошибочная склейка двух тайтлов хуже, чем запасной ключ.
"""

from __future__ import annotations

from urllib.parse import quote

import requests

from .watchlist import normalize_name

SUGGEST_URL = "https://v3.sg.media-imdb.com/suggestion/x/{query}.json"
_KINDS = {
    "movie": "film",
    "tvMovie": "film",
    "tvSeries": "series",
    "tvMiniSeries": "series",
}


class Unavailable(Exception):
    """Сервис не ответил или ответил не так, как ожидалось."""


def _matches(item, name: str, year: str | None, kind: str) -> bool:
    if not isinstance(item, dict) or not str(item.get("id", "")).startswith("tt"):
        return False
    if _KINDS.get(item.get("qid")) != kind:
        return False
    if normalize_name(str(item.get("l") or "")) != name:
        return False
    if year is None:
        return True
    found = item.get("y")
    if not isinstance(found, int):
        return False
    # У сериалов год начала показа на сайтах часто расходится на год.
    return abs(found - int(year)) <= (1 if kind == "series" else 0)


def pick(payload, title: str, year: str | None, kind: str) -> str | None:
    """id единственного подходящего кандидата из ответа сервиса."""
    items = payload.get("d") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise Unavailable("неожиданный ответ")
    name = normalize_name(title)
    ids = {item["id"] for item in items if _matches(item, name, year, kind)}
    return ids.pop() if len(ids) == 1 else None


def find_id(title: str, year: str | None, kind: str, timeout: float = 5) -> str | None:
    """id IMDb (``tt…``) или ``None``, если однозначного совпадения нет. Unavailable при сбое сети."""
    query = normalize_name(title)
    if not query:
        return None
    try:
        response = requests.get(SUGGEST_URL.format(query=quote(query)), timeout=timeout)
    except requests.RequestException as exc:
        raise Unavailable(type(exc).__name__) from exc
    if not response.ok:
        raise Unavailable(f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise Unavailable("ответ не JSON") from exc
    return pick(payload, title, year, kind)
