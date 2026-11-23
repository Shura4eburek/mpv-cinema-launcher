"""Вход через Google: OAuth 2.0 для настольных приложений (loopback-адрес и PKCE).

Долгоживущий refresh token хранится в системном хранилище (keyring), профиль для показа
без сети — в account.json, access token — только в памяти.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPES = "openid email profile https://www.googleapis.com/auth/drive.appdata"

KEYRING_SERVICE = "mpv-cinema-launcher"
KEYRING_NAME = "google-refresh-token"
CLIENT_FILE = "google_client.json"
ENV_CLIENT_ID = "MPV_CINEMA_GOOGLE_CLIENT_ID"
ENV_CLIENT_SECRET = "MPV_CINEMA_GOOGLE_CLIENT_SECRET"

SIGN_IN_TIMEOUT = 300.0
HTTP_TIMEOUT = 10
# Access token обновляется заранее, чтобы не истечь посреди запроса.
REFRESH_MARGIN = 60.0


class Unconfigured(Exception):
    """В сборке нет идентификатора Google-клиента."""


class SignedOut(Exception):
    """Пользователь не вошёл."""


class Offline(Exception):
    """Нет связи с Google."""


class Denied(Exception):
    """Пользователь отказал в доступе."""


class Cancelled(Exception):
    """Вход отменён из приложения."""


class Expired(Exception):
    """Сохранённый доступ отозван или недействителен."""


class GoogleError(Exception):
    """Google ответил неожиданно; текст — для пользователя."""


# --- клиент ---


@dataclass(frozen=True)
class Client:
    client_id: str
    client_secret: str = ""


def _client_dir() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[2] / "packaging"


def load_client(environ=os.environ, base: Path | None = None) -> Client | None:
    """Идентификатор клиента: переменные окружения, иначе google_client.json рядом с backend."""
    client_id = environ.get(ENV_CLIENT_ID, "").strip()
    if client_id:
        return Client(client_id, environ.get(ENV_CLIENT_SECRET, "").strip())
    try:
        raw = json.loads((Path(base) if base else _client_dir()).joinpath(CLIENT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # Файл, скачанный из Google Cloud Console, вкладывает поля в "installed".
    if isinstance(raw, dict) and isinstance(raw.get("installed"), dict):
        raw = raw["installed"]
    if not isinstance(raw, dict) or not isinstance(raw.get("client_id"), str) or not raw["client_id"].strip():
        return None
    secret = raw.get("client_secret")
    return Client(raw["client_id"].strip(), secret.strip() if isinstance(secret, str) else "")


# --- хранилища ---


class TokenStore:
    """Refresh token в системном хранилище; если оно недоступно — только в памяти."""

    def __init__(self, backend=None) -> None:
        self._backend = backend
        self._memory: str | None = None
        self.available = True

    def _keyring(self):
        if self._backend is None:
            import keyring

            self._backend = keyring
        return self._backend

    def _failed(self, action: str, exc: Exception) -> None:
        self.available = False
        print(f"google_auth: хранилище недоступно ({action}): {type(exc).__name__}", file=sys.stderr)

    def get(self) -> str | None:
        if self._memory is not None or not self.available:
            return self._memory
        try:
            self._memory = self._keyring().get_password(KEYRING_SERVICE, KEYRING_NAME)
        except Exception as exc:
            self._failed("чтение", exc)
        return self._memory

    def set(self, token: str) -> None:
        self._memory = token
        try:
            self._keyring().set_password(KEYRING_SERVICE, KEYRING_NAME, token)
            self.available = True
        except Exception as exc:
            self._failed("запись", exc)

    def delete(self) -> None:
        self._memory = None
        try:
            keyring = self._keyring()
            if keyring.get_password(KEYRING_SERVICE, KEYRING_NAME) is not None:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_NAME)
        except Exception as exc:
            print(f"google_auth: не удалось удалить токен: {type(exc).__name__}", file=sys.stderr)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class ProfileStore:
    """Имя, email и адрес аватара для показа без сети. Секретов здесь нет."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> dict | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            self.delete()
            return None
        if not isinstance(raw, dict) or not isinstance(raw.get("email"), str):
            self.delete()
            return None
        picture = raw.get("picture")
        return {
            "name": raw["name"] if isinstance(raw.get("name"), str) else "",
            "email": raw["email"],
            "picture": picture if isinstance(picture, str) else None,
        }

    def save(self, profile: dict, signed_in_at: float) -> None:
        data = {
            "name": profile.get("name") or "",
            "email": profile["email"],
            "picture": profile.get("picture"),
            "signed_in_at": signed_in_at,
        }
        _write_atomic(self.path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"google_auth: не удалось удалить профиль: {exc}", file=sys.stderr)


# --- PKCE и адрес входа ---


def new_verifier() -> str:
    return _token(64)


def new_state() -> str:
    return _token(24)


def _token(size: int) -> str:
    import secrets

    return secrets.token_urlsafe(size)


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def auth_url(client_id: str, redirect_uri: str, code_challenge: str, state: str) -> str:
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        # Без consent Google не выдаёт refresh token повторно.
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTH_URL}?{urlencode(query)}"


# --- приём ответа ---

_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>mpv cinema</title>
<style>body{{background:#000;color:#e2e2e2;font:16px system-ui,sans-serif;display:grid;place-items:center;height:100vh;margin:0}}
p{{background:#161618;border:1px solid #2c2c2f;border-radius:12px;padding:24px 32px}}</style></head>
<body><p>{text}</p></body></html>"""

PAGE_SIGNED_IN = "Вход выполнен. Вкладку можно закрыть и вернуться в приложение."
PAGE_DENIED = "Вход отменён. Вкладку можно закрыть."
PAGE_STALE = "Устаревшая попытка входа. Начните вход в приложении заново."


class Loopback:
    """Одноразовый HTTP-сервер на 127.0.0.1 для ответа Google."""

    def __init__(self, state: str) -> None:
        self._state = state
        self.result: tuple[str, str] | None = None
        loopback = self

        class Handler(http.server.BaseHTTPRequestHandler):
            # Браузер открывает соединения заранее и может ничего не прислать;
            # без таймаута такое соединение остановило бы проверку отмены и срока.
            timeout = 5

            def do_GET(self) -> None:  # noqa: N802
                status, text = loopback._answer(self.path)
                body = _PAGE.format(text=text).encode("utf-8") if text else b""
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:
                pass

        try:
            self._server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        except OSError as exc:
            raise GoogleError("Не удалось принять ответ Google на этом компьютере") from exc
        self._server.timeout = 0.2
        self.redirect_uri = f"http://127.0.0.1:{self._server.server_address[1]}/"

    def _answer(self, path: str) -> tuple[int, str | None]:
        parts = urlsplit(path)
        if parts.path != "/":
            return 404, None
        if self.result is not None:
            return 200, PAGE_SIGNED_IN if self.result[0] == "code" else PAGE_DENIED
        query = parse_qs(parts.query)
        state = query.get("state", [""])[0]
        if not hmac.compare_digest(state.encode("utf-8"), self._state.encode("utf-8")):
            return 400, PAGE_STALE
        code = query.get("code", [""])[0]
        if code:
            self.result = ("code", code)
            return 200, PAGE_SIGNED_IN
        error = query.get("error", [""])[0]
        if error:
            self.result = ("error", error)
            return 200, PAGE_DENIED
        return 400, PAGE_STALE

    def wait(self, cancel: threading.Event, deadline: float, clock: Callable[[], float] = time.monotonic) -> str:
        """Код авторизации; Denied, Cancelled или TimeoutError."""
        try:
            while self.result is None:
                if cancel.is_set():
                    raise Cancelled
                if clock() >= deadline:
                    raise TimeoutError
                self._server.handle_request()
        finally:
            self.close()
        kind, value = self.result
        if kind == "error":
            raise Denied(value)
        return value

    def close(self) -> None:
        self._server.server_close()


# --- запросы к Google ---


def _post(url: str, data: dict, http) -> requests.Response:
    try:
        return http.post(url, data=data, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise Offline from exc


def _token_response(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if response.status_code in (400, 401) and payload.get("error") == "invalid_grant":
        raise Expired
    if not response.ok or not isinstance(payload.get("access_token"), str):
        raise GoogleError(f"Google не выдал доступ (код {response.status_code})")
    return payload


def exchange_code(client: Client, code: str, verifier: str, redirect_uri: str, http=requests) -> dict:
    data = {
        "code": code,
        "client_id": client.client_id,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client.client_secret:
        data["client_secret"] = client.client_secret
    return _token_response(_post(TOKEN_URL, data, http))


def refresh(client: Client, refresh_token: str, http=requests) -> dict:
    data = {"refresh_token": refresh_token, "client_id": client.client_id, "grant_type": "refresh_token"}
    if client.client_secret:
        data["client_secret"] = client.client_secret
    return _token_response(_post(TOKEN_URL, data, http))


def fetch_profile(access_token: str, http=requests) -> dict:
    try:
        response = http.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise Offline from exc
    if response.status_code == 401:
        raise Expired
    try:
        payload = response.json() if response.ok else None
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("email"), str):
        raise GoogleError("Google не сообщил данные аккаунта")
    picture = payload.get("picture")
    name = payload.get("name")
    return {
        "name": name if isinstance(name, str) else "",
        "email": payload["email"],
        "picture": picture if isinstance(picture, str) and picture.startswith("https://") else None,
    }


def download_avatar(url: str | None, path: Path, http=requests) -> bool:
    """Скачать аватар; при неудаче старый файл удаляется, показываются инициалы."""
    try:
        if not url:
            raise ValueError("нет адреса")
        response = http.get(url, timeout=HTTP_TIMEOUT)
        if not response.ok or not response.content:
            raise ValueError(f"код {response.status_code}")
        _write_atomic(Path(path), response.content)
        return True
    except (requests.RequestException, ValueError, OSError) as exc:
        print(f"google_auth: аватар не загружен: {exc}", file=sys.stderr)
        Path(path).unlink(missing_ok=True)
        return False


def revoke(token: str, http=requests) -> bool:
    response = _post(REVOKE_URL, {"token": token}, http)
    # 400 — токен уже недействителен, отзывать нечего.
    return response.ok or response.status_code == 400


# --- аккаунт ---

MESSAGE_DENIED = "Вход отменён"
MESSAGE_TIMEOUT = "Время входа истекло"
MESSAGE_OFFLINE = "Нет связи с Google"
MESSAGE_EXPIRED = "Нужно войти заново"
MESSAGE_REVOKE_FAILED = "Не удалось отозвать доступ в Google"
MESSAGE_FAILED = "Не удалось войти"


class Account:
    """Состояние входа. Переходы — по data-model.md; каждое изменение уходит в on_change."""

    def __init__(
        self,
        client: Client | None,
        tokens: TokenStore,
        profiles: ProfileStore,
        avatar_path: Path,
        on_change: Callable[[dict], None],
        http=requests,
        open_browser: Callable[[str], bool] = webbrowser.open,
        clock: Callable[[], float] = time.time,
        timeout: float = SIGN_IN_TIMEOUT,
    ) -> None:
        self._client = client
        self._tokens = tokens
        self._profiles = profiles
        self._avatar_path = Path(avatar_path)
        self._on_change = on_change
        self._http = http
        self._open_browser = open_browser
        self._clock = clock
        self._timeout = timeout
        self._lock = threading.RLock()
        self._state = "unconfigured" if client is None else "signed_out"
        self._profile: dict | None = None
        self._message: str | None = None
        self._attempt: threading.Event | None = None
        self._access: tuple[str, float] | None = None
        self._restore_started = False
        self._restoring = False
        # Растёт при входе и выходе: результаты устаревших фоновых операций отбрасываются.
        self._generation = 0

    @property
    def state(self) -> str:
        return self._state

    def snapshot(self) -> dict:
        with self._lock:
            account = None
            if self._profile is not None:
                avatar = str(self._avatar_path) if self._avatar_path.is_file() else None
                account = {"name": self._profile.get("name") or "", "email": self._profile["email"], "avatar": avatar}
            return {
                "state": self._state,
                "account": account,
                "storage_warning": not self._tokens.available,
                "message": self._message,
            }

    def _set(self, state: str, message: str | None = None, generation: int | None = None) -> bool:
        with self._lock:
            if generation is not None and generation != self._generation:
                return False
            self._state = state
            self._message = message
            snapshot = self.snapshot()
        self._on_change(snapshot)
        return True

    def _forget(self) -> None:
        self._tokens.delete()
        self._profiles.delete()
        self._avatar_path.unlink(missing_ok=True)
        self._access = None
        self._profile = None

    # --- восстановление ---

    def start_restore(self) -> bool:
        """Первый вызов при сохранённом доступе переводит в restoring; True — нужно вызвать restore()."""
        with self._lock:
            if self._client is None or self._restoring:
                return False
            # Из offline восстановление повторяется при каждом запросе состояния.
            if self._state == "offline":
                self._restoring = True
                return True
            if self._restore_started:
                return False
            self._restore_started = True
            if self._state != "signed_out":
                return False
            token = self._tokens.get()
            profile = self._profiles.load()
            if not token:
                if profile is not None:
                    self._profiles.delete()
                return False
            self._profile = profile or {"name": "", "email": "", "picture": None}
            self._state = "restoring"
            self._restoring = True
            return True

    def restore(self) -> None:
        try:
            self._restore()
        finally:
            with self._lock:
                self._restoring = False

    def _restore(self) -> None:
        with self._lock:
            generation = self._generation
            token = self._tokens.get()
        if not token:
            self._set("signed_out", generation=generation)
            return
        try:
            access = self._refresh_access(token, generation)
            profile = fetch_profile(access, self._http)
        except Expired:
            with self._lock:
                if generation != self._generation:
                    return
                self._forget()
            self._set("expired", MESSAGE_EXPIRED, generation)
            return
        except Offline:
            self._set("offline", generation=generation)
            return
        except GoogleError as exc:
            # Сеть есть, но Google ответил ошибкой: сообщение вместо «нет связи».
            self._set("offline", str(exc), generation)
            return
        self._store_profile(profile, generation)
        self._set("signed_in", generation=generation)

    def _store_profile(self, profile: dict, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._profile = profile
            try:
                self._profiles.save(profile, self._clock())
            except OSError as exc:
                print(f"google_auth: профиль не сохранён: {exc}", file=sys.stderr)
        download_avatar(profile.get("picture"), self._avatar_path, self._http)
        with self._lock:
            # Пока аватар качался, пользователь вышел: файл не должен остаться.
            if generation != self._generation:
                self._avatar_path.unlink(missing_ok=True)

    def _refresh_access(self, refresh_token: str, generation: int) -> str:
        payload = refresh(self._client, refresh_token, self._http)
        with self._lock:
            if generation == self._generation:
                self._access = (payload["access_token"], self._clock() + _expires_in(payload))
        return payload["access_token"]

    # --- вход ---

    def sign_in(self) -> dict:
        with self._lock:
            if self._client is None:
                raise Unconfigured
            if self._attempt is not None or self._state in ("signed_in", "offline", "restoring"):
                return self.snapshot()
            cancel = threading.Event()
            self._attempt = cancel
        self._set("pending")
        threading.Thread(target=self._sign_in, args=(cancel,), name="google-sign-in", daemon=True).start()
        return self.snapshot()

    def cancel(self) -> dict:
        with self._lock:
            attempt, self._attempt = self._attempt, None
            if attempt is not None:
                attempt.set()
        if attempt is not None:
            self._set("signed_out")
        return self.snapshot()

    def _sign_in(self, cancel: threading.Event) -> None:
        message: str | None = None
        try:
            verifier, state = new_verifier(), new_state()
            server = Loopback(state)
            try:
                url = auth_url(self._client.client_id, server.redirect_uri, challenge(verifier), state)
                if not self._open_browser(url):
                    raise GoogleError("Не удалось открыть браузер")
                code = server.wait(cancel, time.monotonic() + self._timeout)
            finally:
                server.close()
            tokens = exchange_code(self._client, code, verifier, server.redirect_uri, self._http)
            profile = fetch_profile(tokens["access_token"], self._http)
            if not isinstance(tokens.get("refresh_token"), str):
                raise GoogleError("Google не выдал постоянный доступ")
            with self._lock:
                # Отмена и выход снимают попытку под этим же замком: либо они, либо вход.
                if self._attempt is not cancel or cancel.is_set():
                    raise Cancelled
                self._attempt = None
                self._generation += 1
                generation = self._generation
                self._tokens.set(tokens["refresh_token"])
                self._access = (tokens["access_token"], self._clock() + _expires_in(tokens))
            self._store_profile(profile, generation)
            self._set("signed_in", generation=generation)
            return
        except Cancelled:
            message = None
        except Denied:
            message = MESSAGE_DENIED
        except TimeoutError:
            message = MESSAGE_TIMEOUT
        except Offline:
            message = MESSAGE_OFFLINE
        except (GoogleError, Expired) as exc:
            message = str(exc) or MESSAGE_FAILED
        except Exception as exc:
            print(f"google_auth: {type(exc).__name__}: {exc}", file=sys.stderr)
            message = MESSAGE_FAILED
        with self._lock:
            current = self._attempt is cancel
            if current:
                self._attempt = None
        if current:
            self._set("signed_out", message)

    # --- выход ---

    def sign_out(self) -> dict:
        with self._lock:
            if self._attempt is not None:
                self._attempt.set()
                self._attempt = None
            if self._client is None:
                return self.snapshot()
            token = self._tokens.get()
            self._generation += 1
            self._forget()
        message = None
        if token:
            try:
                revoked = revoke(token, self._http)
            except (Offline, GoogleError):
                revoked = False
            if not revoked:
                message = MESSAGE_REVOKE_FAILED
        self._set("signed_out", message)
        return self.snapshot()

    # --- для синхронизации (этап 3) ---

    def drop_access_token(self) -> None:
        """Забыть access token: Google отверг его раньше срока, следующий запрос получит новый."""
        with self._lock:
            self._access = None

    def access_token(self) -> str:
        with self._lock:
            state, access, generation = self._state, self._access, self._generation
        if state == "expired":
            raise Expired
        if state not in ("signed_in", "offline", "restoring"):
            raise SignedOut
        if access is not None and access[1] - REFRESH_MARGIN > self._clock():
            return access[0]
        token = self._tokens.get()
        if not token:
            raise SignedOut
        try:
            value = self._refresh_access(token, generation)
        except Expired:
            with self._lock:
                if generation == self._generation:
                    self._forget()
            self._set("expired", MESSAGE_EXPIRED, generation)
            raise
        except (Offline, GoogleError):
            if state != "offline":
                self._set("offline", generation=generation)
            raise Offline
        if state != "signed_in":
            self._set("signed_in", generation=generation)
        return value


def _expires_in(payload: dict) -> float:
    value = payload.get("expires_in")
    return float(value) if isinstance(value, (int, float)) and value > 0 else 3600.0
