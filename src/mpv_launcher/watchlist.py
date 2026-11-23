"""Личный список тайтлов со статусами просмотра: JSON в каталоге приложения, запись атомарна.

Записи не удаляются, а получают пометку ``deleted_at``: так будущая синхронизация между
устройствами узнает об удалении, а не вернёт запись обратно.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import settings
from .sources import clean_title

STATUSES = ("watching", "planned", "completed")
KINDS = ("film", "series")
SOURCES = ("kinogo", "hdrezka", "lampac")
LOOKUP_RETRY = timedelta(days=7)
TOMBSTONE_TTL = timedelta(days=90)

_SEASONS_NOTE = re.compile(r"\s*\([^)]*сезон[^)]*\)", re.I)
_YEAR = re.compile(r"\d{4}")
_ID_KEY = re.compile(r"(tt\d+|kp:\d+)")
_TITLE_FIELDS = ("title", "orig_title", "year", "kind", "url", "poster_url", "source")


def default_path() -> Path:
    return settings.data_dir() / "watchlist.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def normalize_name(text: str) -> str:
    """Название для сравнения: без пометок сезонов, регистра, «ё» и знаков препинания."""
    name = _SEASONS_NOTE.sub("", clean_title(text)).split(" / ")[0]
    return re.sub(r"[\W_]+", " ", name.lower().replace("ё", "е")).strip()


def fallback_key(title: str, orig_title: str | None, year: str | None, kind: str) -> str:
    """Ключ тайтла, пока не известен id IMDb или КиноПоиска."""
    return f"t:{kind}:{year or ''}:{normalize_name(orig_title or title)}"


def _http(value) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def parse_title(raw) -> dict:
    """Описание тайтла со страницы. ValueError при неверных данных."""
    if not isinstance(raw, dict):
        raise ValueError("Нет описания тайтла")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Нет названия")
    if not _http(raw.get("url")):
        raise ValueError("Неверный адрес страницы")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ValueError("Неверный тип тайтла")
    year = raw.get("year")
    if year is not None and not (isinstance(year, str) and _YEAR.fullmatch(year)):
        raise ValueError("Неверный год")
    orig = raw.get("orig_title")
    if orig is not None and not isinstance(orig, str):
        raise ValueError("Неверное оригинальное название")
    poster = raw.get("poster_url")
    if poster is not None and not _http(poster):
        raise ValueError("Неверный адрес постера")
    source = raw.get("source")
    if source is not None and source not in SOURCES:
        raise ValueError("Неверный источник")
    parsed = {
        "title": title.strip(),
        "orig_title": orig.strip() or None if orig else None,
        "year": year,
        "kind": kind,
        "url": raw["url"],
        "poster_url": poster,
        "source": source,
    }
    if not normalize_name(parsed["orig_title"] or parsed["title"]):
        raise ValueError("Пустое название")
    return parsed


def public(entry: dict | None) -> dict | None:
    """Запись для интерфейса: без служебного запасного ключа."""
    if entry is None or entry.get("deleted_at"):
        return None
    return {k: v for k, v in entry.items() if k != "fallback_key"}


def _merge_rank(entry: dict) -> tuple[str, str]:
    """Порядок вариантов записи: позднее изменение побеждает, при равенстве — одинаково везде."""
    return entry["updated_at"], json.dumps(entry, sort_keys=True, ensure_ascii=False)


def merge_items(local: dict, remote: dict, now: datetime | None = None) -> dict:
    """Слияние списков по записям (last-write-wins по ``updated_at``), удаления — tombstones.

    Запись берётся целиком, поэтому поля новых версий приложения не теряются. Tombstones
    старше ``TOMBSTONE_TTL`` убираются из результата.
    """
    merged: dict = {}
    for items in (local, remote):
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if not (isinstance(key, str) and isinstance(entry, dict) and isinstance(entry.get("updated_at"), str)):
                continue
            current = merged.get(key)
            if current is None or _merge_rank(entry) > _merge_rank(current):
                merged[key] = entry
    limit = (now or datetime.now(timezone.utc)) - TOMBSTONE_TTL
    for key in [k for k, e in merged.items() if e.get("deleted_at")]:
        deleted = _parse_time(merged[key]["deleted_at"])
        if deleted is not None and deleted < limit:
            del merged[key]
    return json.loads(json.dumps(merged))


def _episode_order(value: str):
    return (0, int(value), "") if value.isdigit() else (1, 0, value)


class Watchlist:
    def __init__(
        self,
        path: Path | None = None,
        clock: Callable[[], str] = _now,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._path = Path(path or default_path())
        self._on_change = on_change
        self._read_clock = clock
        self._last_time = ""
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._warning: str | None = None

    def _clock(self) -> str:
        """Время изменения строго растёт: у часов Windows грубый шаг, а порядок списка важен."""
        value = self._read_clock()
        if value <= self._last_time:
            last = _parse_time(self._last_time)
            if last is not None:
                value = (last + timedelta(microseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self._last_time = value
        return value

    def _stamp(self, entry: dict | None) -> str:
        """Время изменения записи позже её прежнего: иначе правка записи, пришедшей с устройства
        с убежавшими вперёд часами, проиграет слияние и откатится."""
        value = self._clock()
        previous = _parse_time(entry.get("updated_at")) if entry else None
        if previous is not None and value <= entry["updated_at"]:
            value = (previous + timedelta(microseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            self._last_time = value
        return value

    # --- файл ---

    def _load(self) -> dict:
        if self._data is not None:
            return self._data
        data = {"version": 1, "items": {}, "lookups": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = data
        except ValueError:
            raw = None
        # Прочие OSError (файл занят антивирусом или резервным копированием) уходят наверх:
        # список не загружен и не кешируется, следующее обращение прочитает файл снова.
        if not (isinstance(raw, dict) and isinstance(raw.get("items"), dict) and isinstance(raw.get("lookups", {}), dict)):
            self._set_aside()
            raw = data
        data["items"] = {k: v for k, v in raw["items"].items() if isinstance(v, dict)}
        data["lookups"] = {k: v for k, v in raw.get("lookups", {}).items() if isinstance(v, dict)}
        self._data = data
        return data

    def _set_aside(self) -> None:
        """Нечитаемый файл сохраняется рядом: список начинается заново, данные не пропадают."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        try:
            self._path.replace(self._path.with_name(f"watchlist.broken-{stamp}.json"))
        except OSError as exc:
            print(f"watchlist: повреждённый файл не перенесён: {type(exc).__name__}", file=sys.stderr)
        self._warning = "watchlist_reset"

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, prefix=".watchlist-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=1)
            os.replace(tmp_name, self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _commit(self, change: Callable[[dict], dict | None], notify: bool = True) -> dict | None:
        """Изменение применяется к копии: при сбое записи список в памяти остаётся прежним."""
        with self._lock:
            current = self._load()
            draft = json.loads(json.dumps(current))
            result = change(draft)
            if draft == current:
                return result
            self._save(draft)
            self._data = draft
            # Облаку нужны только записи; кэш поиска id (lookups) не синхронизируется.
            notify = notify and draft["items"] != current["items"]
        if notify and self._on_change is not None:
            try:
                self._on_change()
            except Exception as exc:
                print(f"watchlist: on_change: {type(exc).__name__}: {exc}", file=sys.stderr)
        return result

    # --- синхронизация ---

    def export_items(self) -> dict:
        """Все записи, включая удалённые: копия для облака."""
        with self._lock:
            return json.loads(json.dumps(self._load()["items"]))

    def merge(self, remote_items: dict, now: datetime | None = None) -> bool:
        """Слить облачные записи с локальными. True — локальный список изменился."""
        changed = False

        def change(data):
            nonlocal changed
            merged = merge_items(data["items"], remote_items, now)
            changed = merged != data["items"]
            data["items"] = merged

        self._commit(change, notify=False)
        return changed

    def take_warning(self) -> str | None:
        with self._lock:
            self._load()
            warning, self._warning = self._warning, None
            return warning

    # --- поиск ---

    @staticmethod
    def _find(data: dict, title: dict) -> tuple[str, dict | None]:
        """Ключ записи тайтла и сама запись (или ключ, под которым её создать)."""
        fallback = fallback_key(title["title"], title["orig_title"], title["year"], title["kind"])
        known = (data["lookups"].get(fallback) or {}).get("imdb")
        items = data["items"]
        candidates = [k for k in (known, fallback) if k and k in items]
        candidates += [k for k, e in items.items() if e.get("fallback_key") == fallback and k not in candidates]
        for key in candidates:
            if not items[key].get("deleted_at"):
                return key, items[key]
        # Удалённая запись под нужным ключом возвращается заново, а не дублируется.
        key = known or fallback
        return key, items.get(key)

    def get(self, raw_title) -> dict | None:
        title = parse_title(raw_title)
        with self._lock:
            return public(self._find(self._load(), title)[1])

    def key_of(self, raw_title) -> str:
        title = parse_title(raw_title)
        with self._lock:
            return self._find(self._load(), title)[0]

    def entries(self) -> list[dict]:
        with self._lock:
            items = [public(e) for e in self._load()["items"].values()]
        return sorted((e for e in items if e), key=lambda e: e.get("updated_at") or "", reverse=True)

    # --- изменения ---

    def _touch(self, data: dict, title: dict) -> dict:
        """Запись тайтла с данными страницы; удалённая возвращается без отметок серий."""
        key, entry = self._find(data, title)
        if entry is None or entry.get("deleted_at"):
            entry = {
                "key": key,
                "fallback_key": fallback_key(title["title"], title["orig_title"], title["year"], title["kind"]),
                "status": None,
                "episodes": {},
                "deleted_at": None,
            }
            data["items"][key] = entry
        for name in _TITLE_FIELDS:
            if title[name] is not None or name not in entry:
                entry[name] = title[name]
        entry["updated_at"] = self._stamp(entry)
        return entry

    def set_status(self, raw_title, status: str) -> dict:
        title = parse_title(raw_title)
        if status not in STATUSES:
            raise ValueError("Неверный статус")

        def change(data):
            entry = self._touch(data, title)
            entry["status"] = status
            return public(entry)

        return self._commit(change)

    def remove(self, raw_title) -> None:
        title = parse_title(raw_title)

        def change(data):
            _key, entry = self._find(data, title)
            if entry is None or entry.get("deleted_at"):
                return None
            now = self._stamp(entry)
            entry.update(status=None, episodes={}, deleted_at=now, updated_at=now)
            return None

        self._commit(change)

    @staticmethod
    def _start_watching(entry: dict) -> None:
        if entry.get("status") in (None, "planned"):
            entry["status"] = "watching"

    def on_play_started(self, raw_title) -> dict:
        title = parse_title(raw_title)

        def change(data):
            _key, entry = self._find(data, title)
            if entry is not None and not entry.get("deleted_at") and entry.get("status") in ("watching", "completed"):
                return public(entry)
            entry = self._touch(data, title)
            self._start_watching(entry)
            return public(entry)

        return self._commit(change)

    def set_episode(self, raw_title, season: str, episode: str, watched: bool) -> dict | None:
        title = parse_title(raw_title)
        if title["kind"] != "series":
            raise ValueError("Серии есть только у сериалов")
        if not (isinstance(season, str) and season.strip() and isinstance(episode, str) and episode.strip()):
            raise ValueError("Неверная серия")
        if not isinstance(watched, bool):
            raise ValueError("Неверная отметка")

        def change(data):
            _key, entry = self._find(data, title)
            if not watched and (entry is None or entry.get("deleted_at")):
                return public(entry)
            entry = self._touch(data, title)
            marks = set(entry["episodes"].get(season, []))
            if watched:
                marks.add(episode)
                self._start_watching(entry)
            else:
                marks.discard(episode)
            if marks:
                entry["episodes"][season] = sorted(marks, key=_episode_order)
            else:
                entry["episodes"].pop(season, None)
            return public(entry)

        return self._commit(change)

    # --- id IMDb ---

    def needs_lookup(self, raw_title) -> bool:
        title = parse_title(raw_title)
        fallback = fallback_key(title["title"], title["orig_title"], title["year"], title["kind"])
        with self._lock:
            lookup = self._load()["lookups"].get(fallback)
        if not lookup:
            return True
        if lookup.get("imdb"):
            return False
        checked = _parse_time(lookup.get("checked_at"))
        return checked is None or datetime.now(timezone.utc) - checked >= LOOKUP_RETRY

    def apply_id(self, raw_title, imdb_id: str | None) -> dict | None:
        """Запомнить результат поиска id; найденный id становится ключом записи."""
        title = parse_title(raw_title)
        if imdb_id is not None and not _ID_KEY.fullmatch(imdb_id):
            raise ValueError("Неверный id")
        fallback = fallback_key(title["title"], title["orig_title"], title["year"], title["kind"])

        def change(data):
            data["lookups"][fallback] = {"imdb": imdb_id, "checked_at": self._clock()}
            if imdb_id is None:
                return public(self._find(data, title)[1])
            source_key = next(
                (k for k, e in data["items"].items()
                 if k != imdb_id and e.get("fallback_key") == fallback and not e.get("deleted_at")),
                None,
            )
            if source_key is None:
                return public(data["items"].get(imdb_id))
            source = data["items"][source_key]
            target = data["items"].get(imdb_id)
            if target is None or target.get("deleted_at"):
                merged = {**source, "key": imdb_id}
            else:
                newer, older = (source, target) if source["updated_at"] > target["updated_at"] else (target, source)
                merged = {**newer, "key": imdb_id, "fallback_key": fallback}
                seasons = set(newer.get("episodes", {})) | set(older.get("episodes", {}))
                merged["episodes"] = {
                    s: sorted(set(newer.get("episodes", {}).get(s, [])) | set(older.get("episodes", {}).get(s, [])),
                              key=_episode_order)
                    for s in seasons
                }
            data["items"][imdb_id] = merged
            now = self._stamp(source)
            data["items"][source_key] = {**source, "status": None, "episodes": {}, "deleted_at": now, "updated_at": now}
            return public(merged)

        return self._commit(change)
