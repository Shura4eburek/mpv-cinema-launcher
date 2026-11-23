import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from mpv_launcher import google_auth as ga


# --- подмены ---


class FakeKeyring:
    def __init__(self, fail: bool = False) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.fail = fail

    def _check(self):
        if self.fail:
            raise RuntimeError("нет хранилища")

    def get_password(self, service, name):
        self._check()
        return self.values.get((service, name))

    def set_password(self, service, name, value):
        self._check()
        self.values[(service, name)] = value

    def delete_password(self, service, name):
        self._check()
        del self.values[(service, name)]


class Response:
    def __init__(self, status: int = 200, payload=None, content: bytes = b"") -> None:
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.content = content

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


class FakeHttp:
    """Ответы по адресу; исключение в списке ответов поднимается."""

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, dict]] = []

    def _reply(self, method, url, data):
        self.calls.append((method, url, data))
        answer = self.routes[url]
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer()
        return answer

    def post(self, url, data=None, timeout=None):
        return self._reply("POST", url, data)

    def get(self, url, headers=None, timeout=None):
        return self._reply("GET", url, headers)


TOKENS = {"access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 3600}
PROFILE = {"name": "Тест Тестов", "email": "user@example.com", "picture": "https://lh3.example/a.jpg"}
AVATAR = "https://lh3.example/a.jpg"


def http_ok(**extra):
    routes = {
        ga.TOKEN_URL: Response(200, TOKENS),
        ga.USERINFO_URL: Response(200, PROFILE),
        AVATAR: Response(200, content=b"jpeg"),
        ga.REVOKE_URL: Response(200, {}),
    }
    routes.update(extra)
    return FakeHttp(routes)


# --- клиент ---


def test_load_client_from_environment(tmp_path):
    env = {ga.ENV_CLIENT_ID: " id-1 ", ga.ENV_CLIENT_SECRET: "sec"}
    assert ga.load_client(env, tmp_path) == ga.Client("id-1", "sec")


def test_load_client_from_file_and_console_format(tmp_path):
    (tmp_path / ga.CLIENT_FILE).write_text(json.dumps({"installed": {"client_id": "id-2", "client_secret": "s2"}}))
    assert ga.load_client({}, tmp_path) == ga.Client("id-2", "s2")
    (tmp_path / ga.CLIENT_FILE).write_text(json.dumps({"client_id": "id-3"}))
    assert ga.load_client({}, tmp_path) == ga.Client("id-3", "")


@pytest.mark.parametrize("content", [None, "не json", "[]", '{"client_id": ""}'])
def test_load_client_missing_or_invalid(tmp_path, content):
    if content is not None:
        (tmp_path / ga.CLIENT_FILE).write_text(content)
    assert ga.load_client({}, tmp_path) is None


# --- хранилища ---


def test_token_store_uses_keyring():
    keyring = FakeKeyring()
    store = ga.TokenStore(keyring)
    store.set("tok")
    assert keyring.values[(ga.KEYRING_SERVICE, ga.KEYRING_NAME)] == "tok"
    assert ga.TokenStore(keyring).get() == "tok"
    store.delete()
    assert keyring.values == {}
    assert store.get() is None
    store.delete()  # удалять нечего — без ошибки


def test_token_store_without_keyring_keeps_token_in_memory():
    store = ga.TokenStore(FakeKeyring(fail=True))
    store.set("tok")
    assert store.available is False
    assert store.get() == "tok"
    store.delete()
    assert store.get() is None


def test_profile_store_roundtrip_and_broken_file(tmp_path):
    store = ga.ProfileStore(tmp_path / "account.json")
    assert store.load() is None
    store.save(PROFILE, 10.0)
    assert store.load() == PROFILE
    assert "ref" not in store.path.read_text(encoding="utf-8")
    store.path.write_text("{битый")
    assert store.load() is None
    assert not store.path.exists()


# --- PKCE ---


def test_challenge_matches_rfc7636_vector():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert ga.challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_auth_url_parameters():
    query = parse_qs(urlsplit(ga.auth_url("cid", "http://127.0.0.1:5000/", "chal", "st")).query)
    assert query["client_id"] == ["cid"]
    assert query["redirect_uri"] == ["http://127.0.0.1:5000/"]
    assert query["scope"] == [ga.SCOPES]
    assert query["code_challenge"] == ["chal"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["st"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]


def test_verifier_and_state_are_random():
    assert ga.new_verifier() != ga.new_verifier()
    assert 43 <= len(ga.new_verifier()) <= 128
    assert ga.new_state() != ga.new_state()


# --- loopback ---


def _wait_in_thread(server, cancel=None, timeout=5.0):
    result: dict = {}
    cancel = cancel or threading.Event()

    def run():
        try:
            result["code"] = server.wait(cancel, time.monotonic() + timeout)
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    return thread, result


def test_loopback_accepts_code_with_matching_state():
    server = ga.Loopback("good")
    thread, result = _wait_in_thread(server)
    assert requests.get(server.redirect_uri + "favicon.ico", timeout=5).status_code == 404
    stale = requests.get(server.redirect_uri + "?state=bad&code=x", timeout=5)
    assert stale.status_code == 400
    assert ga.PAGE_STALE in stale.text
    page = requests.get(server.redirect_uri + "?state=good&code=c1", timeout=5)
    thread.join(5)
    assert page.status_code == 200
    assert ga.PAGE_SIGNED_IN in page.text
    assert result == {"code": "c1"}


def test_loopback_denied():
    server = ga.Loopback("st")
    thread, result = _wait_in_thread(server)
    page = requests.get(server.redirect_uri + "?state=st&error=access_denied", timeout=5)
    thread.join(5)
    assert ga.PAGE_DENIED in page.text
    assert isinstance(result["error"], ga.Denied)


def test_loopback_cancel_and_timeout():
    cancel = threading.Event()
    thread, result = _wait_in_thread(ga.Loopback("st"), cancel)
    cancel.set()
    thread.join(5)
    assert isinstance(result["error"], ga.Cancelled)

    thread, result = _wait_in_thread(ga.Loopback("st"), timeout=0.3)
    thread.join(5)
    assert isinstance(result["error"], TimeoutError)


# --- запросы ---


def test_exchange_code_sends_verifier_and_secret():
    http = http_ok()
    assert ga.exchange_code(ga.Client("cid", "sec"), "code", "ver", "http://127.0.0.1:1/", http) == TOKENS
    _, url, data = http.calls[0]
    assert url == ga.TOKEN_URL
    assert data["code_verifier"] == "ver"
    assert data["client_secret"] == "sec"
    assert data["grant_type"] == "authorization_code"


def test_token_errors():
    client = ga.Client("cid")
    with pytest.raises(ga.Expired):
        ga.refresh(client, "r", http_ok(**{ga.TOKEN_URL: Response(400, {"error": "invalid_grant"})}))
    with pytest.raises(ga.Offline):
        ga.refresh(client, "r", http_ok(**{ga.TOKEN_URL: requests.ConnectionError()}))
    with pytest.raises(ga.GoogleError):
        ga.refresh(client, "r", http_ok(**{ga.TOKEN_URL: Response(500)}))


def test_fetch_profile_and_avatar(tmp_path):
    assert ga.fetch_profile("acc", http_ok()) == PROFILE
    path = tmp_path / "avatar.jpg"
    assert ga.download_avatar(AVATAR, path, http_ok())
    assert path.read_bytes() == b"jpeg"
    assert not ga.download_avatar(AVATAR, path, http_ok(**{AVATAR: Response(404)}))
    assert not path.exists()


# --- аккаунт ---


class Harness:
    def __init__(self, tmp_path, http=None, keyring=None, client=ga.Client("cid", "sec"), timeout=5.0):
        self.keyring = keyring or FakeKeyring()
        self.http = http or http_ok()
        self.events: list[dict] = []
        self.opened: list[str] = []
        self.profiles = ga.ProfileStore(tmp_path / "account.json")
        self.avatar = tmp_path / "avatar.jpg"
        self.account = ga.Account(
            client,
            ga.TokenStore(self.keyring),
            self.profiles,
            self.avatar,
            self.events.append,
            http=self.http,
            open_browser=self._open,
            timeout=timeout,
        )

    def _open(self, url):
        self.opened.append(url)
        return True

    def wait_state(self, *states, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.events and self.events[-1]["state"] in states:
                return self.events[-1]
            time.sleep(0.02)
        raise AssertionError(f"нет состояния {states}: {self.events}")

    def browser_reply(self, **query):
        url = self.opened[-1]
        params = parse_qs(urlsplit(url).query)
        redirect = params["redirect_uri"][0]
        query.setdefault("state", params["state"][0])
        return requests.get(redirect, params=query, timeout=5)


def _wait_opened(h):
    end = time.monotonic() + 5
    while not h.opened and time.monotonic() < end:
        time.sleep(0.02)
    assert h.opened


def test_unconfigured(tmp_path):
    h = Harness(tmp_path, client=None)
    assert h.account.snapshot()["state"] == "unconfigured"
    with pytest.raises(ga.Unconfigured):
        h.account.sign_in()


def test_sign_in_success(tmp_path):
    h = Harness(tmp_path)
    assert h.account.sign_in()["state"] == "pending"
    _wait_opened(h)
    assert h.account.sign_in()["state"] == "pending"  # вторая попытка не запускается
    assert len(h.opened) == 1
    h.browser_reply(code="c1")
    state = h.wait_state("signed_in")
    assert state["account"] == {"name": PROFILE["name"], "email": PROFILE["email"], "avatar": str(h.avatar)}
    assert h.keyring.values[(ga.KEYRING_SERVICE, ga.KEYRING_NAME)] == "ref-1"
    assert "ref-1" not in h.profiles.path.read_text(encoding="utf-8")
    assert "acc-1" not in h.profiles.path.read_text(encoding="utf-8")
    assert h.account.access_token() == "acc-1"


@pytest.mark.parametrize(
    ("reply", "routes", "message"),
    [
        ({"error": "access_denied"}, {}, ga.MESSAGE_DENIED),
        ({"code": "c1"}, {ga.TOKEN_URL: requests.ConnectionError()}, ga.MESSAGE_OFFLINE),
    ],
)
def test_sign_in_failures(tmp_path, reply, routes, message):
    h = Harness(tmp_path, http=http_ok(**routes))
    h.account.sign_in()
    _wait_opened(h)
    h.browser_reply(**reply)
    state = h.wait_state("signed_out")
    assert state["message"] == message
    assert h.keyring.values == {}


def test_sign_in_cancel_and_timeout(tmp_path):
    h = Harness(tmp_path)
    h.account.sign_in()
    _wait_opened(h)
    assert h.account.cancel()["state"] == "signed_out"
    assert h.events[-1]["message"] is None

    h = Harness(tmp_path, timeout=0.3)
    h.account.sign_in()
    assert h.wait_state("signed_out")["message"] == ga.MESSAGE_TIMEOUT


def test_storage_warning_when_keyring_missing(tmp_path):
    h = Harness(tmp_path, keyring=FakeKeyring(fail=True))
    h.account.sign_in()
    _wait_opened(h)
    h.browser_reply(code="c1")
    assert h.wait_state("signed_in")["storage_warning"] is True


def _signed_in(tmp_path, http):
    keyring = FakeKeyring()
    keyring.values[(ga.KEYRING_SERVICE, ga.KEYRING_NAME)] = "ref-1"
    h = Harness(tmp_path, http=http, keyring=keyring)
    h.profiles.save(PROFILE, 1.0)
    return h


def test_restore_success(tmp_path):
    h = _signed_in(tmp_path, http_ok())
    assert h.account.start_restore()
    assert h.account.snapshot()["state"] == "restoring"
    assert h.account.snapshot()["account"]["email"] == PROFILE["email"]
    assert not h.account.start_restore()
    h.account.restore()
    assert h.events[-1]["state"] == "signed_in"


def test_restore_expired_forgets_everything(tmp_path):
    h = _signed_in(tmp_path, http_ok(**{ga.TOKEN_URL: Response(400, {"error": "invalid_grant"})}))
    h.account.start_restore()
    h.account.restore()
    assert h.events[-1]["state"] == "expired"
    assert h.events[-1]["message"] == ga.MESSAGE_EXPIRED
    assert h.events[-1]["account"] is None
    assert h.keyring.values == {}
    assert not h.profiles.path.exists()


def test_restore_offline_keeps_account_then_recovers(tmp_path):
    http = http_ok(**{ga.TOKEN_URL: [requests.ConnectionError(), Response(200, TOKENS)]})
    h = _signed_in(tmp_path, http)
    h.account.start_restore()
    h.account.restore()
    assert h.events[-1]["state"] == "offline"
    assert h.events[-1]["account"]["email"] == PROFILE["email"]
    assert h.account.access_token() == "acc-1"
    assert h.events[-1]["state"] == "signed_in"


def test_restore_without_token_drops_stale_profile(tmp_path):
    h = Harness(tmp_path)
    h.profiles.save(PROFILE, 1.0)
    assert not h.account.start_restore()
    assert not h.profiles.path.exists()
    assert h.account.snapshot()["state"] == "signed_out"


def test_access_token_refreshes_before_expiry(tmp_path):
    now = [1000.0]
    http = http_ok(**{ga.TOKEN_URL: [Response(200, {**TOKENS, "expires_in": 100}), Response(200, {**TOKENS, "access_token": "acc-2"})]})
    h = _signed_in(tmp_path, http)
    h.account._clock = lambda: now[0]
    h.account.start_restore()
    h.account.restore()
    assert h.account.access_token() == "acc-1"
    now[0] += 50  # осталось меньше минуты
    assert h.account.access_token() == "acc-2"


def test_access_token_when_signed_out(tmp_path):
    with pytest.raises(ga.SignedOut):
        Harness(tmp_path).account.access_token()


def test_sign_out_revokes(tmp_path):
    h = _signed_in(tmp_path, http_ok())
    h.account.start_restore()
    h.account.restore()
    h.avatar.write_bytes(b"x")
    state = h.account.sign_out()
    assert state["state"] == "signed_out"
    assert state["message"] is None
    assert h.keyring.values == {}
    assert not h.profiles.path.exists()
    assert not h.avatar.exists()
    assert ("POST", ga.REVOKE_URL, {"token": "ref-1"}) in h.http.calls


def test_sign_out_offline_still_signs_out(tmp_path):
    h = _signed_in(tmp_path, http_ok(**{ga.REVOKE_URL: requests.ConnectionError()}))
    state = h.account.sign_out()
    assert state["state"] == "signed_out"
    assert state["message"] == ga.MESSAGE_REVOKE_FAILED
    assert h.keyring.values == {}


def _wait_sign_in_thread():
    end = time.monotonic() + 5
    while any(t.name == "google-sign-in" for t in threading.enumerate()) and time.monotonic() < end:
        time.sleep(0.02)


@pytest.mark.parametrize("action", ["sign_out", "cancel"])
def test_sign_out_or_cancel_during_exchange_wins(tmp_path, action):
    holder = {}

    def exchange():
        getattr(holder["account"], action)()
        return Response(200, TOKENS)

    h = Harness(tmp_path, http=http_ok(**{ga.TOKEN_URL: exchange}))
    holder["account"] = h.account
    h.account.sign_in()
    _wait_opened(h)
    h.browser_reply(code="c1")
    _wait_sign_in_thread()
    assert h.account.snapshot()["state"] == "signed_out"
    assert h.events[-1]["state"] == "signed_out"
    assert h.keyring.values == {}
    assert not h.profiles.path.exists()


def test_restore_google_error_shows_message_and_retries(tmp_path):
    http = http_ok(**{ga.TOKEN_URL: [Response(500), Response(200, TOKENS)]})
    h = _signed_in(tmp_path, http)
    h.account.start_restore()
    h.account.restore()
    assert h.events[-1]["state"] == "offline"
    assert "500" in h.events[-1]["message"]
    assert h.account.start_restore()  # из offline — повтор
    h.account.restore()
    assert h.events[-1]["state"] == "signed_in"
