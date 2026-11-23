"""Список: ключи, статусы, удаление, серии, перенос на id IMDb, повреждённый файл, атомарная запись."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from mpv_launcher import watchlist
from mpv_launcher.watchlist import Watchlist


def film(**over):
    return {"title": "Матрица", "orig_title": "The Matrix", "year": "1999", "kind": "film",
            "url": "https://uakinogo.io/filmy/1-matrica.html", "poster_url": None, **over}


def series(**over):
    return film(title="Проект Лазарь (1-2 сезон)", orig_title="Lazarus Project", year="2022", kind="series",
                url="https://uakinogo.io/serialy/2-lazar.html", **over)


class Clock:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return (datetime(2026, 11, 16, tzinfo=timezone.utc) + timedelta(seconds=self.n)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@pytest.fixture
def path(tmp_path):
    return tmp_path / "watchlist.json"


@pytest.fixture
def wl(path):
    return Watchlist(path, clock=Clock())


def test_fallback_key_normalizes_name():
    assert watchlist.fallback_key("Ёлки", None, "2010", "film") == "t:film:2010:елки"
    assert watchlist.fallback_key("Проект Лазарь (1-2 сезон)", None, "2022", "series") == "t:series:2022:проект лазарь"
    assert watchlist.fallback_key("Дюна / Dune", None, "2021", "film") == "t:film:2021:дюна"
    assert watchlist.fallback_key("x", "Spider-Man: No Way Home", "2021", "film") == "t:film:2021:spider man no way home"


@pytest.mark.parametrize("bad", [
    None, {}, film(title=" "), film(url="ftp://x"), film(kind="anime"), film(year="99"), film(poster_url="x"),
])
def test_invalid_title_rejected(wl, bad):
    with pytest.raises(ValueError):
        wl.set_status(bad, "planned")


def test_status_roundtrip_survives_reload(wl, path):
    entry = wl.set_status(film(), "planned")
    assert entry["status"] == "planned" and entry["key"] == "t:film:1999:the matrix"
    assert "fallback_key" not in entry
    assert Watchlist(path).get(film())["status"] == "planned"


def test_invalid_status_rejected(wl):
    with pytest.raises(ValueError):
        wl.set_status(film(), "dropped")


def test_same_title_other_url_is_one_entry(wl):
    wl.set_status(film(), "planned")
    wl.set_status(film(url="https://kinogo.zone/filmy/1-matrica.html"), "completed")
    assert [e["status"] for e in wl.entries()] == ["completed"]


def test_remove_keeps_tombstone_and_readd_starts_clean(wl, path):
    wl.set_episode(series(), "1", "1", True)
    wl.remove(series())
    assert wl.get(series()) is None and wl.entries() == []
    stored = json.loads(path.read_text(encoding="utf-8"))["items"]["t:series:2022:lazarus project"]
    assert stored["deleted_at"] and stored["status"] is None and stored["episodes"] == {}
    again = wl.set_status(series(), "planned")
    assert again["episodes"] == {} and again["deleted_at"] is None


def test_entries_sorted_newest_first(wl):
    wl.set_status(film(), "planned")
    wl.set_status(series(), "watching")
    assert [e["kind"] for e in wl.entries()] == ["series", "film"]
    wl.set_status(film(), "completed")
    assert [e["kind"] for e in wl.entries()] == ["film", "series"]


@pytest.mark.parametrize("before, after", [(None, "watching"), ("planned", "watching"),
                                           ("watching", "watching"), ("completed", "completed")])
def test_play_started_transitions(wl, before, after):
    if before:
        wl.set_status(film(), before)
    assert wl.on_play_started(film())["status"] == after


def test_play_started_restores_removed(wl):
    wl.set_status(film(), "completed")
    wl.remove(film())
    assert wl.on_play_started(film())["status"] == "watching"


def test_episodes_marking(wl):
    wl.set_status(series(), "planned")
    for ep in ("10", "2", "1", "2"):
        entry = wl.set_episode(series(), "1", ep, True)
    assert entry["episodes"] == {"1": ["1", "2", "10"]} and entry["status"] == "watching"
    wl.set_status(series(), "completed")
    entry = wl.set_episode(series(), "1", "2", False)
    assert entry["episodes"] == {"1": ["1", "10"]} and entry["status"] == "completed"


def test_unmark_without_entry_creates_nothing(wl):
    assert wl.set_episode(series(), "1", "1", False) is None
    assert wl.entries() == []


def test_episodes_only_for_series(wl):
    with pytest.raises(ValueError):
        wl.set_episode(film(), "1", "1", True)


def test_corrupted_file_set_aside(path):
    path.write_text("{мусор", encoding="utf-8")
    wl = Watchlist(path)
    assert wl.entries() == []
    assert wl.take_warning() == "watchlist_reset"
    assert wl.take_warning() is None
    assert len(list(path.parent.glob("watchlist.broken-*.json"))) == 1


def test_failed_write_keeps_previous_file(wl, path, monkeypatch):
    wl.set_status(film(), "planned")
    before = path.read_text(encoding="utf-8")

    def boom(*_args):
        raise OSError("диск")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        wl.set_status(film(), "completed")
    assert path.read_text(encoding="utf-8") == before
    assert wl.get(film())["status"] == "planned"
    assert list(path.parent.glob(".watchlist-*")) == []


def test_lookup_needed_until_found_and_retried_after_week(wl, path):
    assert wl.needs_lookup(film())
    wl.apply_id(film(), None)
    assert not wl.needs_lookup(film())
    data = json.loads(path.read_text(encoding="utf-8"))
    old = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    data["lookups"]["t:film:1999:the matrix"]["checked_at"] = old
    path.write_text(json.dumps(data), encoding="utf-8")
    assert Watchlist(path).needs_lookup(film())


def test_apply_id_moves_entry(wl, path):
    wl.set_status(film(), "planned")
    moved = wl.apply_id(film(), "tt0133093")
    assert moved["key"] == "tt0133093" and moved["status"] == "planned"
    assert wl.get(film())["key"] == "tt0133093"
    assert [e["key"] for e in wl.entries()] == ["tt0133093"]
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    assert items["t:film:1999:the matrix"]["deleted_at"]
    # Дальнейшие изменения идут в запись с id.
    assert wl.set_status(film(), "completed")["key"] == "tt0133093"


def test_apply_id_merges_with_existing(path):
    # Запись под id и запись под запасным ключом (пришла бы с другого устройства).
    fb = "t:series:2022:lazarus project"
    base = {**series(), "fallback_key": fb, "deleted_at": None}
    path.write_text(json.dumps({"version": 1, "lookups": {}, "items": {
        "tt100": {**base, "key": "tt100", "fallback_key": "other", "status": "watching",
                  "episodes": {"1": ["1"]}, "updated_at": "2026-11-01T00:00:00.000000Z"},
        fb: {**base, "key": fb, "status": "completed", "episodes": {"1": ["2"], "2": ["1"]},
             "updated_at": "2026-11-02T00:00:00.000000Z"},
    }}), encoding="utf-8")
    merged = Watchlist(path).apply_id(series(), "tt100")
    assert merged["status"] == "completed"
    assert merged["episodes"] == {"1": ["1", "2"], "2": ["1"]}
    assert [e["key"] for e in Watchlist(path).entries()] == ["tt100"]


def test_apply_id_rejects_bad_id(wl):
    with pytest.raises(ValueError):
        wl.apply_id(film(), "123")


def test_locked_file_is_not_treated_as_corrupt(wl, path, monkeypatch):
    wl.set_status(film(), "planned")
    fresh = Watchlist(path)
    real = type(path).read_text

    def locked(self, *args, **kwargs):
        if self == path:
            raise PermissionError("занят")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "read_text", locked)
    with pytest.raises(PermissionError):
        fresh.entries()
    monkeypatch.undo()
    assert list(path.parent.glob("watchlist.broken-*.json")) == []
    assert fresh.take_warning() is None
    assert fresh.get(film())["status"] == "planned"
