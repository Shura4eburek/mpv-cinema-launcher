"""Синхронизация «Моего списка» через скрытую папку приложения в Google Drive.

Цикл: скачать облачный список → слить с локальным → записать локально → отправить. Слияние
по записям коммутативно (``watchlist.merge_items``), поэтому проигравшее гонку устройство
хранит свои записи и отправит их при следующей синхронизации.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests

from . import google_auth
from .watchlist import Watchlist, merge_items

FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FILE_NAME = "watchlist.json"
HTTP_TIMEOUT = 15
DEBOUNCE = 3.0
RETRY = 60.0
ATTEMPTS = 3
FORMAT_VERSION = 1

MESSAGE_OFFLINE = "Нет связи с Google Drive — изменения отправятся позже"
MESSAGE_AUTH = "Нужно войти заново, чтобы синхронизировать список"
MESSAGE_BAD_REMOTE = "Список в облаке не читается — синхронизация остановлена"
MESSAGE_REJECTED = "Google Drive отклонил запись: {}"
MESSAGE_FAILED = "Ошибка синхронизации"
MESSAGE_UNAUTHORIZED = "Google Drive не принял доступ — попробуйте синхронизировать позже"


class DriveOffline(Exception):
    """Нет сети, 429 или 5xx: повторить позже."""


class DriveUnauthorized(Exception):
    """401: access token недействителен."""


class DriveRejected(Exception):
    """Постоянная ошибка Drive (403, квота и прочие 4xx)."""


class BadRemote(Exception):
    """Облачный файл не читается или записан более новой версией формата."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


# --- Drive ---


class Drive:
    """Файл ``watchlist.json`` в ``appDataFolder`` через Drive API v3."""

    def __init__(self, token: Callable[[], str], http=requests) -> None:
        self._token = token
        self._http = http

    def _request(self, method: str, url: str, **kwargs):
        headers = {"Authorization": f"Bearer {self._token()}", **kwargs.pop("headers", {})}
        try:
            response = self._http.request(method, url, headers=headers, timeout=HTTP_TIMEOUT, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise DriveOffline(type(exc).__name__) from None
        status = response.status_code
        if status == 401:
            raise DriveUnauthorized
        if status == 429 or status >= 500:
            raise DriveOffline(f"HTTP {status}")
        if status >= 400:
            try:
                error = response.json()["error"]
                reason = error["message"]
                kinds = {e.get("reason") for e in error.get("errors", []) if isinstance(e, dict)}
            except (ValueError, KeyError, TypeError, AttributeError):
                reason, kinds = f"HTTP {status}", set()
            # Лимиты запросов Drive отдаёт как 403: это временно, повторить позже.
            if kinds & {"rateLimitExceeded", "userRateLimitExceeded"}:
                raise DriveOffline(reason)
            raise DriveRejected(reason)
        return response

    @staticmethod
    def _json(response) -> dict:
        try:
            data = response.json()
        except ValueError:
            raise DriveOffline("неверный ответ") from None
        if not isinstance(data, dict):
            raise DriveOffline("неверный ответ")
        return data

    def find(self) -> list[dict]:
        params = {
            "spaces": "appDataFolder",
            "q": f"name='{FILE_NAME}' and trashed=false",
            "fields": "files(id,modifiedTime)",
            "orderBy": "createdTime",
        }
        files = self._json(self._request("GET", FILES_URL, params=params)).get("files")
        if not isinstance(files, list):
            raise DriveOffline("неверный ответ")
        return [f for f in files if isinstance(f, dict) and isinstance(f.get("id"), str)]

    def download(self, file_id: str) -> bytes:
        return self._request("GET", f"{FILES_URL}/{file_id}", params={"alt": "media"}).content

    def modified(self, file_id: str) -> str | None:
        return self._json(self._request("GET", f"{FILES_URL}/{file_id}", params={"fields": "modifiedTime"})).get("modifiedTime")

    def create(self, body: bytes) -> dict:
        boundary = uuid.uuid4().hex
        meta = json.dumps({"name": FILE_NAME, "parents": ["appDataFolder"]})
        payload = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Type: application/json\r\n\r\n"
        ).encode() + body + f"\r\n--{boundary}--\r\n".encode()
        response = self._request(
            "POST", UPLOAD_URL,
            params={"uploadType": "multipart", "fields": "id,modifiedTime"},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            data=payload,
        )
        return self._json(response)

    def update(self, file_id: str, body: bytes) -> dict:
        response = self._request(
            "PATCH", f"{UPLOAD_URL}/{file_id}",
            params={"uploadType": "media", "fields": "id,modifiedTime"},
            headers={"Content-Type": "application/json"},
            data=body,
        )
        return self._json(response)

    def delete(self, file_id: str) -> None:
        self._request("DELETE", f"{FILES_URL}/{file_id}")


def encode(items: dict, now: str) -> bytes:
    return json.dumps({"version": FORMAT_VERSION, "items": items, "written_at": now}, ensure_ascii=False).encode("utf-8")


def decode(body: bytes) -> dict:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise BadRemote from None
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        raise BadRemote
    version = data.get("version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise BadRemote
    return data["items"]


# --- состояние на диске ---


class SyncStore:
    """``sync.json``: неотправленные изменения, время последней синхронизации, аккаунт."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> dict:
        default = {"pending": True, "last_synced_at": None, "email": None}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default
        if not isinstance(raw, dict):
            return default
        return {
            "pending": raw.get("pending") if isinstance(raw.get("pending"), bool) else True,
            "last_synced_at": raw.get("last_synced_at") if isinstance(raw.get("last_synced_at"), str) else None,
            "email": raw.get("email") if isinstance(raw.get("email"), str) else None,
        }

    def save(self, data: dict) -> None:
        try:
            _write_atomic(self.path, data)
        except OSError as exc:
            print(f"drive_sync: sync.json не записан: {type(exc).__name__}", file=sys.stderr)


# --- синхронизация ---


class Syncer:
    """Один фоновый поток; запросы во время цикла схлопываются в один следующий цикл."""

    def __init__(
        self,
        watchlist: Watchlist,
        drive: Drive,
        store: SyncStore,
        on_state: Callable[[dict], None],
        on_reloaded: Callable[[], None],
        drop_token: Callable[[], None] = lambda: None,
        clock: Callable[[], str] = _now,
        debounce: float = DEBOUNCE,
        retry: float = RETRY,
    ) -> None:
        self._watchlist = watchlist
        self._drive = drive
        self._store = store
        self._on_state = on_state
        self._on_reloaded = on_reloaded
        self._drop_token = drop_token
        self._clock = clock
        self._debounce = debounce
        self._retry = retry
        saved = store.load()
        self._lock = threading.Condition()
        self._enabled = False
        self._epoch = 0
        self._email: str | None = None
        self._state = "disabled"
        self._message: str | None = None
        self._pending: bool = saved["pending"]
        self._last_synced_at: str | None = saved["last_synced_at"]
        self._saved_email: str | None = saved["email"]
        self._changes = 0
        self._wanted = False
        self._stopped = False
        self._thread: threading.Thread | None = None
        self._debounce_timer: threading.Timer | None = None
        self._retry_timer: threading.Timer | None = None

    # --- снимок и события ---

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> dict:
        return {
            "state": self._state,
            "pending": self._pending,
            "last_synced_at": self._last_synced_at,
            "message": self._message,
        }

    def _notify(self, snapshot: dict) -> None:
        try:
            self._on_state(snapshot)
        except Exception as exc:
            print(f"drive_sync: on_state: {type(exc).__name__}: {exc}", file=sys.stderr)

    def _persist(self) -> None:
        self._store.save({"pending": self._pending, "last_synced_at": self._last_synced_at, "email": self._saved_email})

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    # --- управление ---

    def enable(self, email: str | None) -> None:
        """Включить синхронизацию для аккаунта; тот же аккаунт повторно — без нового цикла."""
        with self._lock:
            if self._stopped or (self._enabled and self._email == email):
                return
            self._enabled = True
            self._epoch += 1
            self._email = email
            self._saved_email = email
            self._state, self._message = "idle", None
            self._persist()
            self._ensure_thread()
            self._wanted = True
            self._lock.notify_all()
            snapshot = self._snapshot()
        self._notify(snapshot)

    def disable(self, auth_required: bool = False) -> None:
        """Остановить синхронизацию. Локальный и облачный списки не трогаются."""
        with self._lock:
            self._enabled = False
            self._epoch += 1
            self._email = None
            self._wanted = False
            self._cancel_timers()
            if auth_required:
                self._state, self._message = "auth_required", MESSAGE_AUTH
            else:
                self._state, self._message = "disabled", None
                self._saved_email = None
                self._persist()
            snapshot = self._snapshot()
        self._notify(snapshot)

    def request(self) -> bool:
        with self._lock:
            if not self._enabled or self._stopped:
                return False
            self._wanted = True
            self._lock.notify_all()
            return True

    def local_changed(self) -> None:
        """Локальное изменение списка: отметить и отправить после паузы."""
        with self._lock:
            self._changes += 1
            was_pending, self._pending = self._pending, True
            if not was_pending:
                self._persist()
            if self._enabled and not self._stopped:
                if self._debounce_timer is not None:
                    self._debounce_timer.cancel()
                self._debounce_timer = threading.Timer(self._debounce, self.request)
                self._debounce_timer.daemon = True
                self._debounce_timer.start()
            snapshot = self._snapshot() if not was_pending else None
        if snapshot is not None:
            self._notify(snapshot)

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._cancel_timers()
            self._lock.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=2)

    def _cancel_timers(self) -> None:
        for timer in (self._debounce_timer, self._retry_timer):
            if timer is not None:
                timer.cancel()
        self._debounce_timer = self._retry_timer = None

    def _ensure_thread(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="drive-sync", daemon=True)
            self._thread.start()

    # --- поток ---

    def _loop(self) -> None:
        while True:
            with self._lock:
                while not (self._wanted or self._stopped):
                    self._lock.wait()
                if self._stopped:
                    return
                self._wanted = False
                if not self._enabled:
                    continue
                epoch = self._epoch
            self._cycle(epoch)

    def _set(self, epoch: int, state: str, message: str | None = None) -> bool:
        with self._lock:
            if epoch != self._epoch:
                return False
            self._state, self._message = state, message
            snapshot = self._snapshot()
        self._notify(snapshot)
        return True

    def _cycle(self, epoch: int) -> None:
        if not self._set(epoch, "syncing"):
            return
        try:
            try:
                self._run_once(epoch)
            except DriveUnauthorized:
                self._drop_token()
                self._run_once(epoch)
        except (DriveOffline, google_auth.Offline) as exc:
            print(f"drive_sync: нет связи: {exc}", file=sys.stderr)
            if self._set(epoch, "offline", MESSAGE_OFFLINE):
                self._schedule_retry(epoch)
        except google_auth.Expired:
            self._set(epoch, "auth_required", MESSAGE_AUTH)
        except DriveUnauthorized:
            # Аккаунт при этом вошёл (токен обновился), поэтому вход заново не поможет:
            # ошибка с ручным повтором, а не «нужно войти».
            self._set(epoch, "error", MESSAGE_UNAUTHORIZED)
        except google_auth.SignedOut:
            self._set(epoch, "disabled")
        except BadRemote:
            self._set(epoch, "error", MESSAGE_BAD_REMOTE)
        except DriveRejected as exc:
            self._set(epoch, "error", MESSAGE_REJECTED.format(exc))
        except Exception as exc:
            print(f"drive_sync: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._set(epoch, "error", MESSAGE_FAILED)
        else:
            self._set(epoch, "idle")

    def _schedule_retry(self, epoch: int) -> None:
        """Без связи повтор нужен всегда: при запуске облачный список ещё не подтянут."""
        with self._lock:
            if epoch != self._epoch or self._stopped:
                return
            if self._retry_timer is not None:
                self._retry_timer.cancel()
            self._retry_timer = threading.Timer(self._retry, self.request)
            self._retry_timer.daemon = True
            self._retry_timer.start()

    def _run_once(self, epoch: int) -> None:
        for _attempt in range(ATTEMPTS):
            files = self._drive.find()
            remote: dict = {}
            for file in files:
                remote = merge_items(remote, decode(self._drive.download(file["id"])))
            with self._lock:
                if epoch != self._epoch:
                    return
                changes = self._changes
            if self._watchlist.merge(remote):
                self._on_reloaded()
            body = encode(self._watchlist.export_items(), self._clock())
            if files:
                target = files[0]
                if self._drive.modified(target["id"]) != target.get("modifiedTime"):
                    continue
                self._drive.update(target["id"], body)
                for extra in files[1:]:
                    self._drive.delete(extra["id"])
            else:
                self._drive.create(body)
            self._finish(epoch, changes)
            return
        raise DriveOffline("файл в облаке меняется слишком часто")

    def _finish(self, epoch: int, changes: int) -> None:
        with self._lock:
            if epoch != self._epoch:
                return
            if self._changes == changes:
                self._pending = False
            self._last_synced_at = self._clock()
            if self._retry_timer is not None:
                self._retry_timer.cancel()
                self._retry_timer = None
            self._persist()
