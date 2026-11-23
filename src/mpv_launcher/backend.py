"""Сервер протокола для окна Tauri: JSON Lines через stdin/stdout (contracts/backend-protocol.md)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlparse

import requests

from . import clipboard, kinogo, lampac, lampac_server, locate, machine, mirror_check, player_ipc, presets, runner, scraper, settings, shaders, sources, trailers, watchlist
from . import drive_sync, google_auth, imdb
from . import url as url_mod
from .cli import EXIT_NO_MPV, Options
from .jobs import Jobs
from .progress import NO_PROGRESS, Cancelled, Progress

_POSTER_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_MAX_POSTER_BYTES = 8 * 1024 * 1024
_STREAM_MAX_AGE_SECONDS = 30 * 60
_REFRESH_TIMEOUT_SECONDS = 45
_CANCEL_GRACE_SECONDS = 3
_EMBEDDED_STOP_SECONDS = 3
_PAGE_CACHE_SECONDS = 300
_MIRROR_CHECK_WORKERS = 8
_OPENING_TIMEOUT_SECONDS = 60
_READY_POLL_SECONDS = 0.2
_MPV_EXIT_INIT_ERROR = 1
_WATCHED_SHARE = 0.95
_PLAYBACK_FAILURES = {
    _MPV_EXIT_INIT_ERROR: "player_failed",
    runner.MPV_EXIT_LOAD_FAILED: "all_mirrors_failed",
    EXIT_NO_MPV: "no_mpv",
}


class ApiError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _http_url(value, field: str = "url") -> str:
    if isinstance(value, str) and url_mod.validate(value) and urlparse(value.strip()).scheme in ("http", "https"):
        return value.strip()
    raise ApiError("invalid_params", f"Недопустимый адрес: {field}")


def _text(params: dict, field: str) -> str:
    value = params.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ApiError("invalid_params", f"Не указано поле {field}")


def _optional_text(params: dict, field: str) -> str | None:
    value = params.get(field)
    return value.strip() or None if isinstance(value, str) else None


def _window_id(params: dict) -> int | None:
    """Идентификатор области видео. Встроенный плеер есть только на Windows."""
    value = params.get("wid")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApiError("invalid_params", "Недопустимая область видео")
    return value if platform.system() == "Windows" else None


def _at_most_1080p(quality) -> bool:
    match = re.match(r"(\d+)p", quality) if isinstance(quality, str) else None
    if match:
        return int(match[1]) <= 1080
    return isinstance(quality, str) and quality.lower() not in ("2k", "4k")


class _Opening:
    """Запуск плеера, который ещё можно отменить: до первого кадра фильма."""

    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self.process = None

    def attach(self, process) -> None:
        self.process = process
        if self.cancelled.is_set():
            process.terminate()

    def cancel(self) -> None:
        self.cancelled.set()
        if self.process is not None:
            self.process.terminate()


class _WatchProgress:
    """Позиция и длительность одного запуска: по ним решается, досмотрен ли тайтл."""

    def __init__(self) -> None:
        self.position: float | None = None
        self.duration: float | None = None
        self.eof = False
        self.started = False
        self.reported = False
        self.lock = threading.Lock()

    def watched(self) -> bool:
        # Обрыв потока mpv тоже видит как конец файла: без длительности конец засчитывается, с ней — только у почти досмотренного.
        if self.duration and self.position is not None:
            return self.position >= self.duration * _WATCHED_SHARE
        return self.eof

    def take_start(self) -> bool:
        """Видео действительно пошло: «Смотрю» ставится один раз за запуск."""
        with self.lock:
            if self.started:
                return False
            self.started = True
            return True

    def take(self) -> bool:
        """Досмотрено и ещё не сообщено: сообщение отправляется один раз за запуск."""
        with self.lock:
            if self.reported or not self.watched():
                return False
            self.reported = True
            return True


def _watch_params(raw) -> dict | None:
    """Параметр ``watch`` запуска (contracts/backend-watchlist.md); ``None`` — без списка."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ApiError("invalid_params", "Неверный параметр watch")
    try:
        watchlist.parse_title(raw.get("title"))
    except ValueError as exc:
        raise ApiError("invalid_params", str(exc)) from exc
    season, episode = raw.get("season"), raw.get("episode")
    for value in (season, episode):
        if value is not None and not (isinstance(value, str) and value.strip()):
            raise ApiError("invalid_params", "Неверная серия")
    if (season is None) != (episode is None) or not isinstance(raw.get("final", False), bool):
        raise ApiError("invalid_params", "Неверный параметр watch")
    return {"title": raw["title"], "season": season, "episode": episode, "final": raw.get("final", False)}


class Backend:
    def __init__(
        self,
        write: Callable[[str], None],
        driver_factory: Callable = scraper.create_headless_driver,
        settings_path: Path | None = None,
        poster_dir: Path | None = None,
        lampac_server_factory: Callable = lampac_server.LampacServer,
        watchlist_path: Path | None = None,
        account_factory: Callable | None = None,
        syncer_factory: Callable | None = None,
    ) -> None:
        self._write_raw = write
        self._write_lock = threading.Lock()
        self._jobs = Jobs()
        self._driver_factory = driver_factory
        self._driver = None
        self._closing = False
        self._stream_times: dict[str, float] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._openings: dict[str, _Opening] = {}
        self._embedded: _Opening | None = None
        self._embedded_position: float | None = None
        self._running: dict[str, Progress] = {}
        # (адрес, озвучка, сезон, серия) -> обновлённые ссылки
        self._refreshed: dict[tuple[str, str | None, str | None, str | None], dict[str, list[str]]] = {}
        # (вид, адрес, озвучка, источник) -> (когда получено, ответ)
        self._page_cache: dict[tuple, tuple[float, dict]] = {}
        self._settings_path = settings_path
        if watchlist_path is None and settings_path is not None:
            watchlist_path = Path(settings_path).parent / "watchlist.json"
        self._watchlist_path = Path(watchlist_path) if watchlist_path is not None else watchlist.default_path()
        self._watchlist = watchlist.Watchlist(watchlist_path, on_change=lambda: self._syncer.local_changed())
        self._lampac = lampac_server_factory(lambda state: self._emit("lampac_state", {"lampac": state}))
        self._poster_dir = Path(poster_dir) if poster_dir else settings.cache_dir() / "posters"
        self._syncer = (syncer_factory or self._default_syncer)(
            lambda state: self._emit("sync_changed", state),
            lambda: self._emit("watchlist_reloaded", {}),
        )
        self._account = (account_factory or self._default_account)(self._on_account)
        # (метод, где выполнять); None — сразу, в потоке чтения.
        self._methods: dict[str, tuple[Callable, Callable | None]] = {
            "status": (self._status, None),
            "cancel": (self._cancel, None),
            "device": (self._device, self._jobs.io),
            "search": (self._search, self._jobs.selenium),
            "movie": (self._movie, self._jobs.selenium),
            "translator_streams": (self._translator_streams, self._jobs.selenium),
            "episode": (self._episode, self._jobs.selenium),
            "poster": (self._poster, self._jobs.io),
            "play": (self._play, self._jobs.io),
            "play_clipboard": (self._play_clipboard, self._jobs.io),
            "player_stop": (self._player_stop, None),
            "copy_text": (self._copy_text, self._jobs.io),
            "trailer": (self._trailer, self._jobs.io),
            "mirror_check": (self._mirror_check, self._jobs.io),
            "open_trailer_search": (self._open_trailer_search, self._jobs.io),
            "lampac_state": (self._lampac_state, None),
            "lampac_sources": (self._lampac_sources, self._jobs.io),
            "lampac_variants": (self._lampac_variants, self._jobs.io),
            "get_settings": (self._get_settings, None),
            "set_settings": (self._set_settings, None),
            "watchlist_list": (self._watchlist_list, None),
            "watchlist_get": (self._watchlist_get, None),
            "watchlist_set_status": (self._watchlist_set_status, None),
            "watchlist_remove": (self._watchlist_remove, None),
            "watchlist_set_episode": (self._watchlist_set_episode, None),
            "watchlist_resolve": (self._watchlist_resolve, self._jobs.io),
            "account_get": (self._account_get, None),
            "account_sign_in": (self._account_sign_in, None),
            "account_cancel": (self._account_cancel, None),
            "account_sign_out": (self._account_sign_out, self._jobs.io),
            "sync_get": (self._sync_get, None),
            "sync_now": (self._sync_now, None),
        }

    def _default_account(self, on_change: Callable[[dict], None]) -> google_auth.Account:
        if self._settings_path is not None:
            account_path = Path(self._settings_path).parent / "account.json"
            avatar_path = self._poster_dir.parent / "avatar.jpg"
        else:
            account_path, avatar_path = settings.account_path(), settings.avatar_path()
        return google_auth.Account(
            google_auth.load_client(),
            google_auth.TokenStore(),
            google_auth.ProfileStore(account_path),
            avatar_path,
            on_change,
        )

    def _default_syncer(self, on_state: Callable[[dict], None], on_reloaded: Callable[[], None]) -> drive_sync.Syncer:
        return drive_sync.Syncer(
            self._watchlist,
            drive_sync.Drive(lambda: self._account.access_token()),
            drive_sync.SyncStore(self._watchlist_path.with_name("sync.json")),
            on_state,
            on_reloaded,
            drop_token=lambda: self._account.drop_access_token(),
        )

    # --- аккаунт Google ---

    def _on_account(self, state: dict) -> None:
        self._emit("account_changed", state)
        current = state.get("state")
        if current in ("signed_in", "offline"):
            self._syncer.enable((state.get("account") or {}).get("email"))
        elif current == "expired":
            self._syncer.disable(auth_required=True)
        elif current in ("signed_out", "unconfigured"):
            self._syncer.disable()

    # --- синхронизация ---

    def _sync_get(self, params: dict) -> dict:
        return self._syncer.snapshot()

    def _sync_now(self, params: dict) -> dict:
        if not self._syncer.request():
            raise ApiError("signed_out", "Нужно войти через Google")
        return self._syncer.snapshot()

    def _account_get(self, params: dict) -> dict:
        restore = self._account.start_restore()
        snapshot = self._account.snapshot()
        if restore:
            self._jobs.io(self._account.restore)
        return snapshot

    def _account_sign_in(self, params: dict) -> dict:
        try:
            return self._account.sign_in()
        except google_auth.Unconfigured:
            raise ApiError("unconfigured", "Вход через Google не настроен в этой сборке") from None

    def _account_cancel(self, params: dict) -> dict:
        return self._account.cancel()

    def _account_sign_out(self, params: dict) -> dict:
        return self._account.sign_out()

    def access_token(self) -> str:
        """Действительный access token Google для синхронизации (этап 3)."""
        try:
            return self._account.access_token()
        except google_auth.SignedOut:
            raise ApiError("signed_out", "Нужно войти через Google") from None
        except google_auth.Expired:
            raise ApiError("expired", google_auth.MESSAGE_EXPIRED) from None
        except google_auth.Offline:
            raise ApiError("offline", google_auth.MESSAGE_OFFLINE) from None

    # --- протокол ---

    def _send(self, message: dict) -> None:
        text = json.dumps(message, ensure_ascii=False)
        with self._write_lock:
            self._write_raw(text)

    def _emit(self, event: str, data: dict) -> None:
        self._send({"event": event, "data": data})

    def handle_line(self, line: str) -> None:
        """Обработать строку запроса. Никогда не завершает процесс из-за плохих данных."""
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError
        except ValueError:
            self._send({"id": None, "error": {"code": "invalid_params", "message": "Неверное сообщение"}})
            return

        request_id = message.get("id")
        params = message.get("params")
        entry = self._methods.get(message.get("method"))
        if entry is None or not isinstance(params, (dict, type(None))):
            self._send({"id": request_id, "error": {"code": "invalid_params", "message": "Неверный запрос"}})
            return

        handler, submit = entry
        task = lambda: self._run(request_id, handler, params or {})
        if submit is None:
            task()
        else:
            submit(task)

    def _run(self, request_id, handler: Callable, params: dict) -> None:
        try:
            self._send({"id": request_id, "result": handler(params)})
        except ApiError as exc:
            self._send({"id": request_id, "error": {"code": exc.code, "message": exc.message}})
        except Exception as exc:
            print(f"backend: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._send({"id": request_id, "error": {"code": "internal", "message": "Внутренняя ошибка"}})

    # --- драйвер ---

    def _driver_is_alive(self) -> bool:
        try:
            _ = self._driver.current_url
            return True
        except Exception as exc:
            print(f"backend: сессия Chrome потеряна: {type(exc).__name__}", file=sys.stderr)
            return False

    def _get_driver(self):
        if self._closing:
            raise ApiError("internal", "Приложение закрывается")
        if self._driver is not None and not self._driver_is_alive():
            self._quit_driver()
        if self._driver is None:
            self._driver = self._driver_factory()
        if self._driver is None:
            raise ApiError("internal", "Не удалось запустить Chrome")
        return self._driver

    def _quit_driver(self) -> None:
        driver, self._driver = self._driver, None
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                print(f"backend: ошибка закрытия драйвера: {exc}", file=sys.stderr)

    def close(self) -> None:
        """Завершить Chrome и не ждать просмотр в отдельном окне: такой mpv продолжает играть."""
        # Не через очередь: операция Selenium может идти ещё долго, а Chrome не должен остаться.
        self._closing = True
        # Отдельный mpv переживает закрытие окна, а встроенному негде показывать видео.
        self._stop_embedded(wait=False)
        self._jobs.shutdown()
        self._syncer.stop()
        self._lampac.close()
        self._quit_driver()

    def apply_lampac_setting(self) -> None:
        """Выключенный Lampac не запускает процессов и не обращается в сеть."""
        if settings.load(self._settings_path)["lampac_enabled"]:
            self._lampac.enable()
        else:
            self._lampac.disable()

    def install_shaders(self) -> None:
        """Скачать шейдеры в фоне и сообщить о результате."""

        def task():
            try:
                ready = bool(shaders.ensure_shaders_installed())
            except Exception as exc:
                print(f"backend: шейдеры: {exc}", file=sys.stderr)
                ready = False
            self._emit("upscale_ready", {"ready": ready})

        self._jobs.io(task)

    # --- методы ---

    # --- ход загрузки и отмена ---

    @contextmanager
    def _tracked(self, params: dict) -> Iterator[Progress]:
        """Шаги операции для интерфейса; отмена превращается в код ``cancelled``."""
        load_id = _optional_text(params, "progress_id")
        if load_id is None:
            yield NO_PROGRESS
            return

        flag = self._cancels.setdefault(load_id, threading.Event())
        progress = Progress(
            emit=lambda step, state: self._emit("load_progress", {"id": load_id, "step": step, "state": state}),
            is_cancelled=flag.is_set,
        )
        self._running[load_id] = progress
        try:
            yield progress
        except Cancelled as exc:
            raise ApiError("cancelled", "Загрузка отменена") from exc
        except Exception:
            # Закрытый при отмене Chrome вызывает любые ошибки, но причина здесь — отмена.
            if flag.is_set():
                raise ApiError("cancelled", "Загрузка отменена") from None
            raise
        finally:
            self._running.pop(load_id, None)
            self._cancels.pop(load_id, None)

    def _cancel(self, params: dict) -> dict:
        load_id = _text(params, "id")
        self._cancels.setdefault(load_id, threading.Event()).set()
        opening = self._openings.get(load_id)
        if opening is not None:
            opening.cancel()

        def stop_stuck_browser():
            # driver.get нельзя прервать иначе; следующая загрузка запустит новый Chrome.
            # Задача в очереди или без работы в браузере не должна закрывать чужой Chrome.
            progress = self._running.get(load_id)
            if progress is not None and progress.in_browser_step and not self._closing:
                print("backend: операция не прервалась, Chrome закрывается", file=sys.stderr)
                self._quit_driver()

        timer = threading.Timer(_CANCEL_GRACE_SECONDS, stop_stuck_browser)
        timer.daemon = True
        timer.start()
        return {"ok": True}

    def _device(self, _params: dict) -> dict:
        return {**machine.detect_device(), "vsr": machine.vsr_available()}

    def _status(self, _params: dict) -> dict:
        return {
            "mpv_found": locate.find_mpv() is not None,
            "upscale_ready": shaders.are_shaders_installed(),
        }

    def _search(self, params: dict) -> list[dict]:
        query = _text(params, "query")
        try:
            results = sources.search(query, self._kinogo_url(), get_driver=self._get_driver)
        except scraper.SiteUnavailable as exc:
            raise ApiError("network", "Сайт недоступен") from exc
        return [asdict(item) for item in results]

    def _cached(self, key: tuple) -> dict | None:
        entry = self._page_cache.get(key)
        if entry is None or time.monotonic() - entry[0] >= _PAGE_CACHE_SECONDS:
            return None
        # Интерфейс получает ссылки этого времени: по нему при запуске решается, не пора ли их обновить.
        if key[1] in self._stream_times:
            self._stream_times[key[1]] = entry[0]
        return entry[1]

    def _remember(self, key: tuple, result: dict) -> None:
        now = time.monotonic()
        self._page_cache = {k: v for k, v in self._page_cache.items() if now - v[0] < _PAGE_CACHE_SECONDS}
        self._page_cache[key] = (now, result)

    def _forget_page(self, url: str) -> None:
        # Страница, открытая вместо KinoGo с HDRezka, лежит в кеше под адресом KinoGo.
        self._page_cache = {k: v for k, v in self._page_cache.items() if k[1] != url and v[1].get("url") != url}

    def _movie(self, params: dict) -> dict:
        url = _http_url(params.get("url"))
        key = ("movie", url, _optional_text(params, "voice"), _optional_text(params, "source"))
        with self._tracked(params) as progress:
            progress.check()
            cached = self._cached(key)
            if cached is not None:
                return cached
            try:
                details = sources.open_movie(
                    url,
                    None,
                    self._kinogo_url(),
                    get_driver=self._get_driver,
                    source=_optional_text(params, "source"),
                    title=_optional_text(params, "title"),
                    voice=_optional_text(params, "voice"),
                    progress=progress,
                )
            except scraper.SiteUnavailable as exc:
                raise ApiError("network", "Страница фильма не загрузилась") from exc
        # Страница проверки или ошибки зеркала: это сбой сайта, а не фильм без видео.
        if not (details.translators or details.streams or details.description or details.alternatives):
            raise ApiError("network", "Страница фильма не загрузилась")
        if details.source == "kinogo" and details.streams:
            self._mark_fresh(url)
        result = asdict(details)
        # Страницу без видео не запоминаем: это мог быть разовый сбой сайта.
        if details.streams or details.translators or details.alternatives:
            self._remember(key, result)
        return result

    def _mark_fresh(self, url: str) -> None:
        """Интерфейс получил новые ссылки: ссылки, обновлённые при запуске, больше не нужны."""
        self._stream_times[url] = time.monotonic()
        for key in [k for k in self._refreshed if k[0] == url]:
            del self._refreshed[key]

    def _kinogo_voice_streams(self, url: str, voice: str, progress: Progress = NO_PROGRESS) -> dict:
        return self._kinogo_details(url, progress, voice=voice).streams

    def _kinogo_details(self, url: str, progress: Progress, **selection) -> scraper.MovieDetails:
        try:
            details = kinogo.fetch_movie(
                url, None, self._kinogo_url(), progress=progress, get_driver=self._get_driver, **selection
            )
        except kinogo.NoVideo as exc:
            raise ApiError("no_streams", "Для этой озвучки видео не найдено") from exc
        except scraper.SiteUnavailable as exc:
            raise ApiError("network", "Страница фильма не загрузилась") from exc
        self._mark_fresh(url)
        return details

    def _kinogo_url(self) -> str:
        return settings.load(self._settings_path)["kinogo_url"]

    def _refreshed_urls(
        self,
        movie_url: str,
        quality,
        voice,
        urls: list[str],
        progress: Progress = NO_PROGRESS,
        season: str | None = None,
        episode: str | None = None,
    ) -> list[str]:
        """Ссылки KinoGo временные: получить новые, если старые устарели или уже не сработали."""
        key = (movie_url, voice, season, episode)
        selection = {"season": season, "episode": episode} if season else {}
        captured = self._stream_times.get(movie_url)
        if captured is not None and time.monotonic() - captured < _STREAM_MAX_AGE_SECONDS:
            # Интерфейс не знает об обновлённых ссылках и присылает старые.
            return self._refreshed.get(key, {}).get(quality) or urls

        def refresh():
            return kinogo.fetch_movie(
                movie_url, None, self._kinogo_url(), voice=voice, progress=progress, get_driver=self._get_driver, **selection
            )

        try:
            details = self._jobs.selenium(refresh).result(timeout=_REFRESH_TIMEOUT_SECONDS)
        except Cancelled:
            raise
        except Exception as exc:
            # Закрытый при отмене Chrome выглядит как обычный сбой: фильм запускать нельзя.
            progress.check()
            print(f"backend: не удалось обновить ссылку: {type(exc).__name__}", file=sys.stderr)
            return urls
        # Заголовок уже назван: другая серия под ним хуже, чем честная ошибка.
        if details.series is not None and details.series.moved:
            raise ApiError("no_streams", "Для этой серии видео не найдено")
        streams = details.streams
        self._mark_fresh(movie_url)
        self._refreshed[key] = streams
        # Выбранный вариант мог исчезнуть: старая ссылка уже истекла, поэтому берём лучший из новых.
        return streams.get(quality) or streams.get(sources.best_quality(streams)) or urls

    def _translator_streams(self, params: dict) -> dict:
        url = _http_url(params.get("url"))
        translator_id = _text(params, "translator_id")
        key = ("voice", url, translator_id, _optional_text(params, "source"))
        with self._tracked(params) as progress:
            progress.check()
            cached = self._cached(key)
            if cached is not None:
                return cached
            if sources.is_kinogo(url, self._kinogo_url(), params.get("source")):
                streams = self._kinogo_voice_streams(url, translator_id, progress)
                self._remember(key, streams)
                return streams
            with progress.step("voice", browser=True):
                driver = self._get_driver()
                # Запрос озвучки выполняется в контексте страницы фильма, а драйвер мог уйти на поиск.
                if driver.current_url != url:
                    scraper.fetch_movie_details(url, driver=driver)
                streams = scraper.fetch_translator_streams(url, translator_id, driver)
        if not streams:
            raise ApiError("no_streams", "Для этой озвучки видео не найдено")
        self._remember(key, streams)
        return streams

    def _episode(self, params: dict) -> dict:
        """Потоки серии вместе со списками: наборы сезонов, серий и озвучек зависят от выбора."""
        url = _http_url(params.get("url"))
        season = _text(params, "season")
        episode = _optional_text(params, "episode")
        voice = _optional_text(params, "translator_id")
        source = _optional_text(params, "source")
        # Озвучка, которую зритель не выбирал сейчас, может отсутствовать в новом сезоне: это не ошибка.
        voice_optional = params.get("voice_optional") is True
        key = ("episode", url, voice, season, episode, source, voice_optional)
        with self._tracked(params) as progress:
            progress.check()
            cached = self._cached(key)
            if cached is not None:
                return cached
            if sources.is_kinogo(url, self._kinogo_url(), source):
                details = self._kinogo_details(url, progress, voice=voice, season=season, episode=episode, strict=not voice_optional)
            else:
                try:
                    with progress.step("episode", browser=True):
                        driver = self._get_driver()
                        # Запрос серии выполняется в контексте страницы, а драйвер мог уйти на поиск.
                        if driver.current_url != url:
                            scraper.fetch_movie_details(url, driver=driver)
                        details = scraper.fetch_episode(url, driver, voice, season, episode)
                except scraper.SiteUnavailable as exc:
                    raise ApiError("network", "Страница фильма не загрузилась") from exc
        if not details.streams:
            raise ApiError("no_streams", "Для этой серии видео не найдено")
        result = {
            "streams": details.streams,
            "translators": [asdict(item) for item in details.translators],
            "active_translator_id": details.active_translator_id,
            "series": asdict(details.series) if details.series else None,
        }
        self._remember(key, result)
        return result

    def _poster(self, params: dict) -> dict:
        url = _http_url(params.get("url"))
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        for cached_suffix in _POSTER_TYPES.values():
            cached = self._poster_dir / f"{key}{cached_suffix}"
            if cached.is_file():
                return {"path": str(cached)}

        try:
            response = requests.get(url, headers=scraper.get_random_headers(), timeout=10)
        except requests.RequestException as exc:
            raise ApiError("network", "Постер не загрузился") from exc

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        suffix = _POSTER_TYPES.get(content_type)
        if response.status_code != 200 or suffix is None or len(response.content) > _MAX_POSTER_BYTES:
            raise ApiError("network", "Постер не загрузился")

        self._poster_dir.mkdir(parents=True, exist_ok=True)
        target = self._poster_dir / f"{key}{suffix}"
        tmp = target.with_suffix(f"{suffix}.{threading.get_ident()}.tmp")
        tmp.write_bytes(response.content)
        os.replace(tmp, target)
        return {"path": str(target)}

    def _stop_embedded(self, wait: bool = True) -> None:
        """В окне работает один встроенный плеер: новый запуск и закрытие завершают прежний."""
        opening, self._embedded = self._embedded, None
        if opening is None:
            return
        opening.cancel()
        if wait and opening.process is not None:
            try:
                opening.process.wait(timeout=_EMBEDDED_STOP_SECONDS)
            except Exception as exc:
                print(f"backend: встроенный плеер не закрылся: {type(exc).__name__}", file=sys.stderr)

    def _remember_position(self, position: float) -> None:
        self._embedded_position = position

    def _player_stop(self, _params: dict) -> dict:
        self._stop_embedded(wait=False)
        return {"ok": True}

    def _start_playback(
        self,
        urls: list[str],
        title: str | None,
        referer: str | None = None,
        site_referer: bool = True,
        movie_url: str | None = None,
        load_id: str | None = None,
        allow_vsr: bool = False,
        wid: int | None = None,
        resume: bool = False,
        watch_info: dict | None = None,
    ) -> dict:
        mpv_path = locate.find_mpv()
        if mpv_path is None:
            raise ApiError("no_mpv", "Плеер mpv не установлен")

        # Ссылка могла обновляться, пока приложение закрывалось: окна для видео уже нет.
        if self._closing:
            raise ApiError("internal", "Приложение закрывается")
        if wid is not None:
            self._stop_embedded()
        start = self._embedded_position if wid is not None and resume else None
        self._embedded_position = None
        opening = self._openings.get(load_id) if load_id else None
        if opening is not None and opening.cancelled.is_set():
            raise ApiError("cancelled", "Загрузка отменена")
        if wid is not None:
            # Встроенный плеер всегда можно остановить, даже без хода загрузки.
            opening = opening or _Opening()
            self._embedded = opening
        ready_file = None
        if opening is not None:
            handle, ready_file = tempfile.mkstemp(prefix="mpv-cinema-ready-")
            os.close(handle)
            os.unlink(ready_file)
        ids = {"id": load_id} if load_id else {}
        # Канал управления: без него конец просмотра не отследить.
        ipc_server = player_ipc.server_path(uuid.uuid4().hex) if wid is not None or watch_info is not None else None
        progress_of_watch = _WatchProgress()

        saved = settings.load(self._settings_path)
        profile = machine.preset_profile(saved["preset"])
        options = Options(
            url=urls[0],
            title=title,
            profile=profile,
            content=saved["content"],
            interpolation=saved["interpolation"],
            referer=referer or (f"{scraper.get_base_url()}/" if site_referer else None),
            ready_file=ready_file,
            wid=wid,
            ipc_server=ipc_server,
            start=start,
            # На аниме VSR не проверялся, там остаётся Anime4K.
            vsr=(
                allow_vsr
                and profile == "high"
                and saved["content"] == "film"
                and machine.vsr_available()
                and machine.mpv_supports_vsr(mpv_path)
            ),
        )
        plan = presets.build_plan(options, profile)
        finished = threading.Event()

        # Без интерфейса плеера сигнала не будет: ждать его незачем.
        signal_wired = any(arg.endswith(f"cinema-ready_file={ready_file}") for arg in plan.mpv_args)

        def report_when_playing():
            # Без сигнала от плеера экран всё равно снимается: фильм не должен быть закрыт им навсегда.
            deadline = time.monotonic() + (_OPENING_TIMEOUT_SECONDS if signal_wired else 0)
            while time.monotonic() < deadline and not finished.is_set() and not os.path.exists(ready_file):
                time.sleep(_READY_POLL_SECONDS)
            if not finished.is_set():
                self._openings.pop(load_id, None)
                self._emit("playback_started", ids)

        def on_fallback(url: str) -> None:
            if kinogo.is_player_server(url):
                self._emit("playback_fallback", {"code": "lower_quality"})

        def watch():
            try:
                code = runner.run_with_fallback(
                    plan,
                    urls[1:],
                    on_fallback=on_fallback,
                    on_process=opening.attach if opening else None,
                    should_stop=opening.cancelled.is_set if opening else None,
                )
            except Exception as exc:
                print(f"backend: запуск mpv: {exc}", file=sys.stderr)
                self._emit("playback_failed", {"code": "internal", **ids})
                return
            finally:
                finished.set()
                if self._embedded is opening:
                    self._embedded = None
                self._openings.pop(load_id, None)
                self._cancels.pop(load_id, None)
                if ready_file:
                    Path(ready_file).unlink(missing_ok=True)
                player_ipc.remove_server(ipc_server)
            # Отменённый запуск закрыт намеренно: это не сбой воспроизведения.
            if opening is not None and opening.cancelled.is_set():
                # Встроенный плеер закрывают и после досмотра: конец просмотра засчитывается.
                self._report_watched(watch_info, progress_of_watch)
                self._emit("playback_finished", {"code": code, **ids})
                return
            failure = _PLAYBACK_FAILURES.get(code)
            if not failure:
                self._report_watched(watch_info, progress_of_watch)
            if failure:
                if movie_url:
                    self._stream_times.pop(movie_url, None)  # «Повторить» получит новую ссылку
                    self._forget_page(movie_url)
                self._emit("playback_failed", {"code": failure, **ids})
            else:
                self._emit("playback_finished", {"code": code, **ids})

        self._jobs.play(watch)
        if ipc_server is not None:

            def on_position(position: float) -> None:
                progress_of_watch.position = position
                if wid is not None:
                    self._remember_position(position)
                if watch_info is not None and position > 0 and progress_of_watch.take_start():
                    self._watch_started(watch_info)

            def on_duration(duration: float) -> None:
                progress_of_watch.duration = duration

            def on_eof() -> None:
                # При --keep-open встроенный плеер не закрывается в конце: засчитать сразу.
                progress_of_watch.eof = True
                self._report_watched(watch_info, progress_of_watch)

            threading.Thread(
                target=player_ipc.watch,
                args=(
                    ipc_server,
                    lambda on: self._emit("player_fullscreen", {"on": on, **ids}),
                    on_position,
                    finished.is_set,
                ),
                kwargs={"on_duration": on_duration, "on_eof": on_eof},
                daemon=True,
            ).start()
        if opening is not None:
            threading.Thread(target=report_when_playing, daemon=True).start()
        return {"started": True}

    @contextmanager
    def _opening(self, params: dict) -> Iterator[str | None]:
        """Регистрирует запуск плеера: сбой до старта mpv снимает регистрацию."""
        load_id = _optional_text(params, "progress_id")
        if load_id:
            opening = _Opening()
            # Отмена могла прийти, пока запуск ждал своей очереди.
            early = self._cancels.get(load_id)
            if early is not None and early.is_set():
                opening.cancelled.set()
            self._openings[load_id] = opening
        try:
            yield load_id
        except Exception:
            self._openings.pop(load_id, None)
            self._cancels.pop(load_id, None)
            raise

    def _play(self, params: dict) -> dict:
        urls = params.get("urls")
        if not isinstance(urls, list) or not urls:
            raise ApiError("invalid_params", "Нет адресов потока")
        clean = [_http_url(u, "urls") for u in urls]
        title = params.get("title")
        referer = _http_url(params["referer"], "referer") if params.get("referer") else None
        movie_url = _http_url(params["movie_url"], "movie_url") if params.get("movie_url") else None
        wid = _window_id(params)
        try:
            watch = _watch_params(params.get("watch"))
        except ApiError as exc:
            # Список — дополнение к просмотру: неверные данные для него не должны мешать запуску.
            print(f"backend: watch пропущен: {exc.message}", file=sys.stderr)
            watch = None
        with self._opening(params) as load_id:
            if movie_url and sources.is_kinogo(movie_url, self._kinogo_url(), params.get("source")):
                voice = _optional_text(params, "voice")
                with self._tracked(params) as progress:
                    clean = self._refreshed_urls(
                        movie_url,
                        params.get("quality"),
                        voice,
                        clean,
                        progress,
                        _optional_text(params, "season"),
                        _optional_text(params, "episode"),
                    )
            return self._start_playback(
                clean,
                watch_info=watch,
                title=title if isinstance(title, str) and title.strip() else None,
                referer=referer,
                # Адрес HDRezka нужен только её потокам.
                site_referer=params.get("source") != "lampac",
                movie_url=movie_url,
                load_id=load_id,
                # Только для фильмов до 1080p: четырёхкратный объём 4K фильтру не нужен.
                allow_vsr=movie_url is not None and _at_most_1080p(params.get("quality")),
                wid=wid,
                resume=params.get("resume") is True,
            )

    def _play_clipboard(self, params: dict) -> dict:
        with self._opening(params) as load_id:
            raw = clipboard.read()
            if not url_mod.validate(raw):
                raise ApiError("no_url", "В буфере обмена нет ссылки")
            return self._start_playback([raw.strip()], None, load_id=load_id)

    def _copy_text(self, params: dict) -> dict:
        clipboard.write(_text(params, "text"))
        return {"ok": True}

    def _mirror_check(self, params: dict) -> dict:
        query = _text(params, "query")
        check_id = _text(params, "id")
        sites = mirror_check.mirrors(self._kinogo_url())
        for site, base in sites:
            self._emit("mirror_result", {"id": check_id, "mirror": mirror_check.pending(site, base)})

        def run(item: tuple[str, str]) -> None:
            self._emit("mirror_result", {"id": check_id, "mirror": mirror_check.check(item[0], item[1], query)})

        with ThreadPoolExecutor(max_workers=_MIRROR_CHECK_WORKERS) as pool:
            # list(): исключение из потока не должно потеряться.
            list(pool.map(run, sites))
        return {"total": len(sites)}

    def _lampac_state(self, _params: dict) -> dict:
        return self._lampac.state()

    def _lampac_base(self) -> str:
        base = self._lampac.base_url
        if base is None:
            raise ApiError("lampac_off", "Lampac не запущен")
        return base

    def _lampac_sources(self, params: dict) -> dict:
        title = _text(params, "title")
        search_id = _text(params, "progress_id")
        base = self._lampac_base()
        with self._tracked(params) as progress:
            def search(serial: bool) -> int:
                return lampac.search(
                    base,
                    title,
                    _optional_text(params, "original_title"),
                    _optional_text(params, "year"),
                    lambda source: self._emit("lampac_source", {"id": search_id, "source": source}),
                    progress.check,
                    serial=serial,
                )

            guess = params.get("serial") is True
            try:
                # Сайт не всегда говорит, фильм это или сериал: другая догадка тоже проверяется.
                found = search(guess) or search(not guess)
            except lampac.Unavailable as exc:
                print(f"backend: lampac: {exc}", file=sys.stderr)
                raise ApiError("network", "Lampac не ответил") from exc
        return {"found": found}

    def _lampac_variants(self, params: dict) -> dict:
        url = _http_url(params.get("url"))
        # Адреса приходят из интерфейса: запросы уходят только на свой сервер.
        if urlparse(url).netloc != urlparse(self._lampac_base()).netloc:
            raise ApiError("invalid_params", "Адрес не относится к Lampac")
        try:
            variants = lampac.load_variants(url)
        except lampac.Unavailable as exc:
            raise ApiError("network", "Lampac не ответил") from exc
        if variants is None:
            raise ApiError("not_found", "У источника нет вариантов")
        return variants

    def _trailer(self, params: dict) -> dict:
        try:
            videos = trailers.find(_text(params, "title"), _optional_text(params, "year"))
        except trailers.TrailerUnavailable as exc:
            raise ApiError("network", "YouTube недоступен") from exc
        if not videos:
            raise ApiError("not_found", "Трейлер не найден")
        return {"videos": videos}

    def _open_trailer_search(self, params: dict) -> dict:
        # Адрес строится здесь: интерфейс не может открыть в браузере что угодно.
        webbrowser.open(trailers.search_url(_text(params, "title"), _optional_text(params, "year")))
        return {"ok": True}

    def _get_settings(self, _params: dict) -> dict:
        return settings.load(self._settings_path)

    def _set_settings(self, params: dict) -> dict:
        try:
            updated = settings.update(params, self._settings_path)
            if "lampac_enabled" in params:
                self.apply_lampac_setting()
            return updated
        except ValueError as exc:
            raise ApiError("invalid_params", str(exc)) from exc

    # --- мой список ---

    def _watch_started(self, watch: dict) -> None:
        """Запуск просмотра ставит «Смотрю». Сбой записи списка не мешает просмотру."""
        try:
            self._emit("watchlist_changed", {"entry": self._watchlist.on_play_started(watch["title"])})
        except Exception as exc:
            print(f"backend: список при запуске: {type(exc).__name__}: {exc}", file=sys.stderr)

    def _report_watched(self, watch: dict | None, progress: _WatchProgress) -> None:
        """Досмотренная серия отмечается; о конце просмотра интерфейс узнаёт один раз."""
        if watch is None or not progress.take():
            return
        try:
            title = watch["title"]
            if watch["episode"] is not None and title.get("kind") == "series":
                entry = self._watchlist.set_episode(title, watch["season"], watch["episode"], True)
                self._emit("watchlist_changed", {"entry": entry})
            entry = self._watchlist.get(title)
            final = watch["final"] and (entry is None or entry["status"] != "completed")
            self._emit("watch_completed", {"key": self._watchlist.key_of(title), "title": title, "final": final})
        except Exception as exc:
            print(f"backend: список после просмотра: {type(exc).__name__}: {exc}", file=sys.stderr)

    @staticmethod
    def _watch_call(action: Callable[[], dict | None]) -> dict | None:
        try:
            return action()
        except ValueError as exc:
            raise ApiError("invalid_params", str(exc)) from exc

    def _watchlist_list(self, _params: dict) -> dict:
        result: dict = {"items": self._watchlist.entries()}
        warning = self._watchlist.take_warning()
        if warning:
            result["warning"] = warning
        return result

    def _watchlist_get(self, params: dict) -> dict:
        return {"entry": self._watch_call(lambda: self._watchlist.get(params.get("title")))}

    def _changed(self, entry: dict | None) -> dict:
        """Изменение видно всем экранам: страница фильма и «Мой список» обновятся сами."""
        self._emit("watchlist_changed", {"entry": entry})
        return {"entry": entry}

    def _watchlist_set_status(self, params: dict) -> dict:
        return self._changed(self._watch_call(
            lambda: self._watchlist.set_status(params.get("title"), params.get("status"))))

    def _watchlist_remove(self, params: dict) -> dict:
        self._watch_call(lambda: self._watchlist.remove(params.get("title")))
        return self._changed(None)

    def _watchlist_set_episode(self, params: dict) -> dict:
        return self._changed(self._watch_call(lambda: self._watchlist.set_episode(
            params.get("title"), params.get("season"), params.get("episode"), params.get("watched"))))

    def _watchlist_resolve(self, params: dict) -> dict:
        """Найти id IMDb и перевести на него запись. Сбой сети не ошибка: остаётся запасной ключ."""
        raw = params.get("title")
        title = self._watch_call(lambda: watchlist.parse_title(raw))
        if self._watchlist.needs_lookup(raw):
            try:
                found = imdb.find_id(title["orig_title"] or title["title"], title["year"], title["kind"])
            except imdb.Unavailable as exc:
                # «Не найдено» запоминается на неделю, а сбой сети — нет: в следующий раз поиск повторится.
                print(f"backend: поиск IMDb: {exc}", file=sys.stderr)
            else:
                self._watchlist.apply_id(raw, found)
        return {"entry": self._watchlist.get(raw), "key": self._watchlist.key_of(raw)}


def _take_stdio():
    """Забрать настоящие stdin/stdout себе, чтобы print, Chrome и mpv не попадали в протокол."""
    proto_in = os.fdopen(os.dup(0), "r", encoding="utf-8", errors="replace", newline="\n")
    proto_out = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n", buffering=1)

    os.dup2(2, 1)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    sys.stdout = sys.stderr
    return proto_in, proto_out


def serve() -> int:
    proto_in, proto_out = _take_stdio()

    def write(text: str) -> None:
        proto_out.write(text + "\n")
        proto_out.flush()

    backend = Backend(write=write)
    backend.install_shaders()
    if settings.load()["lampac_enabled"]:
        backend.apply_lampac_setting()
    for line in proto_in:
        if line.strip():
            backend.handle_line(line)

    backend.close()
    # Поток просмотра ждёт mpv, а окно уже закрыто: mpv остаётся, процесс завершается сразу.
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(serve())
