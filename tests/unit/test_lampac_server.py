import json
import threading
from unittest import mock

import pytest

from mpv_launcher import lampac_server as ls


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundle"
    (root / "app").mkdir(parents=True)
    (root / "runtime").mkdir()
    (root / "app" / "Core.dll").write_text("x")
    (root / "runtime" / "dotnet.exe").write_text("x")
    (root / "VERSION").write_text("1.2.3\n")
    return root


def test_install_copies_once_and_removes_old_versions(bundle, tmp_path):
    root = tmp_path / "data"
    (root / "1.0.0").mkdir(parents=True)
    target = ls.install(bundle, root)
    assert target == root / "1.2.3"
    assert (target / "app" / "Core.dll").is_file()
    assert not (root / "1.0.0").exists()
    (target / "app" / "cache.txt").write_text("кеш")
    assert ls.install(bundle, root) == target
    assert (target / "app" / "cache.txt").is_file()


def test_interrupted_copy_is_repeated(bundle, tmp_path):
    root = tmp_path / "data"
    (root / "1.2.3" / "app").mkdir(parents=True)
    target = ls.install(bundle, root)
    assert (target / "app" / "Core.dll").is_file()


def test_config_listens_only_locally_without_browser():
    config = ls._config(5000)
    assert config["listen"]["ip"] == "127.0.0.1"
    assert config["listen"]["port"] == 5000
    assert config["chromium"]["enable"] is False
    assert config["firefox"]["enable"] is False


def _windows():
    return mock.patch.object(ls.platform, "system", return_value="Windows")


class _Process:
    def __init__(self, code=None):
        self.code = code
        self.returncode = code
        self._handle = 1
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.code = 1


def _start(server):
    done = threading.Event()
    original = server._on_state

    def watch(state):
        original(state)
        if state["state"] != "starting":
            done.set()

    server._on_state = watch
    server.enable()
    assert done.wait(5)


def _server(bundle, tmp_path, states):
    return ls.LampacServer(states.append, bundle=bundle, root=tmp_path / "data")


def test_start_reports_running_and_stop_reports_off(bundle, tmp_path):
    states, process = [], _Process()
    server = _server(bundle, tmp_path, states)
    with _windows(), mock.patch.object(ls.subprocess, "Popen", return_value=process) as popen, \
        mock.patch.object(ls.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
        mock.patch.object(ls, "_ProcessGroup"), \
        mock.patch.object(ls.requests, "get", return_value=mock.Mock(ok=True)):
        _start(server)
        assert [s["state"] for s in states] == ["starting", "running"]
        assert server.base_url.startswith("http://127.0.0.1:")
        cwd = popen.call_args.kwargs["cwd"]
        port = json.loads((cwd / "init.conf").read_text(encoding="utf-8"))["listen"]["port"]
        assert server.base_url.endswith(str(port))
        server.close()
    assert process.terminated
    assert server.base_url is None


def test_turning_off_right_after_answer_does_not_hang(bundle, tmp_path):
    states, process = [], _Process()
    server = _server(bundle, tmp_path, states)

    def answer(*args, **kwargs):
        server._wanted = False
        return mock.Mock(ok=True)

    with _windows(), mock.patch.object(ls.subprocess, "Popen", return_value=process), \
        mock.patch.object(ls.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
        mock.patch.object(ls, "_ProcessGroup"), \
        mock.patch.object(ls.requests, "get", side_effect=answer):
        _start(server)
        assert server._lock.acquire(timeout=2)
        server._lock.release()
    assert states[-1]["state"] == "off"
    assert process.terminated


def test_exit_during_start_shows_reason(bundle, tmp_path):
    states = []
    server = _server(bundle, tmp_path, states)
    with _windows(), mock.patch.object(ls.subprocess, "Popen", return_value=_Process(code=3)), \
        mock.patch.object(ls.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
        mock.patch.object(ls, "_ProcessGroup"):
        _start(server)
    assert states[-1]["state"] == "error"
    assert "код 3" in states[-1]["detail"]


def test_missing_bundle_is_reported_without_start(tmp_path):
    states = []
    server = ls.LampacServer(states.append, bundle=tmp_path / "нет", root=tmp_path / "data")
    with _windows(), mock.patch.object(ls.subprocess, "Popen") as popen:
        _start(server)
        assert server.available is False
    popen.assert_not_called()
    assert states[-1]["state"] == "error"


def test_crash_after_start_turns_into_error(bundle, tmp_path):
    states, process = [], _Process()
    server = _server(bundle, tmp_path, states)
    with _windows(), mock.patch.object(ls.subprocess, "Popen", return_value=process), \
        mock.patch.object(ls.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
        mock.patch.object(ls, "_ProcessGroup"), \
        mock.patch.object(ls.requests, "get", return_value=mock.Mock(ok=True)):
        _start(server)
        process.code = 9
        process.returncode = 9
        assert server.base_url is None
    assert states[-1]["state"] == "error"
    assert "9" in states[-1]["detail"]


def test_not_available_on_other_systems(bundle, tmp_path):
    server = _server(bundle, tmp_path, [])
    with mock.patch.object(ls.platform, "system", return_value="Darwin"):
        assert server.available is False
