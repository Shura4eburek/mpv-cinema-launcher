"""Запросы к локальному серверу Lampac и разбор его ответов."""

from __future__ import annotations

import re
import sys
import time
import zlib
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from .sources import clean_title

_REQUEST_TIMEOUT_SECONDS = 20
_SEARCH_LIMIT_SECONDS = 40
_POLL_TIMEOUT_SECONDS = 10
_WORKERS = 6
_POLL_PAUSE_SECONDS = 0.25
_AUTO_QUALITY = "Авто"
# Заглушка правообладателя вместо фильма.
_BLOCKED = re.compile(r"/abuse[_.-]", re.I)
# «Проект Лазарь (1-2 сезон)»: пометка сайта, а не часть названия.
_SEASONS_NOTE = re.compile(r"\s*\([^)]*сезон[^)]*\)", re.I)


class Unavailable(Exception):
    """Сервер не ответил."""


def stable_id(title: str, year: str | None, serial: bool = False) -> int:
    """Lampac кеширует по номеру: с одним номером все фильмы получили бы один и тот же список."""
    return zlib.crc32(f"{title}|{year}|{serial}".encode("utf-8")) % 900_000_000 + 100_000_000


def _as_json_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "rjson"]
    return urlunsplit(parts._replace(query=urlencode([*query, ("rjson", "true")])))


def _get_json(url: str, params: dict | None = None, timeout: float = _REQUEST_TIMEOUT_SECONDS):
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise Unavailable(type(exc).__name__) from exc
    if not response.ok:
        raise Unavailable(f"HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise Unavailable("ответ не JSON") from exc


def _name_only(label: str) -> str:
    """«VeoVeo ~ 1080p» — заявленное качество: настоящее видно по вариантам."""
    return re.split(r"\s+[~-]\s+", label, maxsplit=1)[0].strip()


def _qualities(entry: dict) -> list[dict]:
    listed = entry.get("quality")
    if isinstance(listed, dict) and listed:
        pairs = list(listed.items())
    else:
        label = entry.get("maxquality") if isinstance(entry.get("maxquality"), str) else _AUTO_QUALITY
        pairs = [(label, entry.get("url"))]
    return [{"label": str(label), "url": url} for label, url in pairs if isinstance(url, str) and url and not _BLOCKED.search(url)]


def _subtitles(entry: dict) -> list[dict]:
    found = entry.get("subtitles")
    if not isinstance(found, list):
        return []
    return [{"label": s.get("label") or "", "url": s["url"]} for s in found if isinstance(s, dict) and s.get("url")]


def _episode(entry: dict) -> dict | None:
    number = entry.get("e")
    if number is None:
        return None
    return {"season": entry.get("s"), "number": number, "name": str(entry.get("name") or f"{number} серия")}


def _seasons(data: dict) -> list[dict]:
    return [
        {"name": str(s.get("name") or s.get("id")), "url": s["url"]}
        for s in data.get("data") or []
        if isinstance(s, dict) and s.get("url")
    ]


def parse_variants(data, source_url: str) -> dict | None:
    """Варианты фильма или серии сезона. None, если смотреть нечего."""
    if not isinstance(data, dict) or data.get("type") not in ("movie", "episode"):
        return None
    voices = [
        {"name": v["name"], "url": v["url"], "active": bool(v.get("active"))}
        for v in data.get("voice") or []
        if isinstance(v, dict) and v.get("name") and v.get("url")
    ]
    active = next((v["name"] for v in voices if v["active"]), None)
    items = []
    for entry in data.get("data") or []:
        if not isinstance(entry, dict) or entry.get("method") != "play":
            continue
        qualities = _qualities(entry)
        if qualities:
            items.append({
                "voice": entry.get("voice_name") or active or entry.get("translate") or "",
                "qualities": qualities,
                "subtitles": _subtitles(entry),
                "episode": _episode(entry),
            })
    if not items:
        return None
    return {"url": source_url, "kind": data["type"], "voices": voices, "seasons": [], "items": items}


def _same_title(found: str, wanted: list[str]) -> bool:
    normal = lambda text: re.sub(r"\W+", " ", clean_title(text).lower().replace("ё", "е")).strip()
    return normal(found) in {normal(title) for title in wanted if title}


def _exact_similar(data, titles: list[str], year: str | None) -> str | None:
    """Список похожих годится, только если в нём точно этот фильм: иначе запустится чужой."""
    if not isinstance(data, dict) or data.get("type") != "similar" or not year:
        return None
    for entry in data.get("data") or []:
        if (
            isinstance(entry, dict)
            and entry.get("url")
            and str(entry.get("year")) == str(year)
            and _same_title(str(entry.get("title") or ""), titles)
        ):
            return entry["url"]
    return None


def load_variants(url: str, titles: list[str] | None = None, year: str | None = None, serial: bool | None = None) -> dict | None:
    """``serial`` отбрасывает ответ другого вида: источник мог найти одноимённый фильм вместо сериала."""
    target = _as_json_url(url)
    data = _get_json(target)
    exact = _exact_similar(data, titles or [], year)
    if exact:
        target = _as_json_url(exact)
        data = _get_json(target)
    if not isinstance(data, dict):
        return None
    if serial is not None and (data.get("type") in ("season", "episode")) != serial:
        return None
    if data.get("type") != "season":
        return parse_variants(data, target)

    seasons = _seasons(data)
    if not seasons:
        return None
    target = _as_json_url(seasons[0]["url"])
    variants = parse_variants(_get_json(target), target)
    if variants is not None:
        variants["seasons"] = seasons
    return variants


def search(
    base: str,
    title: str,
    original_title: str | None,
    year: str | None,
    on_source: Callable[[dict], None],
    check_cancelled: Callable[[], None],
    serial: bool = False,
) -> int:
    """Опросить источники. Каждый найденный сообщается сразу, не дожидаясь остальных."""
    name = _SEASONS_NOTE.sub("", clean_title(title)).split(" / ")[0].strip()
    query = {
        "id": stable_id(name, year, serial),
        "serial": int(serial),
        "title": name,
        "original_title": original_title or "",
        "year": year or "",
    }
    titles = [name, original_title or ""]
    started = _get_json(f"{base}/lite/events", {**query, "life": "true"})
    memkey = started.get("memkey") if isinstance(started, dict) else None
    if not memkey:
        raise Unavailable("нет ключа проверки")

    checked: set[str] = set()
    pending: dict[Future, dict] = {}
    found = 0

    def load(item: dict) -> dict | None:
        sep = "&" if "?" in item["url"] else "?"
        variants = load_variants(f"{item['url']}{sep}{urlencode(query)}", titles, year, serial)
        if variants is None:
            return None
        return {"id": item["balanser"], "name": _name_only(str(item.get("name") or item["balanser"])), "variants": variants}

    def collect() -> None:
        nonlocal found
        for future in [f for f in pending if f.done()]:
            item = pending.pop(future)
            try:
                source = future.result()
            except Exception as exc:
                # Сбой одного источника, в том числе неожиданный ответ, не мешает остальным.
                print(f"lampac: {item.get('balanser')}: {type(exc).__name__}: {exc}", file=sys.stderr)
                continue
            if source is not None:
                found += 1
                on_source(source)

    seen = 0
    deadline = time.monotonic() + _SEARCH_LIMIT_SECONDS
    ready = False
    failure: Unavailable | None = None
    pool = ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="lampac")
    try:
        while time.monotonic() < deadline and not (ready and not pending):
            check_cancelled()
            collect()
            if not ready:
                try:
                    poll = _get_json(f"{base}/lifeevents", {"memkey": memkey, "seen": seen}, _POLL_TIMEOUT_SECONDS)
                except Unavailable as exc:
                    # Уже запрошенные источники ещё могут ответить.
                    failure, ready = exc, True
                    continue
                online = poll.get("online") if isinstance(poll, dict) else None
                if not isinstance(online, list):
                    ready = True
                    continue
                seen = len(online)
                ready = bool(poll.get("ready"))
                for item in online:
                    key = item.get("balanser") if isinstance(item, dict) else None
                    if key and item.get("show") and item.get("url") and key not in checked:
                        checked.add(key)
                        pending[pool.submit(load, item)] = item
            time.sleep(_POLL_PAUSE_SECONDS)
        collect()
    finally:
        # Не ждать идущие запросы: отменённый поиск не должен занимать общую очередь.
        pool.shutdown(wait=False, cancel_futures=True)
    if failure is not None and not found:
        raise failure
    return found
