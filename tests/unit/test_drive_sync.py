import json
import threading

import pytest
import requests

from mpv_launcher import drive_sync as ds
from mpv_launcher import google_auth
from mpv_launcher import watchlist as wl

TITLE = {"title": "Фильм", "orig_title": "Film", "year": "2020", "kind": "film", "url": "https://example.com/f"}
OTHER = {"title": "Другой", "orig_title": "Other", "year": "2021", "kind": "film", "url": "https://example.com/o"}
FUTURE = "2099-01-01T00:00:00.000000Z"


class FakeDrive:
    def __init__(self):
        self.files: dict[str, dict] = {}
        self.counter = 0
        self.calls: list[str] = []
        self.fail: list[Exception] = []
        self.before_modified = None

    def _tick(self):
        self.counter += 1
        return f"m{self.counter}"

    def put(self, body: bytes) -> str:
        file_id = f"f{len(self.files) + 1}"
        self.files[file_id] = {"body": body, "modifiedTime": self._tick()}
        return file_id

    def _call(self, name):
        self.calls.append(name)
        if self.fail:
            raise self.fail.pop(0)

    def find(self):
        self._call("find")
        return [{"id": k, "modifiedTime": v["modifiedTime"]} for k, v in self.files.items()]

    def download(self, file_id):
        self._call("download")
        return self.files[file_id]["body"]

    def modified(self, file_id):
        self._call("modified")
        if self.before_modified is not None:
            hook, self.before_modified = self.before_modified, None
            hook()
        return self.files[file_id]["modifiedTime"]

    def create(self, body):
        self._call("create")
        return {"id": self.put(body)}

    def update(self, file_id, body):
        self._call("update")
        self.files[file_id] = {"body": body, "modifiedTime": self._tick()}
        return {"id": file_id}

    def delete(self, file_id):
        self._call("delete")
        del self.files[file_id]

    def items(self, file_id="f1"):
        return json.loads(self.files[file_id]["body"])["items"]


class Harness:
    def __init__(self, tmp_path, drive=None, name="a"):
        self.drive = drive or FakeDrive()
        self.states: list[dict] = []
        self.reloaded = 0
        self.cond = threading.Condition()
        self.dropped = 0
        self.watchlist = wl.Watchlist(tmp_path / f"{name}-watchlist.json", on_change=lambda: self.syncer.local_changed())
        self.store = ds.SyncStore(tmp_path / f"{name}-sync.json")
        self.syncer = ds.Syncer(
            self.watchlist, self.drive, self.store, self._state, self._reloaded,
            drop_token=self._drop, debounce=0.05, retry=0.05,
        )

    def _state(self, snapshot):
        with self.cond:
            self.states.append(snapshot)
            self.cond.notify_all()

    def _reloaded(self):
        self.reloaded += 1

    def _drop(self):
        self.dropped += 1

    def wait(self, state, count=1, timeout=3):
        with self.cond:
            ok = self.cond.wait_for(lambda: sum(s["state"] == state for s in self.states) >= count, timeout)
        assert ok, [s["state"] for s in self.states]
        return self.syncer.snapshot()

    def after(self, index, states=("idle", "offline", "error", "auth_required", "disabled"), timeout=3):
        """Первое итоговое состояние после ``index``: цикл синхронизации завершён."""
        with self.cond:
            ok = self.cond.wait_for(lambda: any(s["state"] in states for s in self.states[index:]), timeout)
        assert ok, [s["state"] for s in self.states]
        return next(s for s in self.states[index:] if s["state"] in states)

    def sync(self, email="user@example.com"):
        with self.cond:
            index = len(self.states)
        if self.syncer.enabled:
            assert self.syncer.request()
        else:
            self.syncer.enable(email)
        # enable() сначала сообщает idle — ждём завершения цикла после syncing.
        with self.cond:
            assert self.cond.wait_for(lambda: any(s["state"] == "syncing" for s in self.states[index:]), 3)
            index += next(i for i, s in enumerate(self.states[index:]) if s["state"] == "syncing")
        return self.after(index)

    def close(self):
        self.syncer.stop()


@pytest.fixture
def make(tmp_path):
    made = []

    def factory(**kwargs):
        made.append(Harness(tmp_path, **kwargs))
        return made[-1]

    yield factory
    for h in made:
        h.close()


# --- формат ---


def test_decode_rejects_bad_files():
    for body in (b"not json", b"[]", b'{"version": 1}', b'{"version": 2, "items": {}}', b'{"items": {}}', b"\xff"):
        with pytest.raises(ds.BadRemote):
            ds.decode(body)
    assert ds.decode(ds.encode({"a": {}}, "t")) == {"a": {}}


def test_store_defaults_and_roundtrip(tmp_path):
    store = ds.SyncStore(tmp_path / "sync.json")
    assert store.load() == {"pending": True, "last_synced_at": None, "email": None}
    (tmp_path / "sync.json").write_text("{bad", encoding="utf-8")
    assert store.load()["pending"] is True
    store.save({"pending": False, "last_synced_at": "t", "email": "e"})
    assert store.load() == {"pending": False, "last_synced_at": "t", "email": "e"}


# --- Drive ---


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code = status
        self._payload = payload
        self.content = content

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


class FakeHttp:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_drive_maps_errors_and_sends_token():
    http = FakeHttp([
        FakeResponse(200, {"files": [{"id": "x", "modifiedTime": "m"}]}),
        requests.ConnectionError(),
        FakeResponse(401),
        FakeResponse(503),
        FakeResponse(403, {"error": {"message": "quota"}}),
        FakeResponse(403, {"error": {"message": "slow down", "errors": [{"reason": "userRateLimitExceeded"}]}}),
    ])
    drive = ds.Drive(lambda: "tok", http)
    assert drive.find() == [{"id": "x", "modifiedTime": "m"}]
    method, url, kwargs = http.calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["params"]["spaces"] == "appDataFolder"
    with pytest.raises(ds.DriveOffline):
        drive.find()
    with pytest.raises(ds.DriveUnauthorized):
        drive.find()
    with pytest.raises(ds.DriveOffline):
        drive.find()
    with pytest.raises(ds.DriveRejected, match="quota"):
        drive.find()
    with pytest.raises(ds.DriveOffline):
        drive.find()


def test_drive_create_uses_app_data_folder():
    http = FakeHttp([FakeResponse(200, {"id": "new"})])
    ds.Drive(lambda: "tok", http).create(b'{"items": {}}')
    method, url, kwargs = http.calls[0]
    assert method == "POST" and url == ds.UPLOAD_URL
    assert b'"parents": ["appDataFolder"]' in kwargs["data"]
    assert kwargs["headers"]["Content-Type"].startswith("multipart/related; boundary=")


# --- синхронизация ---


def test_first_sync_creates_cloud_file(make):
    h = make()
    h.watchlist.set_status(TITLE, "planned")
    state = h.sync()
    assert state["state"] == "idle" and state["pending"] is False and state["last_synced_at"]
    assert h.drive.calls.count("create") == 1
    assert h.watchlist.key_of(TITLE) in h.drive.items()
    assert h.store.load()["email"] == "user@example.com"


def test_two_devices_merge(make, tmp_path):
    drive = FakeDrive()
    a, b = make(drive=drive, name="a"), make(drive=drive, name="b")
    a.watchlist.set_status(TITLE, "planned")
    a.sync()
    b.watchlist.set_status(OTHER, "watching")
    b.sync()
    assert b.reloaded == 1
    assert b.watchlist.get(TITLE)["status"] == "planned"
    a.sync()
    assert a.watchlist.get(OTHER)["status"] == "watching"
    b.watchlist.remove(TITLE)
    b.sync()
    a.sync()
    assert a.watchlist.get(TITLE) is None
    for _ in range(3):
        a.sync()
        b.sync()
    assert a.watchlist.get(TITLE) is None and b.watchlist.get(TITLE) is None


def test_bad_remote_changes_nothing(make):
    h = make()
    h.drive.put(b"garbage")
    h.watchlist.set_status(TITLE, "planned")
    before = h.watchlist.export_items()
    state = h.sync()
    assert state["state"] == "error" and state["message"] == ds.MESSAGE_BAD_REMOTE
    assert h.drive.files["f1"]["body"] == b"garbage"
    assert h.watchlist.export_items() == before
    assert state["pending"] is True


def test_race_retries_and_keeps_both(make):
    h = make()
    other = wl.Watchlist(h.watchlist._path.with_name("other.json"))
    other.set_status(OTHER, "planned")
    h.drive.put(ds.encode(other.export_items(), "t"))
    h.watchlist.set_status(TITLE, "planned")

    def other_device_writes():
        other.set_status(OTHER, "completed")
        h.drive.update("f1", ds.encode(other.export_items(), "t2"))

    h.drive.before_modified = other_device_writes
    assert h.sync()["state"] == "idle"
    items = h.drive.items()
    assert h.watchlist.key_of(TITLE) in items
    assert items[other.key_of(OTHER)]["status"] == "completed"
    assert h.drive.calls.count("find") == 2


def test_duplicate_files_are_merged(make):
    h = make()
    one = wl.Watchlist(h.watchlist._path.with_name("one.json"))
    one.set_status(TITLE, "planned")
    two = wl.Watchlist(h.watchlist._path.with_name("two.json"))
    two.set_status(OTHER, "planned")
    h.drive.put(ds.encode(one.export_items(), "t"))
    h.drive.put(ds.encode(two.export_items(), "t"))
    h.sync()
    assert list(h.drive.files) == ["f1"]
    assert set(h.drive.items()) == {one.key_of(TITLE), two.key_of(OTHER)}


def test_change_during_cycle_keeps_pending(make):
    h = make()
    h.watchlist.set_status(TITLE, "planned")
    h.drive.before_modified = lambda: h.syncer.local_changed()
    h.syncer.enable("user@example.com")
    h.wait("idle", 2)
    # Повтор после debounce отправляет и это изменение.
    with h.cond:
        assert h.cond.wait_for(lambda: h.syncer.snapshot()["pending"] is False, 3)


def test_unauthorized_retries_with_new_token(make):
    h = make()
    h.drive.fail = [ds.DriveUnauthorized()]
    assert h.sync()["state"] == "idle"
    assert h.dropped == 1


def test_second_unauthorized_is_retryable_error(make):
    h = make()
    h.drive.fail = [ds.DriveUnauthorized(), ds.DriveUnauthorized()]
    state = h.sync()
    assert state["state"] == "error" and state["message"] == ds.MESSAGE_UNAUTHORIZED
    assert h.sync()["state"] == "idle"


def test_expired_and_rejected(make):
    h = make()
    h.drive.fail = [google_auth.Expired()]
    assert h.sync()["state"] == "auth_required"
    h.drive.fail = [ds.DriveRejected("quota")]
    state = h.sync()
    assert state["state"] == "error" and "quota" in state["message"]


def test_debounce_collapses_changes(make):
    h = make()
    h.sync()
    writes = h.drive.calls.count("create") + h.drive.calls.count("update")
    index = len(h.states)
    for status in ("planned", "watching", "completed"):
        h.watchlist.set_status(TITLE, status)
    h.after(index + 1, ("idle",))
    assert h.drive.calls.count("create") + h.drive.calls.count("update") == writes + 1
    assert h.drive.items()[h.watchlist.key_of(TITLE)]["status"] == "completed"


def test_offline_changes_are_sent_later(make):
    h = make()
    h.drive.fail = [ds.DriveOffline("x")]
    h.watchlist.set_status(TITLE, "planned")
    state = h.sync()
    assert state["state"] == "offline" and state["pending"] is True
    h.wait("idle", 2)
    assert h.syncer.snapshot()["pending"] is False
    assert h.watchlist.key_of(TITLE) in h.drive.items()


def test_pending_survives_restart(make, tmp_path):
    drive = FakeDrive()
    h = make(drive=drive)
    h.watchlist.set_status(TITLE, "planned")
    assert h.store.load()["pending"] is True
    h.close()
    again = make(drive=drive)
    assert again.syncer.snapshot()["pending"] is True
    assert again.sync()["pending"] is False
    assert again.watchlist.key_of(TITLE) in drive.items()


def test_disabled_makes_no_requests(make):
    h = make()
    h.watchlist.set_status(TITLE, "planned")
    assert h.syncer.request() is False
    h.sync()
    h.syncer.disable()
    calls = len(h.drive.calls)
    h.watchlist.set_status(TITLE, "completed")
    assert h.syncer.request() is False
    threading.Event().wait(0.2)
    assert len(h.drive.calls) == calls
    assert h.watchlist.get(TITLE)["status"] == "completed"
    assert h.syncer.snapshot()["state"] == "disabled"
    assert h.store.load()["email"] is None


def test_sign_out_keeps_cloud(make):
    h = make()
    h.watchlist.set_status(TITLE, "planned")
    h.sync()
    cloud = dict(h.drive.files)
    h.syncer.disable()
    assert h.drive.files == cloud
    assert h.watchlist.get(TITLE) is not None


def test_other_account_merges_local(make):
    first, second = FakeDrive(), FakeDrive()
    h = make(drive=first)
    h.watchlist.set_status(TITLE, "planned")
    h.sync("one@example.com")
    h.syncer.disable()
    remote = wl.Watchlist(h.watchlist._path.with_name("remote.json"))
    remote.set_status(OTHER, "planned")
    second.put(ds.encode(remote.export_items(), "t"))
    h.syncer._drive = second
    h.sync("two@example.com")
    assert set(second.items()) == {h.watchlist.key_of(TITLE), remote.key_of(OTHER)}
    assert h.store.load()["email"] == "two@example.com"


def test_offline_start_retries_without_pending(make):
    h = make()
    h.store.save({"pending": False, "last_synced_at": None, "email": None})
    h.syncer._pending = False
    remote = wl.Watchlist(h.watchlist._path.with_name("remote.json"))
    remote.set_status(OTHER, "planned")
    h.drive.put(ds.encode(remote.export_items(), "t"))
    h.drive.fail = [ds.DriveOffline("x")]
    assert h.sync()["state"] == "offline"
    h.wait("idle", 2)
    assert h.watchlist.get(OTHER)["status"] == "planned"
