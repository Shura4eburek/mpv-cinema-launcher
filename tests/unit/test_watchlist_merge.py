from datetime import datetime, timedelta, timezone

from mpv_launcher import watchlist as wl

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
T1 = "2026-11-10T10:00:00.000000Z"
T2 = "2026-11-11T10:00:00.000000Z"
OLD = (NOW - timedelta(days=91)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def entry(key, updated, status="planned", deleted=None, **extra):
    return {"key": key, "status": status, "episodes": {}, "deleted_at": deleted, "updated_at": updated, **extra}


TITLE = {"title": "Фильм", "orig_title": "Film", "year": "2020", "kind": "film", "url": "https://example.com/f"}


def test_only_one_side_is_kept():
    merged = wl.merge_items({"a": entry("a", T1)}, {"b": entry("b", T2)}, NOW)
    assert set(merged) == {"a", "b"}


def test_later_change_wins_both_ways():
    old, new = entry("a", T1, "planned"), entry("a", T2, "completed")
    assert wl.merge_items({"a": old}, {"a": new}, NOW)["a"]["status"] == "completed"
    assert wl.merge_items({"a": new}, {"a": old}, NOW)["a"]["status"] == "completed"


def test_equal_time_is_deterministic():
    one, two = entry("a", T1, "planned"), entry("a", T1, "watching")
    assert wl.merge_items({"a": one}, {"a": two}, NOW) == wl.merge_items({"a": two}, {"a": one}, NOW)


def test_tombstone_wins_over_older_and_loses_to_newer():
    alive_old, dead, alive_new = entry("a", T1), entry("a", T2, None, deleted=T2), entry("a", "2026-11-12T00:00:00.000000Z")
    assert wl.merge_items({"a": alive_old}, {"a": dead}, NOW)["a"]["deleted_at"] == T2
    assert wl.merge_items({"a": dead}, {"a": alive_new}, NOW)["a"]["deleted_at"] is None


def test_unknown_fields_survive():
    merged = wl.merge_items({}, {"a": entry("a", T1, rating=5)}, NOW)
    assert merged["a"]["rating"] == 5


def test_garbage_is_dropped():
    merged = wl.merge_items({"a": entry("a", T1)}, {"b": "x", "c": {"status": "planned"}, "d": entry("d", None)}, NOW)
    assert set(merged) == {"a"}
    assert wl.merge_items({"a": entry("a", T1)}, "junk", NOW) == {"a": entry("a", T1)}


def test_old_tombstones_are_pruned():
    merged = wl.merge_items({"a": entry("a", OLD, None, deleted=OLD), "b": entry("b", T1, None, deleted=T1)}, {}, NOW)
    assert set(merged) == {"b"}


def test_merge_is_idempotent():
    local, remote = {"a": entry("a", T1)}, {"a": entry("a", T2), "b": entry("b", T1)}
    once = wl.merge_items(local, remote, NOW)
    assert wl.merge_items(once, remote, NOW) == once


def test_watchlist_merge_and_on_change(tmp_path):
    calls = []
    w = wl.Watchlist(tmp_path / "watchlist.json", on_change=lambda: calls.append(1))
    w.set_status(TITLE, "planned")
    assert calls == [1]
    key = w.key_of(TITLE)
    exported = w.export_items()
    assert w.merge(exported) is False
    later = {key: {**exported[key], "status": "completed", "updated_at": "2099-01-01T00:00:00.000000Z"}}
    assert w.merge(later) is True
    assert w.get(TITLE)["status"] == "completed"
    assert calls == [1]
    reread = wl.Watchlist(tmp_path / "watchlist.json")
    assert reread.get(TITLE)["status"] == "completed"


def test_on_change_failure_does_not_break_change(tmp_path):
    def boom():
        raise RuntimeError("x")

    w = wl.Watchlist(tmp_path / "watchlist.json", on_change=boom)
    assert w.set_status(TITLE, "planned")["status"] == "planned"


def test_no_change_no_notify(tmp_path):
    calls = []
    w = wl.Watchlist(tmp_path / "watchlist.json", on_change=lambda: calls.append(1))
    w.remove(TITLE)
    assert calls == []


def test_edit_beats_entry_from_clock_ahead(tmp_path):
    w = wl.Watchlist(tmp_path / "watchlist.json", clock=lambda: "2026-11-16T10:00:00.000000Z")
    w.set_status(TITLE, "planned")
    key = w.key_of(TITLE)
    ahead = {key: {**w.export_items()[key], "status": "watching", "updated_at": "2026-11-16T10:10:00.000000Z"}}
    assert w.merge(ahead)
    w.set_status(TITLE, "completed")
    assert w.export_items()[key]["updated_at"] > "2026-11-16T10:10:00.000000Z"
    assert not w.merge(ahead)
    assert w.get(TITLE)["status"] == "completed"
    w.remove(TITLE)
    assert w.export_items()[key]["deleted_at"] > "2026-11-16T10:10:00.000000Z"


def test_lookup_only_change_does_not_notify(tmp_path):
    calls = []
    w = wl.Watchlist(tmp_path / "watchlist.json", on_change=lambda: calls.append(1))
    w.apply_id(TITLE, None)
    assert calls == []
