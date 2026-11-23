"""Локальный сервер Lampac: отдельная неизменённая программа из состава приложения. Только Windows."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from . import settings

_START_TIMEOUT_SECONDS = 90
_POLL_SECONDS = 0.5
_STOP_TIMEOUT_SECONDS = 3
_LOG_TAIL_CHARS = 300
_READY_MARK = ".ready"


def bundle_dir() -> Path | None:
    """Каталог Lampac в составе приложения: рядом с каталогом backend."""
    override = os.environ.get("MPV_CINEMA_LAMPAC_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent / "lampac"
    # Запуск из исходников: каталог, который готовит build_windows.ps1.
    return Path(__file__).resolve().parents[2] / "app" / "src-tauri" / "resources" / "lampac"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _config(port: int) -> dict:
    # Браузер выключен: источники с обходом защиты через него не используются.
    return {
        "listen": {"version": True, "ip": "127.0.0.1", "port": port, "scheme": "http", "localhost": "127.0.0.1"},
        "chromium": {"enable": False},
        "firefox": {"enable": False},
        "openstat": {"enable": False},
        "online": {"name": "Lampac NextGen", "spiderName": "Lampac NextGen", "version": True},
    }


def _version_of(bundle: Path) -> str:
    return (bundle / "VERSION").read_text(encoding="utf-8").strip()


def install(bundle: Path, root: Path) -> Path:
    """Lampac пишет кеш и журналы рядом с собой, а каталог установки может быть закрыт для записи."""
    target = root / _version_of(bundle)
    if (target / _READY_MARK).is_file():
        return target
    temporary = root / f"{target.name}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    shutil.rmtree(target, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle / "app", temporary / "app")
    shutil.copytree(bundle / "runtime", temporary / "runtime")
    (temporary / _READY_MARK).touch()
    os.replace(temporary, target)
    # Прежние версии после обновления приложения больше не нужны.
    for other in root.iterdir():
        if other != target and other.is_dir():
            shutil.rmtree(other, ignore_errors=True)
    return target


class _ProcessGroup:
    """Windows завершит процессы группы, даже если backend закроется аварийно."""

    def __init__(self, process_handle: int) -> None:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [
                ("user_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_set", ctypes.c_size_t),
                ("max_set", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", ctypes.c_ulonglong * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel = kernel
        self._job = kernel.CreateJobObjectW(None, None)
        if not self._job:
            raise OSError(ctypes.get_last_error(), "CreateJobObject")
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        extended_limit_information = 9
        if not kernel.SetInformationJobObject(self._job, extended_limit_information, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        if not kernel.AssignProcessToJobObject(self._job, process_handle):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")

    def close(self) -> None:
        if self._job:
            self._kernel.CloseHandle(self._job)
            self._job = None


class LampacServer:
    def __init__(self, on_state: Callable[[dict], None], bundle: Path | None = None, root: Path | None = None) -> None:
        self._on_state = on_state
        self._bundle = bundle if bundle is not None else bundle_dir()
        self._root = root if root is not None else settings.cache_dir() / "lampac"
        self._lock = threading.Lock()
        self._wanted = False
        self._state = "off"
        self._detail = ""
        self._process: subprocess.Popen | None = None
        self._group: _ProcessGroup | None = None
        self._url: str | None = None

    @property
    def available(self) -> bool:
        return (
            platform.system() == "Windows"
            and self._bundle is not None
            and (self._bundle / "app" / "Core.dll").is_file()
        )

    @property
    def base_url(self) -> str | None:
        """Адрес работающего сервера."""
        self._check_alive()
        return self._url if self._state == "running" else None

    def state(self) -> dict:
        self._check_alive()
        return {"state": self._state, "detail": self._detail, "available": self.available}

    def enable(self) -> None:
        self._wanted = True
        threading.Thread(target=self._start, daemon=True, name="lampac-start").start()

    def disable(self) -> None:
        self._wanted = False
        threading.Thread(target=self._stop_and_report, daemon=True, name="lampac-stop").start()

    def close(self) -> None:
        """Закрытие приложения: быстро и в этом потоке. Без блокировки: запуск мог занять её надолго."""
        self._wanted = False
        self._terminate()

    def _set(self, state: str, detail: str = "") -> None:
        self._state, self._detail = state, detail
        self._on_state(self.state_without_check())

    def state_without_check(self) -> dict:
        return {"state": self._state, "detail": self._detail, "available": self.available}

    def _check_alive(self) -> None:
        process = self._process
        if self._state == "running" and process is not None and process.poll() is not None:
            self._url = None
            self._set("error", f"Lampac неожиданно завершился, код {process.returncode}")

    def _start(self) -> None:
        with self._lock:
            if not self._wanted or (self._process is not None and self._process.poll() is None):
                return
            if not self.available:
                self._set("error", "Lampac не входит в эту сборку приложения")
                return
            self._set("starting")
            try:
                self._launch()
            except Exception as exc:
                print(f"lampac: запуск: {type(exc).__name__}: {exc}", file=sys.stderr)
                self._terminate()
                if self._wanted:
                    self._set("error", str(exc) or type(exc).__name__)
                else:
                    self._set("off")

    def _launch(self) -> None:
        target = install(self._bundle, self._root)
        app = target / "app"
        port = _free_port()
        (app / "init.conf").write_text(json.dumps(_config(port), ensure_ascii=False, indent=2), encoding="utf-8")
        runtime = target / "runtime"
        log_path = target / "server.log"
        environment = {**os.environ, "DOTNET_ROOT": str(runtime), "DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
        with log_path.open("wb") as log:
            self._process = subprocess.Popen(
                [str(runtime / "dotnet.exe"), "Core.dll"],
                cwd=app,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        try:
            self._group = _ProcessGroup(int(self._process._handle))
        except OSError as exc:
            print(f"lampac: группа процессов: {exc}", file=sys.stderr)

        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if not self._wanted:
                raise RuntimeError("Запуск отменён")
            code = self._process.poll()
            if code is not None:
                raise RuntimeError(f"Lampac завершился при запуске, код {code}: {_log_tail(log_path)}")
            try:
                if requests.get(f"{url}/version", params={"type": "hash"}, timeout=2).ok:
                    if not self._wanted:
                        raise RuntimeError("Запуск отменён")
                    self._url = url
                    self._set("running", f"Порт {port}")
                    return
            except requests.RequestException:
                pass
            time.sleep(_POLL_SECONDS)
        raise RuntimeError("Lampac не ответил вовремя")

    def _stop_and_report(self) -> None:
        with self._lock:
            if self._wanted:
                return
            self._terminate()
            self._set("off")

    def _terminate(self) -> None:
        self._url = None
        process, self._process = self._process, None
        group, self._group = self._group, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
        if group is not None:
            group.close()


def _log_tail(path: Path) -> str:
    try:
        return " ".join(path.read_text(encoding="utf-8", errors="replace").split())[-_LOG_TAIL_CHARS:]
    except OSError:
        return ""
