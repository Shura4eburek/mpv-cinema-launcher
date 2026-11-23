"""Поиск трейлера фильма на YouTube: без ключа, по странице результатов."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

import requests

from .sources import clean_title

_SEARCH_URL = "https://www.youtube.com/results?search_query="
_MAX_VIDEOS = 5
_TIMEOUT_SECONDS = 10

_VIDEO = re.compile(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"')
_TRAILER_WORD = re.compile(r"трейлер|тизер|trailer|teaser", re.I)
# Такие ролики показывают чужое видео поверх трейлера или рассказывают о нём.
_NOT_TRAILER = re.compile(r"реакци|\breaction|обзор|разбор|\breview", re.I)
_YEAR = re.compile(r"\((\d{4})\)")


class TrailerUnavailable(Exception):
    """YouTube не ответил или ответил ошибкой."""


def _film_name(title: str) -> str:
    # У HDRezka название идёт как «Довод / Тенет»: второе название только мешает поиску.
    return clean_title(title).split(" / ")[0]


def search_url(title: str, year: str | None) -> str:
    year = year or next(iter(_YEAR.findall(title)), None)
    name = _film_name(title)
    return _SEARCH_URL + quote_plus(" ".join(filter(None, [name, year, "трейлер"])))


def _is_trailer(video_title: str, name: str) -> bool:
    if not _TRAILER_WORD.search(video_title):
        return False
    # Название фильма не считается: «Цепная реакция - трейлер» не реакция на трейлер.
    rest = video_title.lower().replace(name.lower(), " ") if name else video_title
    return not _NOT_TRAILER.search(rest)


def parse_videos(html: str, name: str = "") -> list[dict]:
    found: dict[str, str] = {}
    for video_id, raw_title in _VIDEO.findall(html):
        try:
            found.setdefault(video_id, json.loads(f'"{raw_title}"'))
        except ValueError:
            continue
    # Лучше честно сообщить, что трейлера нет, чем запустить со звуком постороннее видео.
    usable = [(video_id, title) for video_id, title in found.items() if _is_trailer(title, name)]
    # Сортировка устойчива: внутри групп сохраняется порядок YouTube.
    if name:
        usable.sort(key=lambda item: name.lower() not in item[1].lower())
    return [{"id": video_id, "title": title} for video_id, title in usable[:_MAX_VIDEOS]]


def find(title: str, year: str | None) -> list[dict]:
    try:
        response = requests.get(search_url(title, year), headers={"Accept-Language": "ru"}, timeout=_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise TrailerUnavailable(type(exc).__name__) from exc
    if response.status_code != 200:
        raise TrailerUnavailable(f"HTTP {response.status_code}")
    response.encoding = "utf-8"
    # Страница согласия или проверки: поиск не выполнен, и это не значит, что трейлера нет.
    if "ytInitialData" not in response.text:
        raise TrailerUnavailable("нет данных поиска")
    return parse_videos(response.text, _film_name(title))
