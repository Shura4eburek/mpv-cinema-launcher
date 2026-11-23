"""Протокол backend: разбор строк, проверка данных, коды ошибок, запуск плеера, постеры."""

import json
import threading
from types import SimpleNamespace
from unittest import mock

import pytest

from mpv_launcher import backend as be
from mpv_launcher import runner, scraper


class Harness:
    def __init__(self, tmp_path, driver=None):
        self.lines = []
        self.received = threading.Condition()
        self.driver = driver if driver is not None else mock.Mock()
        self.created = 0
        self.backend = be.Backend(
            write=self._write,
            driver_factory=self._factory,
            settings_path=tmp_path / "settings.json",
            poster_dir=tmp_path / "posters",
        )

    def _factory(self):
        self.created += 1
        return self.driver

    def _write(self, text):
        with self.received:
            self.lines.append(json.loads(text))
            self.received.notify_all()

    def wait_for(self, predicate, timeout=5):
        with self.received:
            assert self.received.wait_for(
                lambda: any(predicate(m) for m in self.lines), timeout
            ), f"нет ожидаемого сообщения: {self.lines}"
            return next(m for m in self.lines if predicate(m))

    def call(self, method, params=None, request_id=1):
        self.backend.handle_line(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        return self.wait_for(lambda m: m.get("id") == request_id)

    def event(self, name):
        return self.wait_for(lambda m: m.get("event") == name)


@pytest.fixture(autouse=True)
def kinogo_is_down():
    """По умолчанию тесты проверяют путь HDRezka; KinoGo настраивается отдельно."""
    with mock.patch.object(be.sources.kinogo, "search", side_effect=scraper.SiteUnavailable()):
        yield


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    yield harness
    harness.backend.close()


def test_bad_json_does_not_stop_backend(h):
    h.backend.handle_line("{not json")
    assert h.wait_for(lambda m: "error" in m)["error"]["code"] == "invalid_params"
    assert "result" in h.call("get_settings")


def test_non_object_message_is_rejected(h):
    h.backend.handle_line("[1, 2]")
    assert h.wait_for(lambda m: "error" in m)["error"]["code"] == "invalid_params"


def test_unknown_method(h):
    assert h.call("nope")["error"]["code"] == "invalid_params"


def test_status_reports_mpv_and_shaders(h):
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.shaders, "are_shaders_installed", return_value=False):
        result = h.call("status")["result"]
    assert result == {"mpv_found": True, "upscale_ready": False}


def test_search_returns_cards_and_does_not_start_chrome_eagerly(h):
    item = scraper.MovieSearchResult(title="Т", url="https://s/1", poster_url=None, info="2020")
    with mock.patch.object(be.scraper, "search_movies", return_value=[item]) as search:
        result = h.call("search", {"query": "Т"})["result"]
    assert result == [{"title": "Т", "url": "https://s/1", "poster_url": None, "info": "2020", "source": "hdrezka"}]
    assert h.created == 0
    assert search.call_args.kwargs["raise_on_unavailable"] is True
    assert search.call_args.kwargs["get_driver"]() is h.driver


def test_scraper_starts_browser_only_after_http_failed():
    get_driver = mock.Mock(return_value=None)
    with mock.patch.object(scraper.requests, "get", return_value=SimpleNamespace(
        status_code=200, text="<html></html>", encoding=None
    )):
        scraper.search_movies("x", get_driver=get_driver)
    get_driver.assert_not_called()

    with mock.patch.object(scraper.requests, "get", side_effect=OSError()):
        assert scraper.search_movies("x", get_driver=get_driver) == []
    get_driver.assert_called_once()


def test_dead_chrome_session_is_replaced(tmp_path):
    harness = Harness(tmp_path)
    dead = mock.Mock()
    type(dead).current_url = mock.PropertyMock(side_effect=RuntimeError("session deleted"))
    harness.backend._driver = dead
    details = scraper.MovieDetails(title="Т", url="https://s/1", description="d")
    with mock.patch.object(be.scraper, "fetch_movie_details", return_value=details) as fetch:
        harness.call("movie", {"url": "https://s/1"})
    dead.quit.assert_called_once()
    assert fetch.call_args.kwargs["driver"] is harness.driver
    harness.backend.close()


def test_blocked_movie_page_is_network_error(h):
    details = scraper.MovieDetails(title="Подождите, идёт проверка", url="https://s/1")
    with mock.patch.object(be.scraper, "fetch_movie_details", return_value=details):
        assert h.call("movie", {"url": "https://s/1"})["error"]["code"] == "network"


def test_translator_request_failure_is_not_reported_as_no_video(h):
    h.driver.current_url = "https://s/1"
    h.driver.execute_script.side_effect = RuntimeError("no jQuery")
    assert h.call("translator_streams", {"url": "https://s/1", "translator_id": "7"})["error"]["code"] == "internal"


def test_search_requires_query(h):
    assert h.call("search", {"query": "  "})["error"]["code"] == "invalid_params"


def test_search_network_error(h):
    with mock.patch.object(be.scraper, "search_movies", side_effect=scraper.SiteUnavailable()):
        assert h.call("search", {"query": "x"})["error"]["code"] == "network"


def test_driver_failure_does_not_leak_exception_text(h):
    with mock.patch.object(be.scraper, "search_movies", side_effect=RuntimeError("secret path")):
        error = h.call("search", {"query": "x"})["error"]
    assert error["code"] == "internal"
    assert "secret" not in error["message"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "", None, 5])
def test_movie_rejects_non_http_url(h, url):
    assert h.call("movie", {"url": url})["error"]["code"] == "invalid_params"


def test_movie_returns_details(h):
    h.driver.current_url = "https://s/1"
    details = scraper.MovieDetails(title="Т", url="https://s/1", streams={"720p": ["https://c/a.m3u8"]})
    with mock.patch.object(be.scraper, "fetch_movie_details", return_value=details):
        result = h.call("movie", {"url": "https://s/1"})["result"]
    assert result["title"] == "Т"
    assert result["streams"] == {"720p": ["https://c/a.m3u8"]}


def test_translator_streams_opens_movie_page_when_driver_moved(h):
    h.driver.current_url = "https://s/other"
    streams = {"720p": ["https://c/a.m3u8"]}
    with mock.patch.object(be.scraper, "fetch_movie_details") as fetch, \
        mock.patch.object(be.scraper, "fetch_translator_streams", return_value=streams):
        result = h.call("translator_streams", {"url": "https://s/1", "translator_id": "7"})["result"]
    fetch.assert_called_once_with("https://s/1", driver=h.driver)
    assert result == streams


def test_translator_streams_empty_is_no_streams(h):
    h.driver.current_url = "https://s/1"
    with mock.patch.object(be.scraper, "fetch_translator_streams", return_value={}):
        error = h.call("translator_streams", {"url": "https://s/1", "translator_id": "7"})["error"]
    assert error["code"] == "no_streams"


def test_translator_streams_site_returns_no_url(h):
    h.driver.current_url = "https://s/1"
    h.driver.execute_script.return_value = {"success": False, "url": False, "message": "недоступно"}
    error = h.call("translator_streams", {"url": "https://s/1", "translator_id": "7"})["error"]
    assert error["code"] == "no_streams"


# --- KinoGo ---

KINOGO_MOVIE = "https://uakinogo.io/filmy/1.html"


def test_search_prefers_kinogo(h):
    card = scraper.MovieSearchResult(title="К", url=KINOGO_MOVIE, source="kinogo")
    with mock.patch.object(be.sources.kinogo, "search", side_effect=None, return_value=[card]),         mock.patch.object(be.scraper, "search_movies") as hdrezka:
        result = h.call("search", {"query": "К"})["result"]
    assert result[0]["source"] == "kinogo"
    hdrezka.assert_not_called()


def _kinogo_details(streams=None):
    return scraper.MovieDetails(
        title="К", url=KINOGO_MOVIE, source="kinogo", referer="https://cinemar.cc/",
        streams=streams or {"1080p": ["https://atlas/old.m3u8"]},
    )


def test_kinogo_movie_without_video_returns_alternatives(h):
    error = be.kinogo.NoVideo("нет плеера")
    error.details = scraper.MovieDetails(title="К (2024)", url=KINOGO_MOVIE, source="kinogo")
    alternative = scraper.MovieSearchResult(title="К", url="https://rezka/1.html")
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=error),         mock.patch.object(be.scraper, "search_movies", return_value=[alternative]):
        result = h.call("movie", {"url": KINOGO_MOVIE})["result"]
    assert result["streams"] == {}
    assert result["alternatives"][0]["url"] == "https://rezka/1.html"


def test_kinogo_site_failure_is_network_error(h):
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=scraper.SiteUnavailable()):
        assert h.call("movie", {"url": KINOGO_MOVIE})["error"]["code"] == "network"


def _play_kinogo(h, request_id=5):
    return h.call("play", {
        "title": "К", "urls": ["https://atlas/old.m3u8"], "movie_url": KINOGO_MOVIE,
        "quality": "1080p", "referer": "https://cinemar.cc/",
    }, request_id=request_id)


def test_fresh_kinogo_link_is_used_as_is_with_player_referer(h):
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=_kinogo_details()) as fetch,         mock.patch.object(be.locate, "find_mpv", return_value="mpv"),         mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        h.call("movie", {"url": KINOGO_MOVIE}, request_id=1)
        _play_kinogo(h)
        h.event("playback_finished")
    assert fetch.call_count == 1
    plan = run.call_args.args[0]
    assert plan.mpv_args[-1] == "https://atlas/old.m3u8"
    assert any("Referer: https://cinemar.cc/" in a for a in plan.mpv_args)


def test_expired_kinogo_link_is_refreshed(h):
    new = _kinogo_details({"1080p": ["https://atlas/new.m3u8", "https://cfnd/new.m3u8"]})
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=[_kinogo_details(), new]),         mock.patch.object(be.locate, "find_mpv", return_value="mpv"),         mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        h.call("movie", {"url": KINOGO_MOVIE}, request_id=1)
        h.backend._stream_times[KINOGO_MOVIE] -= be._STREAM_MAX_AGE_SECONDS + 1
        _play_kinogo(h)
        h.event("playback_finished")
    plan, fallback = run.call_args.args
    assert plan.mpv_args[-1] == "https://atlas/new.m3u8"
    assert fallback == ["https://cfnd/new.m3u8"]


def test_failed_kinogo_playback_refreshes_link_on_retry(h):
    new = _kinogo_details({"1080p": ["https://atlas/new.m3u8"]})
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=[_kinogo_details(), new]) as fetch,         mock.patch.object(be.locate, "find_mpv", return_value="mpv"),         mock.patch.object(be.runner, "run_with_fallback", side_effect=[runner.MPV_EXIT_LOAD_FAILED, 0]) as run:
        h.call("movie", {"url": KINOGO_MOVIE}, request_id=1)
        _play_kinogo(h, request_id=2)
        h.event("playback_failed")
        _play_kinogo(h, request_id=3)
        h.event("playback_finished")
    assert fetch.call_count == 2
    assert run.call_args.args[0].mpv_args[-1] == "https://atlas/new.m3u8"


def test_player_server_fallback_warns_about_quality(h):
    def run(plan, fallback, on_fallback, **_):
        on_fallback("https://emerald.host.cinemap.cc/m/1080.m3u8")
        on_fallback("https://cfnd.cinemap.cc/sig/m/1080.m3u8")
        return 0

    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run):
        h.call("play", {"title": "К", "urls": ["https://a/1.m3u8"]})
        assert h.event("playback_fallback")["data"]["code"] == "lower_quality"
        h.event("playback_finished")
    assert len([m for m in h.lines if m.get("event") == "playback_fallback"]) == 1


def test_second_play_after_refresh_uses_new_links_not_expired_ones(h):
    new = _kinogo_details({"1080p": ["https://atlas/new.m3u8"]})
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=[_kinogo_details(), new]) as fetch, \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        h.call("movie", {"url": KINOGO_MOVIE}, request_id=1)
        h.backend._stream_times[KINOGO_MOVIE] -= be._STREAM_MAX_AGE_SECONDS + 1
        _play_kinogo(h, request_id=2)
        h.event("playback_finished")
        _play_kinogo(h, request_id=3)
        h.wait_for(lambda m: m.get("id") == 3)
        for _ in range(100):
            if run.call_count == 2:
                break
            threading.Event().wait(0.02)
    assert fetch.call_count == 2
    assert run.call_args.args[0].mpv_args[-1] == "https://atlas/new.m3u8"


def test_refresh_without_selected_quality_uses_best_new_variant(h):
    new = _kinogo_details({"240p": ["https://atlas/240.m3u8"], "720p": ["https://atlas/720.m3u8"]})
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=new), \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        _play_kinogo(h)
        h.event("playback_finished")
    assert run.call_args.args[0].mpv_args[-1] == "https://atlas/720.m3u8"


def test_movie_passes_card_source_title_and_saved_voice(h):
    with mock.patch.object(be.sources, "open_movie", return_value=_kinogo_details()) as open_movie:
        h.call("movie", {"url": "https://new-domain/1.html", "source": "kinogo", "title": "К", "voice": "Гаврилов"})
    kwargs = open_movie.call_args.kwargs
    assert (kwargs["source"], kwargs["title"], kwargs["voice"]) == ("kinogo", "К", "Гаврилов")


def test_refresh_keeps_selected_voice(h):
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=_kinogo_details()) as fetch, \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0):
        h.call("play", {"title": "К", "urls": ["https://atlas/old.m3u8"], "movie_url": KINOGO_MOVIE,
                        "quality": "1080p", "voice": "Гаврилов"})
        h.event("playback_finished")
    assert fetch.call_args.kwargs["voice"] == "Гаврилов"


def test_kinogo_voice_switch_returns_streams(h):
    streams = {"1080p": ["https://atlas/gavrilov.m3u8"]}
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=_kinogo_details(streams)) as fetch:
        result = h.call("translator_streams", {"url": KINOGO_MOVIE, "translator_id": "Гаврилов"})["result"]
    assert result == streams
    assert fetch.call_args.kwargs["voice"] == "Гаврилов"


def test_kinogo_missing_voice_is_no_streams(h):
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=be.kinogo.NoVideo("нет")):
        error = h.call("translator_streams", {"url": KINOGO_MOVIE, "translator_id": "Нет такой"})["error"]
    assert error["code"] == "no_streams"


def test_refresh_failure_keeps_old_link(h):
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=be.kinogo.NoVideo("x")),         mock.patch.object(be.locate, "find_mpv", return_value="mpv"),         mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        _play_kinogo(h)
        h.event("playback_finished")
    assert run.call_args.args[0].mpv_args[-1] == "https://atlas/old.m3u8"


@pytest.mark.parametrize("field", ["referer", "movie_url"])
def test_play_validates_optional_addresses(h, field):
    error = h.call("play", {"title": "К", "urls": ["https://a/1.m3u8"], field: "file:///x"})["error"]
    assert error["code"] == "invalid_params"


# --- ход загрузки и отмена ---

def _steps(h):
    return [(m["data"]["step"], m["data"]["state"]) for m in h.lines if m.get("event") == "load_progress"]


def test_movie_reports_real_steps(h):
    def fetch(url, driver, base, voice, strict, progress, get_driver):
        with progress.step("page"):
            pass
        with progress.step("quality"):
            pass
        return _kinogo_details()

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch):
        h.call("movie", {"url": KINOGO_MOVIE, "progress_id": "a"})
    assert _steps(h) == [("page", "running"), ("page", "done"), ("quality", "running"), ("quality", "done")]
    assert all(m["data"]["id"] == "a" for m in h.lines if m.get("event") == "load_progress")


def test_failed_step_is_reported(h):
    def fetch(url, driver, base, voice, strict, progress, get_driver):
        with progress.step("page"):
            raise scraper.SiteUnavailable()

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch):
        h.call("movie", {"url": KINOGO_MOVIE, "progress_id": "a"})
    assert ("page", "error") in _steps(h)


def test_cancel_interrupts_waiting_and_returns_cancelled(h):
    started = threading.Event()

    def fetch(url, driver, base, voice, strict, progress, get_driver):
        started.set()
        while True:
            progress.check()
            threading.Event().wait(0.01)

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch):
        h.backend.handle_line(json.dumps({"id": 1, "method": "movie", "params": {"url": KINOGO_MOVIE, "progress_id": "a"}}))
        assert started.wait(2)
        h.backend.handle_line(json.dumps({"id": 2, "method": "cancel", "params": {"id": "a"}}))
        assert h.wait_for(lambda m: m.get("id") == 1)["error"]["code"] == "cancelled"
    assert "a" not in h.backend._cancels


def test_cancelled_movie_does_not_fall_back_to_hdrezka(h):
    def fetch(url, driver, base, voice, strict, progress, get_driver):
        h.backend._cancels["a"].set()
        raise be.kinogo.NoVideo("Chrome закрыт")

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch), \
        mock.patch.object(be.scraper, "search_movies") as search:
        assert h.call("movie", {"url": KINOGO_MOVIE, "progress_id": "a"})["error"]["code"] == "cancelled"
    search.assert_not_called()


def test_stuck_operation_closes_chrome_after_grace(h, monkeypatch):
    monkeypatch.setattr(be, "_CANCEL_GRACE_SECONDS", 0.02)
    release = threading.Event()
    started = threading.Event()

    def fetch(url, driver, base, voice, strict, progress, get_driver):
        get_driver()
        with progress.step("player", browser=True):
            started.set()
            release.wait(5)
        return _kinogo_details()

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch):
        h.backend.handle_line(json.dumps({"id": 1, "method": "movie", "params": {"url": KINOGO_MOVIE, "progress_id": "a"}}))
        assert started.wait(2)
        h.backend.handle_line(json.dumps({"id": 2, "method": "cancel", "params": {"id": "a"}}))
        for _ in range(200):
            if h.driver.quit.called:
                break
            threading.Event().wait(0.01)
        release.set()
        h.wait_for(lambda m: m.get("id") == 1)
    h.driver.quit.assert_called()


def test_cancel_outside_browser_step_keeps_chrome(h, monkeypatch):
    monkeypatch.setattr(be, "_CANCEL_GRACE_SECONDS", 0.02)
    release = threading.Event()
    started = threading.Event()

    def fetch(url, driver, base, voice, strict, progress, get_driver):
        get_driver()
        with progress.step("quality"):
            started.set()
            release.wait(5)
        return _kinogo_details()

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch):
        h.backend.handle_line(json.dumps({"id": 1, "method": "movie", "params": {"url": KINOGO_MOVIE, "progress_id": "a"}}))
        assert started.wait(2)
        h.backend.handle_line(json.dumps({"id": 2, "method": "cancel", "params": {"id": "a"}}))
        threading.Event().wait(0.2)
        h.driver.quit.assert_not_called()
        release.set()
        h.wait_for(lambda m: m.get("id") == 1)


def test_chrome_starts_only_when_page_needs_it(h):
    def fetch(url, driver, base, voice, strict, progress, get_driver):
        assert driver is None
        assert h.created == 0
        return _kinogo_details()

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch):
        assert "result" in h.call("movie", {"url": KINOGO_MOVIE, "progress_id": "a"})


def test_cancelled_refresh_does_not_start_player(h):
    def fetch(url, driver, base, voice, progress, get_driver):
        h.backend._cancels["a"].set()
        raise be.kinogo.NoVideo("Chrome закрыт")

    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=fetch), \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback") as run:
        result = h.call("play", {"title": "К", "urls": ["https://atlas/old.m3u8"], "movie_url": KINOGO_MOVIE,
                                 "quality": "1080p", "progress_id": "a"})
    assert result["error"]["code"] == "cancelled"
    run.assert_not_called()


# --- кеш страницы фильма ---


def _film(**extra):
    return scraper.MovieDetails(title="Довод", url="https://rezka/1.html", streams={"1080p": ["https://a/1.m3u8"]}, **extra)


_OPEN = {"url": "https://rezka/1.html", "source": "hdrezka", "title": "Довод"}


def test_movie_page_is_cached_for_five_minutes(h):
    with mock.patch.object(be.sources, "open_movie", return_value=_film()) as load, \
        mock.patch.object(be.time, "monotonic", return_value=1000.0) as clock:
        first = h.call("movie", _OPEN, request_id=2)["result"]
        clock.return_value = 1299.0
        assert h.call("movie", _OPEN, request_id=3)["result"] == first
        assert load.call_count == 1
        clock.return_value = 1300.0
        h.call("movie", _OPEN, request_id=4)
        assert load.call_count == 2


def test_cache_is_separate_for_each_voice(h):
    with mock.patch.object(be.sources, "open_movie", return_value=_film()) as load:
        h.call("movie", _OPEN, request_id=2)
        h.call("movie", {**_OPEN, "voice": "Дубляж"}, request_id=3)
    assert load.call_count == 2


def test_failed_page_is_not_cached(h):
    empty = scraper.MovieDetails(title="Довод", url="https://rezka/1.html", description="Текст")
    with mock.patch.object(be.sources, "open_movie", return_value=empty) as load:
        h.call("movie", _OPEN, request_id=2)
        h.call("movie", _OPEN, request_id=3)
    assert load.call_count == 2


def test_failed_playback_forgets_page(h):
    with mock.patch.object(be.sources, "open_movie", return_value=_film()) as load:
        h.call("movie", _OPEN, request_id=2)
        h.backend._forget_page("https://rezka/1.html")
        h.call("movie", _OPEN, request_id=3)
    assert load.call_count == 2


def test_cached_kinogo_page_keeps_age_of_its_links(h):
    url = "https://rezka/1.html"
    with mock.patch.object(be.sources, "open_movie", return_value=_film()), \
        mock.patch.object(be.time, "monotonic", return_value=1000.0) as clock:
        h.call("movie", _OPEN, request_id=2)
        h.backend._stream_times[url] = 1200.0  # за это время загружена другая озвучка
        clock.return_value = 1250.0
        h.call("movie", _OPEN, request_id=3)
    assert h.backend._stream_times[url] == 1000.0


def test_voice_streams_are_cached(h):
    params = {"url": "https://rezka/1.html", "translator_id": "5", "source": "hdrezka"}
    h.driver.current_url = params["url"]
    with mock.patch.object(be.scraper, "fetch_translator_streams", return_value={"720p": ["https://a/2.m3u8"]}) as fetch:
        h.call("translator_streams", params, request_id=2)
        assert h.call("translator_streams", params, request_id=3)["result"] == {"720p": ["https://a/2.m3u8"]}
    assert fetch.call_count == 1


# --- Lampac ---


class _FakeLampac:
    def __init__(self, on_state):
        self.on_state = on_state
        self.calls = []
        self.base_url = None

    def state(self):
        return {"state": "running" if self.base_url else "off", "detail": "", "available": True}

    def enable(self):
        self.calls.append("enable")

    def disable(self):
        self.calls.append("disable")

    def close(self):
        self.calls.append("close")


@pytest.fixture
def lh(tmp_path):
    harness = Harness.__new__(Harness)
    harness.lines = []
    harness.received = threading.Condition()
    harness.driver = mock.Mock()
    harness.created = 0
    harness.backend = be.Backend(
        write=harness._write,
        driver_factory=harness._factory,
        settings_path=tmp_path / "settings.json",
        poster_dir=tmp_path / "posters",
        lampac_server_factory=_FakeLampac,
    )
    yield harness
    harness.backend.close()


def test_setting_starts_and_stops_lampac(lh):
    server = lh.backend._lampac
    lh.call("set_settings", {"interpolation": False}, request_id=2)
    assert server.calls == []
    lh.call("set_settings", {"lampac_enabled": True}, request_id=3)
    lh.call("set_settings", {"lampac_enabled": False}, request_id=4)
    assert server.calls == ["enable", "disable"]


def test_close_stops_lampac(lh):
    lh.backend.close()
    assert "close" in lh.backend._lampac.calls


def test_state_event_reaches_interface(lh):
    lh.backend._lampac.on_state({"state": "starting", "detail": "", "available": True})
    assert lh.event("lampac_state")["data"]["lampac"]["state"] == "starting"


def test_sources_need_running_server(lh):
    answer = lh.call("lampac_sources", {"title": "Довод", "progress_id": "s1"}, request_id=2)
    assert answer["error"]["code"] == "lampac_off"


def test_sources_are_sent_as_events(lh):
    lh.backend._lampac.base_url = "http://127.0.0.1:5000"
    source = {"id": "a", "name": "A", "variants": {}}

    def fake(base, title, original, year, on_source, check, serial=False):
        assert serial is False
        assert (base, title, original, year) == ("http://127.0.0.1:5000", "Довод", "Tenet", "2020")
        on_source(source)
        return 1

    with mock.patch.object(be.lampac, "search", side_effect=fake):
        answer = lh.call("lampac_sources", {"title": "Довод", "original_title": "Tenet", "year": "2020", "progress_id": "s1"}, request_id=2)
    assert answer["result"] == {"found": 1}
    assert lh.event("lampac_source")["data"] == {"id": "s1", "source": source}


def test_serial_flag_reaches_search(lh):
    lh.backend._lampac.base_url = "http://127.0.0.1:5000"
    with mock.patch.object(be.lampac, "search", return_value=1) as search:
        lh.call("lampac_sources", {"title": "Т", "serial": True, "progress_id": "s2"}, request_id=2)
    assert search.call_count == 1
    assert search.call_args.kwargs["serial"] is True


def test_other_kind_is_tried_when_nothing_found(lh):
    lh.backend._lampac.base_url = "http://127.0.0.1:5000"
    with mock.patch.object(be.lampac, "search", side_effect=[0, 2]) as search:
        answer = lh.call("lampac_sources", {"title": "Т", "serial": True, "progress_id": "s3"}, request_id=2)
    assert answer["result"] == {"found": 2}
    assert [c.kwargs["serial"] for c in search.call_args_list] == [True, False]


def test_lampac_stream_gets_no_hdrezka_referer(lh):
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        lh.call("play", {"title": "К", "urls": ["https://cdn/a.m3u8"], "movie_url": "https://k/1.html", "source": "lampac"}, request_id=2)
        lh.event("playback_finished")
    assert not any("Referer" in a for a in run.call_args.args[0].mpv_args)


def test_variants_only_from_own_server(lh):
    lh.backend._lampac.base_url = "http://127.0.0.1:5000"
    with mock.patch.object(be.lampac, "load_variants") as load:
        answer = lh.call("lampac_variants", {"url": "https://evil.example/lite/a"}, request_id=2)
    assert answer["error"]["code"] == "invalid_params"
    load.assert_not_called()


def test_variants_errors(lh):
    lh.backend._lampac.base_url = "http://127.0.0.1:5000"
    url = "http://127.0.0.1:5000/lite/a"
    with mock.patch.object(be.lampac, "load_variants", return_value=None):
        assert lh.call("lampac_variants", {"url": url}, request_id=2)["error"]["code"] == "not_found"
    with mock.patch.object(be.lampac, "load_variants", side_effect=be.lampac.Unavailable("x")):
        assert lh.call("lampac_variants", {"url": url}, request_id=3)["error"]["code"] == "network"


def test_lampac_film_does_not_refresh_kinogo_links(lh):
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run, \
        mock.patch.object(be.kinogo, "fetch_movie") as fetch:
        lh.call("play", {"title": "К", "urls": ["http://127.0.0.1:5000/proxy/a.mp4"], "movie_url": "https://uakinogo.io/filmy/1.html", "source": "lampac", "quality": "Авто"}, request_id=2)
        lh.event("playback_finished")
    fetch.assert_not_called()
    assert run.call_args.args[0].mpv_args[-1] == "http://127.0.0.1:5000/proxy/a.mp4"


# --- проверка зеркал ---


def test_mirror_check_reports_each_address_twice(h):
    sites = [("kinogo", "https://a.test"), ("hdrezka", "https://r.test")]
    done = lambda site, base, query: {"site": site, "url": base, "state": "ok", "query": query}
    with mock.patch.object(be.mirror_check, "mirrors", return_value=sites), \
        mock.patch.object(be.mirror_check, "check", side_effect=done):
        assert h.call("mirror_check", {"query": "Довод", "id": "c1"}, request_id=2)["result"] == {"total": 2}
    events = [m["data"] for m in h.lines if m.get("event") == "mirror_result"]
    assert all(e["id"] == "c1" for e in events)
    assert [e["mirror"]["state"] for e in events[:2]] == ["checking", "checking"]
    assert sorted(e["mirror"]["url"] for e in events[2:]) == ["https://a.test", "https://r.test"]
    assert events[2]["mirror"]["query"] == "Довод"


# --- трейлер ---


def test_trailer_returns_videos(h):
    videos = [{"id": "aaaaaaaaaaa", "title": "Трейлер"}]
    with mock.patch.object(be.trailers, "find", return_value=videos) as find:
        assert h.call("trailer", {"title": "Довод", "year": "2020"})["result"] == {"videos": videos}
    find.assert_called_once_with("Довод", "2020")


def test_trailer_errors(h):
    with mock.patch.object(be.trailers, "find", return_value=[]):
        assert h.call("trailer", {"title": "Т"}, request_id=2)["error"]["code"] == "not_found"
    with mock.patch.object(be.trailers, "find", side_effect=be.trailers.TrailerUnavailable()):
        assert h.call("trailer", {"title": "Т"}, request_id=3)["error"]["code"] == "network"


def test_open_trailer_search_builds_address_itself(h):
    with mock.patch.object(be.webbrowser, "open") as browser:
        h.call("open_trailer_search", {"title": "Довод (2020)", "url": "https://evil.example/"})
    assert browser.call_args.args[0].startswith("https://www.youtube.com/results?search_query=")
    assert "evil" not in browser.call_args.args[0]


# --- экран «Открываем плеер» ---

_HDREZKA_FILM = {
    "title": "К",
    "urls": ["https://a/1.m3u8"],
    "movie_url": "https://rezka/1.html",
    "source": "hdrezka",
    "quality": "1080p",
}


def _ready_file(plan):
    prefix = "--script-opts-append=cinema-ready_file="
    return next(a[len(prefix):] for a in plan.mpv_args if a.startswith(prefix))


def _play_with_id(h, request_id=1):
    return h.call("play", {"title": "К", "urls": ["https://a/1.m3u8"], "progress_id": "open"}, request_id=request_id)


def test_player_reports_started_when_film_is_playing(h):
    release = threading.Event()

    def run(plan, fallback, **_):
        be.Path(_ready_file(plan)).write_text("ready")
        release.wait(5)
        return 0

    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run):
        assert _play_with_id(h)["result"] == {"started": True}
        assert h.event("playback_started")["data"] == {"id": "open"}
        assert "open" not in h.backend._openings
        release.set()
        h.event("playback_finished")


def test_started_is_not_reported_before_film_plays(h, monkeypatch):
    release = threading.Event()
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=lambda *a, **k: release.wait(5) and 0):
        _play_with_id(h)
        threading.Event().wait(0.5)
        assert not [m for m in h.lines if m.get("event") == "playback_started"]
        release.set()
        h.event("playback_finished")
    assert not [m for m in h.lines if m.get("event") == "playback_started"]


def test_opening_timeout_removes_screen_without_signal(h, monkeypatch):
    monkeypatch.setattr(be, "_OPENING_TIMEOUT_SECONDS", 0.05)
    release = threading.Event()
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=lambda *a, **k: release.wait(5) and 0):
        _play_with_id(h)
        assert h.event("playback_started")
        release.set()
        h.event("playback_finished")


def test_cancel_closes_opening_player_without_failure(h):
    process = mock.Mock()
    release = threading.Event()
    process.terminate.side_effect = release.set

    def run(plan, fallback, on_process, should_stop, **_):
        on_process(process)
        release.wait(5)
        assert should_stop() is True
        return runner.MPV_EXIT_LOAD_FAILED

    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run):
        _play_with_id(h)
        for _ in range(100):
            if "open" in h.backend._openings and h.backend._openings["open"].process:
                break
            threading.Event().wait(0.01)
        h.backend.handle_line(json.dumps({"id": 9, "method": "cancel", "params": {"id": "open"}}))
        assert h.event("playback_finished")["data"]["id"] == "open"
    process.terminate.assert_called_once()
    assert not [m for m in h.lines if m.get("event") == "playback_failed"]


def test_cancel_after_film_started_does_not_close_player(h):
    process = mock.Mock()
    release = threading.Event()

    def run(plan, fallback, on_process, **_):
        on_process(process)
        be.Path(_ready_file(plan)).write_text("ready")
        release.wait(5)
        return 0

    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run):
        _play_with_id(h)
        h.event("playback_started")
        h.backend.handle_line(json.dumps({"id": 9, "method": "cancel", "params": {"id": "open"}}))
        threading.Event().wait(0.1)
        process.terminate.assert_not_called()
        release.set()
        h.event("playback_finished")


def test_failure_before_player_start_clears_opening(h):
    with mock.patch.object(be.locate, "find_mpv", return_value=None):
        assert _play_with_id(h)["error"]["code"] == "no_mpv"
    assert h.backend._openings == {}


def test_device_reports_detected_preset(h):
    with mock.patch.object(be.machine, "detect_device", return_value={"preset": "high", "gpu": "RTX"}), \
        mock.patch.object(be.machine, "vsr_available", return_value=True):
        assert h.call("device")["result"] == {"preset": "high", "gpu": "RTX", "vsr": True}


@pytest.mark.parametrize(
    ("preset", "content", "available", "expected"),
    [
        ("high", "film", True, True),
        ("high", "film", False, False),
        ("high", "anime", True, False),
        ("mid", "film", True, False),
        ("low", "film", True, False),
    ],
)
def test_vsr_is_used_only_for_high_films(h, preset, content, available, expected):
    h.call("set_settings", {"preset": preset, "content": content}, request_id=2)
    with mock.patch.object(be.machine, "vsr_available", return_value=available), \
        mock.patch.object(be.machine, "mpv_supports_vsr", return_value=True), \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        h.call("play", _HDREZKA_FILM)
        h.event("playback_finished")
    args = run.call_args.args[0].mpv_args
    assert any("scaling-mode=nvidia" in a for a in args) is expected


def test_auto_high_uses_vsr(h):
    with mock.patch.object(be.machine, "detect_device", return_value={"preset": "high", "gpu": "RTX"}), \
        mock.patch.object(be.machine, "vsr_available", return_value=True), \
        mock.patch.object(be.machine, "mpv_supports_vsr", return_value=True), \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        h.call("play", _HDREZKA_FILM)
        h.event("playback_finished")
    assert any("scaling-mode=nvidia" in a for a in run.call_args.args[0].mpv_args)


@pytest.mark.parametrize(
    ("params", "supported"),
    [
        ({"movie_url": "https://rezka/1.html", "source": "hdrezka", "quality": "4K"}, True),
        ({"movie_url": "https://rezka/1.html", "source": "hdrezka", "quality": "2160p"}, True),
        ({}, True),
        (None, False),
    ],
)
def test_vsr_is_skipped_for_4k_links_and_old_mpv(h, params, supported):
    request = {"title": "К", "urls": ["https://a/1.m3u8"], **(_HDREZKA_FILM if params is None else params)}
    h.call("set_settings", {"preset": "high", "content": "film"}, request_id=2)
    with mock.patch.object(be.machine, "vsr_available", return_value=True), \
        mock.patch.object(be.machine, "mpv_supports_vsr", return_value=supported), \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        h.call("play", request)
        h.event("playback_finished")
    assert not any("scaling-mode=nvidia" in a for a in run.call_args.args[0].mpv_args)


def test_cancel_before_queued_start_stops_player(h):
    h.backend.handle_line(json.dumps({"id": 9, "method": "cancel", "params": {"id": "open"}}))
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback") as run:
        assert _play_with_id(h)["error"]["code"] == "cancelled"
    run.assert_not_called()
    assert "open" not in h.backend._cancels


def test_started_is_immediate_without_player_interface(h, monkeypatch):
    monkeypatch.setattr(be.presets, "_player_args", lambda base, embedded=False: None)
    release = threading.Event()
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=lambda *a, **k: release.wait(5) and 0):
        _play_with_id(h)
        assert h.event("playback_started")["data"] == {"id": "open"}
        release.set()
        h.event("playback_finished")


# --- play ---

@pytest.mark.parametrize("urls", [[], None, "https://c/a.m3u8", ["file:///x.m3u8"], ["https://c/a", 5]])
def test_play_validates_urls(h, urls):
    assert h.call("play", {"title": "Т", "urls": urls})["error"]["code"] == "invalid_params"


def test_play_without_mpv(h):
    with mock.patch.object(be.locate, "find_mpv", return_value=None):
        error = h.call("play", {"title": "Т", "urls": ["https://c/a.m3u8"]})["error"]
    assert error["code"] == "no_mpv"


def test_play_starts_and_reports_finish_with_mirrors_and_title(h):
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        result = h.call("play", {"title": "Довод", "urls": ["https://a/1.m3u8", "https://b/1.m3u8"]})["result"]
        assert result == {"started": True}
        assert h.event("playback_finished")["data"] == {"code": 0}
    plan, fallback = run.call_args.args
    assert plan.mpv_args[-1] == "https://a/1.m3u8"
    assert "--force-media-title=Довод" in plan.mpv_args
    assert fallback == ["https://b/1.m3u8"]


def test_play_reports_when_all_mirrors_failed(h):
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=runner.MPV_EXIT_LOAD_FAILED):
        h.call("play", {"title": "Т", "urls": ["https://a/1.m3u8"]})
        assert h.event("playback_failed")["data"]["code"] == "all_mirrors_failed"


def test_player_start_error_is_reported(h):
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=1):
        h.call("play", {"title": "Т", "urls": ["https://a/1.m3u8"]})
        assert h.event("playback_failed")["data"]["code"] == "player_failed"


def test_play_applies_saved_settings(h):
    h.call("set_settings", {"content": "anime", "preset": "low"}, request_id=2)
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        h.call("play", {"title": "Т", "urls": ["https://a/1.m3u8"]})
        h.event("playback_finished")
    args = run.call_args.args[0].mpv_args
    assert any(a.endswith("low.conf") for a in args if a.startswith("--include="))
    assert "--profile=anime" in args


def test_play_clipboard_without_link(h):
    with mock.patch.object(be.clipboard, "read", return_value="just text"):
        assert h.call("play_clipboard")["error"]["code"] == "no_url"


def test_play_clipboard_uses_link_title(h):
    with mock.patch.object(be.clipboard, "read", return_value=" https://a/1.m3u8 "), \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0) as run:
        assert h.call("play_clipboard")["result"] == {"started": True}
        h.event("playback_finished")
    args = run.call_args.args[0].mpv_args
    assert args[-1] == "https://a/1.m3u8"
    assert "--force-media-title=Видео по ссылке" in args


def test_copy_text(h):
    with mock.patch.object(be.clipboard, "write", return_value=True) as write:
        assert h.call("copy_text", {"text": "abc"})["result"] == {"ok": True}
    write.assert_called_once_with("abc")


# --- settings ---

def test_settings_roundtrip_and_validation(h):
    assert h.call("get_settings", request_id=1)["result"]["content"] == "film"
    assert h.call("set_settings", {"content": "anime"}, request_id=2)["result"]["content"] == "anime"
    assert h.call("set_settings", {"content": "bad"}, request_id=3)["error"]["code"] == "invalid_params"
    assert h.call("get_settings", request_id=4)["result"]["content"] == "anime"


# --- poster ---

def _response(content=b"img", content_type="image/jpeg", status=200):
    return SimpleNamespace(
        status_code=status,
        headers={"Content-Type": content_type},
        content=content,
    )


@pytest.mark.parametrize("url", ["file:///x.jpg", "javascript:x", None])
def test_poster_rejects_non_http(h, url):
    assert h.call("poster", {"url": url})["error"]["code"] == "invalid_params"


def test_poster_downloads_once_then_uses_cache(h):
    with mock.patch.object(be.requests, "get", return_value=_response()) as get:
        first = h.call("poster", {"url": "https://s/p.jpg"}, request_id=1)["result"]["path"]
        second = h.call("poster", {"url": "https://s/p.jpg"}, request_id=2)["result"]["path"]
    assert first == second
    assert first.endswith(".jpg")
    assert get.call_count == 1


@pytest.mark.parametrize(
    "resp",
    [_response(status=404), _response(content_type="text/html"), _response(content_type="image/svg+xml")],
)
def test_poster_bad_response(h, resp):
    with mock.patch.object(be.requests, "get", return_value=resp):
        assert h.call("poster", {"url": "https://s/p.jpg"})["error"]["code"] == "network"


def test_poster_cache_ignores_unfinished_temp_files(h, tmp_path):
    with mock.patch.object(be.requests, "get", return_value=_response()):
        path = h.call("poster", {"url": "https://s/p.jpg"}, request_id=1)["result"]["path"]
    final = be.Path(path)
    temp = final.with_name(f"{final.name}.123.tmp")
    final.rename(temp)
    with mock.patch.object(be.requests, "get", return_value=_response()) as get:
        again = h.call("poster", {"url": "https://s/p.jpg"}, request_id=2)["result"]["path"]
    assert again == path
    get.assert_called_once()


def test_poster_network_failure(h):
    with mock.patch.object(be.requests, "get", side_effect=be.requests.ConnectionError()):
        assert h.call("poster", {"url": "https://s/p.jpg"})["error"]["code"] == "network"


# --- остановка ---

def test_close_quits_chrome_without_waiting_for_running_work(tmp_path):
    harness = Harness(tmp_path)
    harness.driver.current_url = "https://s/1"
    release = threading.Event()
    started = threading.Event()

    def slow_fetch(url, driver):
        started.set()
        release.wait(5)
        return scraper.MovieDetails(title="Т", url=url, description="d")

    with mock.patch.object(be.scraper, "fetch_movie_details", side_effect=slow_fetch):
        harness.backend.handle_line(json.dumps({"id": 1, "method": "movie", "params": {"url": "https://s/1"}}))
        assert started.wait(2)
        harness.backend.close()
        harness.driver.quit.assert_called_once()
        release.set()


def test_close_without_driver_does_not_create_one(tmp_path):
    harness = Harness(tmp_path)
    harness.backend.close()
    assert harness.created == 0


SERIES = scraper.SeriesInfo(
    seasons=[scraper.Season("2", "Сезон 2", [scraper.Episode("3", "Серия 3")])],
    season="2",
    episode="3",
)
SERIES_URL = "https://rezka.test/series/1.html"


def _episode_details(streams=None, series=SERIES):
    return scraper.MovieDetails(
        title="",
        url=SERIES_URL,
        translators=[scraper.Translator("12", "Амедиа", True)],
        active_translator_id="12",
        streams={"1080p": ["https://s/e.m3u8"]} if streams is None else streams,
        series=series,
    )


def _ask_episode(h, request_id=1, **params):
    base = {"url": SERIES_URL, "source": "hdrezka", "translator_id": "12", "season": "2", "episode": "3"}
    return h.call("episode", {**base, **params}, request_id=request_id)


def test_episode_returns_streams_and_lists(h):
    h.driver.current_url = SERIES_URL
    with mock.patch.object(be.scraper, "fetch_episode", return_value=_episode_details()) as fetch:
        result = _ask_episode(h)["result"]
    assert fetch.call_args.args[2:] == ("12", "2", "3")
    assert result["streams"] == {"1080p": ["https://s/e.m3u8"]}
    assert result["active_translator_id"] == "12"
    assert result["translators"][0]["name"] == "Амедиа"
    assert result["series"]["season"] == "2" and result["series"]["moved"] is False


def test_episode_opens_page_when_driver_moved(h):
    h.driver.current_url = "about:blank"
    with mock.patch.object(be.scraper, "fetch_movie_details") as page, \
        mock.patch.object(be.scraper, "fetch_episode", return_value=_episode_details()):
        _ask_episode(h)
    page.assert_called_once()


def test_episode_without_video_is_no_streams(h):
    h.driver.current_url = SERIES_URL
    with mock.patch.object(be.scraper, "fetch_episode", return_value=_episode_details(streams={})):
        assert _ask_episode(h)["error"]["code"] == "no_streams"


def test_episode_requires_season(h):
    assert h.call("episode", {"url": SERIES_URL})["error"]["code"] == "invalid_params"


def test_episode_cache_separates_episodes_and_voices(h):
    h.driver.current_url = SERIES_URL
    with mock.patch.object(be.scraper, "fetch_episode", return_value=_episode_details()) as fetch:
        _ask_episode(h, 1)
        _ask_episode(h, 2)
        assert fetch.call_count == 1
        _ask_episode(h, 3, episode="4")
        assert fetch.call_count == 2
        _ask_episode(h, 4, translator_id="80")
        assert fetch.call_count == 3


def test_episode_on_kinogo_passes_selection(h):
    details = _kinogo_details({"1080p": ["https://atlas/e.m3u8"]})
    details.series = SERIES
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=details) as fetch:
        result = h.call("episode", {"url": KINOGO_MOVIE, "source": "kinogo", "season": "2", "episode": "3", "translator_id": "Гоблин"})["result"]
    assert fetch.call_args.kwargs["season"] == "2"
    assert fetch.call_args.kwargs["episode"] == "3"
    assert fetch.call_args.kwargs["voice"] == "Гоблин"
    assert result["streams"] == {"1080p": ["https://atlas/e.m3u8"]}


def test_episode_on_kinogo_without_video_is_no_streams(h):
    with mock.patch.object(be.kinogo, "fetch_movie", side_effect=be.kinogo.NoVideo("нет")):
        error = h.call("episode", {"url": KINOGO_MOVIE, "source": "kinogo", "season": "2"})["error"]
    assert error["code"] == "no_streams"


def test_refresh_keeps_selected_episode(h):
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=_kinogo_details()) as fetch, \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0):
        h.call("play", {"title": "К", "urls": ["https://atlas/old.m3u8"], "movie_url": KINOGO_MOVIE,
                        "quality": "1080p", "voice": "Гоблин", "season": "2", "episode": "3"})
        h.event("playback_finished")
    assert fetch.call_args.kwargs["season"] == "2"
    assert fetch.call_args.kwargs["episode"] == "3"


def test_film_refresh_does_not_pass_episode(h):
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=_kinogo_details()) as fetch, \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", return_value=0):
        h.call("play", {"title": "К", "urls": ["https://atlas/old.m3u8"], "movie_url": KINOGO_MOVIE, "quality": "1080p"})
        h.event("playback_finished")
    assert "season" not in fetch.call_args.kwargs


def test_forget_page_removes_page_opened_instead_of_kinogo(h):
    h.backend._remember(("movie", KINOGO_MOVIE, None, "kinogo"), {"url": SERIES_URL})
    h.backend._remember(("movie", "https://other", None, "kinogo"), {"url": "https://other"})
    h.backend._forget_page(SERIES_URL)
    assert h.backend._cached(("movie", KINOGO_MOVIE, None, "kinogo")) is None
    assert h.backend._cached(("movie", "https://other", None, "kinogo")) is not None


def test_episode_on_kinogo_requires_only_voice_chosen_by_viewer(h):
    details = _kinogo_details({"1080p": ["https://atlas/e.m3u8"]})
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=details) as fetch:
        base = {"url": KINOGO_MOVIE, "source": "kinogo", "season": "1", "translator_id": "Кравец"}
        h.call("episode", base, request_id=1)
        assert fetch.call_args.kwargs["strict"] is True
        h.call("episode", {**base, "voice_optional": True}, request_id=2)
        assert fetch.call_args.kwargs["strict"] is False
    assert fetch.call_count == 2


def test_episode_request_failure_is_network_error(h):
    h.driver.current_url = SERIES_URL
    with mock.patch.object(be.scraper, "fetch_episode", side_effect=scraper.SiteUnavailable("нет ответа")):
        assert _ask_episode(h)["error"]["code"] == "network"


def test_refresh_does_not_start_other_episode_under_old_title(h):
    details = _kinogo_details()
    details.series = scraper.SeriesInfo(seasons=[], season="2", episode="2", moved=True)
    with mock.patch.object(be.kinogo, "fetch_movie", return_value=details), \
        mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback") as run:
        answer = h.call("play", {"title": "К", "urls": ["https://atlas/old.m3u8"], "movie_url": KINOGO_MOVIE,
                                 "quality": "1080p", "season": "2", "episode": "3"})
    assert answer["error"]["code"] == "no_streams"
    run.assert_not_called()


def _play_embedded(h, request_id=1, **extra):
    return h.call("play", {"title": "К", "urls": ["https://s/1.m3u8"], "progress_id": f"p{request_id}", **extra}, request_id=request_id)


@pytest.mark.parametrize("wid", [0, -5, "12", True, 1.5])
def test_play_rejects_bad_window_id(h, wid):
    assert _play_embedded(h, wid=wid)["error"]["code"] == "invalid_params"


def test_window_id_reaches_player_only_on_windows(h, monkeypatch):
    plans = []

    def run(plan, *_args, **_kwargs):
        plans.append(plan)
        return 0

    monkeypatch.setattr(be.platform, "system", lambda: "Linux")
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run), \
        mock.patch.object(be.player_ipc, "watch"):
        _play_embedded(h, 1, wid=77)
        h.wait_for(lambda m: m.get("event") == "playback_finished" and m["data"].get("id") == "p1")
        monkeypatch.setattr(be.platform, "system", lambda: "Windows")
        _play_embedded(h, 2, wid=77)
        h.wait_for(lambda m: m.get("event") == "playback_finished" and m["data"].get("id") == "p2")
    assert not [a for a in plans[0].mpv_args if a.startswith("--wid")]
    assert "--wid=77" in plans[1].mpv_args


def test_new_embedded_start_and_stop_end_previous_player(h, monkeypatch):
    monkeypatch.setattr(be.platform, "system", lambda: "Windows")
    release = threading.Event()
    processes = []

    def run(_plan, *_args, on_process=None, **_kwargs):
        process = mock.Mock()
        process.terminate.side_effect = release.set
        processes.append(process)
        on_process(process)
        release.wait(5)
        release.clear()
        return 1

    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run), \
        mock.patch.object(be.player_ipc, "watch"):
        _play_embedded(h, 1, wid=77)
        while not processes:
            pass
        _play_embedded(h, 2, wid=77)
        h.wait_for(lambda m: m.get("event") == "playback_finished" and m["data"].get("id") == "p1")
        processes[0].terminate.assert_called()
        while len(processes) < 2:
            pass
        assert h.call("player_stop", {}, request_id=3)["result"] == {"ok": True}
        h.wait_for(lambda m: m.get("event") == "playback_finished" and m["data"].get("id") == "p2")
    # Остановка намеренная: это не сбой воспроизведения.
    assert not [m for m in h.lines if m.get("event") == "playback_failed"]


def test_closing_app_stops_embedded_player_but_not_separate_window(h):
    opening = be._Opening()
    opening.process = mock.Mock()
    h.backend._embedded = opening
    h.backend.close()
    opening.process.terminate.assert_called_once()


def test_resume_continues_from_last_position_only_when_asked(h, monkeypatch):
    monkeypatch.setattr(be.platform, "system", lambda: "Windows")
    plans = []

    def run(plan, *_args, **_kwargs):
        plans.append(plan)
        return 0

    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run), \
        mock.patch.object(be.player_ipc, "watch"):
        h.backend._embedded_position = 83.5
        _play_embedded(h, 1, wid=77, resume=True)
        h.wait_for(lambda m: m.get("event") == "playback_finished" and m["data"].get("id") == "p1")
        h.backend._embedded_position = 83.5
        _play_embedded(h, 2, wid=77)
        h.wait_for(lambda m: m.get("event") == "playback_finished" and m["data"].get("id") == "p2")
    assert "--start=83.500" in plans[0].mpv_args
    assert not [a for a in plans[1].mpv_args if a.startswith("--start")]


def test_no_player_starts_while_app_is_closing(h):
    h.backend._closing = True
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback") as run:
        answer = _play_embedded(h, 1, wid=77)
    assert answer["error"]["code"] == "internal"
    run.assert_not_called()


# --- мой список ---

WATCH_FILM = {"title": "Матрица", "orig_title": "The Matrix", "year": "1999", "kind": "film",
              "url": "https://uakinogo.io/filmy/1-matrica.html", "poster_url": None}
WATCH_SERIES = {**WATCH_FILM, "title": "Проект Лазарь", "orig_title": "The Lazarus Project", "year": "2022",
                "kind": "series", "url": "https://uakinogo.io/serialy/2-lazar.html"}


def test_watchlist_status_get_remove(h):
    assert h.call("watchlist_get", {"title": WATCH_FILM})["result"] == {"entry": None}
    entry = h.call("watchlist_set_status", {"title": WATCH_FILM, "status": "planned"}, 2)["result"]["entry"]
    assert entry["status"] == "planned" and "fallback_key" not in entry
    # Тот же тайтл с другого зеркала — та же запись.
    other = {**WATCH_FILM, "url": "https://kinogo.zone/filmy/1-matrica.html"}
    assert h.call("watchlist_get", {"title": other}, 3)["result"]["entry"]["status"] == "planned"
    assert h.call("watchlist_remove", {"title": WATCH_FILM}, 4)["result"] == {"entry": None}
    assert h.call("watchlist_list", {}, 5)["result"] == {"items": []}


@pytest.mark.parametrize("method, params", [
    ("watchlist_set_status", {"title": WATCH_FILM, "status": "dropped"}),
    ("watchlist_set_status", {"title": {**WATCH_FILM, "url": "x"}, "status": "planned"}),
    ("watchlist_get", {}),
    ("watchlist_set_episode", {"title": WATCH_FILM, "season": "1", "episode": "1", "watched": True}),
    ("watchlist_set_episode", {"title": WATCH_SERIES, "season": "1", "episode": "1", "watched": "да"}),
])
def test_watchlist_invalid_params(h, method, params):
    assert h.call(method, params)["error"]["code"] == "invalid_params"


def test_watchlist_list_and_episodes(h):
    h.call("watchlist_set_status", {"title": WATCH_FILM, "status": "completed"})
    entry = h.call("watchlist_set_episode",
                   {"title": WATCH_SERIES, "season": "1", "episode": "3", "watched": True}, 2)["result"]["entry"]
    assert entry["episodes"] == {"1": ["3"]} and entry["status"] == "watching"
    items = h.call("watchlist_list", {}, 3)["result"]["items"]
    assert [i["kind"] for i in items] == ["series", "film"]


def test_watchlist_reset_warning_once(tmp_path):
    (tmp_path / "watchlist.json").write_text("мусор", encoding="utf-8")
    harness = Harness(tmp_path)
    try:
        assert harness.call("watchlist_list", {})["result"] == {"items": [], "warning": "watchlist_reset"}
        assert harness.call("watchlist_list", {}, 2)["result"] == {"items": []}
    finally:
        harness.backend.close()


def test_watchlist_resolve_moves_to_imdb_id(h):
    h.call("watchlist_set_status", {"title": WATCH_FILM, "status": "planned"})
    with mock.patch.object(be.imdb, "find_id", return_value="tt0133093") as find:
        result = h.call("watchlist_resolve", {"title": WATCH_FILM}, 2)["result"]
        assert result["key"] == "tt0133093" and result["entry"]["status"] == "planned"
        # Найденный id запомнен: повторного запроса нет.
        h.call("watchlist_resolve", {"title": WATCH_FILM}, 3)
    assert find.call_count == 1
    find.assert_called_with("The Matrix", "1999", "film")


def test_watchlist_resolve_network_failure_keeps_fallback(h):
    with mock.patch.object(be.imdb, "find_id", side_effect=be.imdb.Unavailable("сеть")) as find:
        result = h.call("watchlist_resolve", {"title": WATCH_FILM})["result"]
        assert result == {"entry": None, "key": "t:film:1999:the matrix"}
        h.call("watchlist_resolve", {"title": WATCH_FILM}, 2)
    # Сбой сети не запоминается как «не найдено».
    assert find.call_count == 2


def _fake_ipc(position=None, duration=None, eof=False):
    """Канал управления, который сообщает позицию, длительность и конец файла."""

    def watch(_path, _fullscreen, on_position, _stop, on_duration=None, on_eof=None):
        if duration is not None:
            on_duration(duration)
        if position is not None:
            on_position(position)
        if eof:
            on_eof()

    return watch


def _play_watched(h, monkeypatch, watch, ipc, code=0, request_id=1):
    monkeypatch.setattr(be.platform, "system", lambda: "Windows")
    gate = threading.Event()
    plans = []

    def run(plan, *_args, **_kwargs):
        plans.append(plan)
        gate.wait(5)  # канал успевает сообщить позицию до завершения mpv
        return code

    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run), \
        mock.patch.object(be.player_ipc, "watch", side_effect=ipc):
        result = h.call("play", {"title": "К", "urls": ["https://s/1.m3u8"], "watch": watch}, request_id=request_id)
        gate.set()
        h.wait_for(lambda m: m.get("event") in ("playback_finished", "playback_failed"))
    return result, plans


def _events(h, name):
    return [m["data"] for m in h.lines if m.get("event") == name]


def test_play_with_watch_marks_watching_and_completion(h, monkeypatch):
    watch = {"title": WATCH_FILM, "final": True}
    result, plans = _play_watched(h, monkeypatch, watch, _fake_ipc(position=96, duration=100))
    assert result["result"] == {"started": True}
    assert any(a.startswith("--input-ipc-server=") for a in plans[0].mpv_args)
    assert not any(a.startswith("--wid") for a in plans[0].mpv_args)
    assert _events(h, "watchlist_changed")[0]["entry"]["status"] == "watching"
    h.event("watch_completed")
    done = _events(h, "watch_completed")
    assert len(done) == 1 and done[0]["final"] is True and done[0]["key"] == "t:film:1999:the matrix"


def test_interrupted_play_is_not_completed(h, monkeypatch):
    _play_watched(h, monkeypatch, {"title": WATCH_FILM, "final": True}, _fake_ipc(position=50, duration=100))
    assert _events(h, "watch_completed") == []


def test_failed_play_is_not_completed(h, monkeypatch):
    _play_watched(h, monkeypatch, {"title": WATCH_FILM, "final": True}, _fake_ipc(eof=True),
                  code=runner.MPV_EXIT_LOAD_FAILED)
    # Конец файла пришёл раньше сбоя: он засчитан один раз, после сбоя повторно не сообщается.
    assert len(_events(h, "watch_completed")) <= 1


def test_episode_marked_on_end_of_file(h, monkeypatch):
    watch = {"title": WATCH_SERIES, "season": "1", "episode": "6", "final": False}
    _play_watched(h, monkeypatch, watch, _fake_ipc(eof=True))
    h.event("watch_completed")
    assert _events(h, "watch_completed")[0]["final"] is False
    entry = h.call("watchlist_get", {"title": WATCH_SERIES}, 9)["result"]["entry"]
    assert entry["episodes"] == {"1": ["6"]} and entry["status"] == "watching"


def test_completed_status_kept_on_replay(h, monkeypatch):
    h.call("watchlist_set_status", {"title": WATCH_FILM, "status": "completed"}, 7)
    _play_watched(h, monkeypatch, {"title": WATCH_FILM}, _fake_ipc())
    assert h.call("watchlist_get", {"title": WATCH_FILM}, 8)["result"]["entry"]["status"] == "completed"


@pytest.mark.parametrize("watch", [
    "да", {"title": {**WATCH_FILM, "kind": "x"}}, {"title": WATCH_SERIES, "season": "1"},
    {"title": WATCH_FILM, "final": "yes"},
])
def test_bad_watch_does_not_block_playback(h, monkeypatch, watch):
    result, plans = _play_watched(h, monkeypatch, watch, _fake_ipc(position=96, duration=100))
    assert result["result"] == {"started": True} and plans
    assert _events(h, "watchlist_changed") == [] and _events(h, "watch_completed") == []


def test_stream_cut_short_is_not_completed(h, monkeypatch):
    # Обрыв потока на 20%: mpv сообщает конец файла, но фильм не досмотрен.
    _play_watched(h, monkeypatch, {"title": WATCH_FILM, "final": True}, _fake_ipc(position=20, duration=100, eof=True))
    assert _events(h, "watch_completed") == []


def test_watching_is_set_only_after_video_starts(h, monkeypatch):
    _play_watched(h, monkeypatch, {"title": WATCH_FILM, "final": True}, _fake_ipc(), code=runner.MPV_EXIT_LOAD_FAILED)
    assert h.call("watchlist_get", {"title": WATCH_FILM}, 9)["result"]["entry"] is None


def test_completed_title_is_not_offered_again(h, monkeypatch):
    h.call("watchlist_set_status", {"title": WATCH_FILM, "status": "completed"}, 7)
    _play_watched(h, monkeypatch, {"title": WATCH_FILM, "final": True}, _fake_ipc(position=99, duration=100))
    h.event("watch_completed")
    assert _events(h, "watch_completed")[0]["final"] is False


def test_watchlist_changes_are_announced(h):
    h.call("watchlist_set_status", {"title": WATCH_FILM, "status": "planned"})
    h.call("watchlist_remove", {"title": WATCH_FILM}, 2)
    changed = _events(h, "watchlist_changed")
    assert changed[0]["entry"]["status"] == "planned" and changed[1] == {"entry": None}


def test_play_with_watch_tracks_on_macos(h, monkeypatch):
    plans = []

    def run(plan, *_args, **_kwargs):
        plans.append(plan)
        return 0

    monkeypatch.setattr(be.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(be.player_ipc.platform, "system", lambda: "Darwin")
    with mock.patch.object(be.locate, "find_mpv", return_value="mpv"), \
        mock.patch.object(be.runner, "run_with_fallback", side_effect=run), \
        mock.patch.object(be.player_ipc, "watch", side_effect=_fake_ipc(eof=True)):
        h.call("play", {"title": "К", "urls": ["https://s/1.m3u8"], "watch": {"title": WATCH_FILM, "final": True}})
        h.event("watch_completed")
    assert any(a.startswith("--input-ipc-server=/tmp/mpv-cinema-") for a in plans[0].mpv_args)


# --- аккаунт Google ---


class FakeAccount:
    def __init__(self, on_change, restore=False, configured=True):
        self.on_change = on_change
        self.restore_needed = restore
        self.configured = configured
        self.restored = threading.Event()
        self.state = {"state": "signed_out", "account": None, "storage_warning": False, "message": None}

    def snapshot(self):
        return dict(self.state)

    def start_restore(self):
        needed, self.restore_needed = self.restore_needed, False
        if needed:
            self.state["state"] = "restoring"
        return needed

    def restore(self):
        self.state["state"] = "signed_in"
        self.on_change(self.snapshot())
        self.restored.set()

    def sign_in(self):
        if not self.configured:
            raise be.google_auth.Unconfigured
        self.state["state"] = "pending"
        return self.snapshot()

    def cancel(self):
        self.state["state"] = "signed_out"
        return self.snapshot()

    def sign_out(self):
        self.state["state"] = "signed_out"
        self.on_change(self.snapshot())
        return self.snapshot()

    def access_token(self):
        raise be.google_auth.Offline


def _account_harness(tmp_path, **kwargs):
    harness = Harness.__new__(Harness)
    harness.lines = []
    harness.received = threading.Condition()
    harness.driver = mock.Mock()
    harness.created = 0
    created = []

    def factory(on_change):
        created.append(FakeAccount(on_change, **kwargs))
        return created[0]

    harness.backend = be.Backend(
        write=harness._write,
        driver_factory=harness._factory,
        settings_path=tmp_path / "settings.json",
        poster_dir=tmp_path / "posters",
        account_factory=factory,
    )
    return harness, created[0]


def test_account_get_starts_restore_once(tmp_path):
    h, account = _account_harness(tmp_path, restore=True)
    try:
        assert h.call("account_get")["result"]["state"] == "restoring"
        assert h.event("account_changed")["data"]["state"] == "signed_in"
        assert h.call("account_get", request_id=2)["result"]["state"] == "signed_in"
    finally:
        h.backend.close()


def test_account_sign_in_cancel_and_sign_out(tmp_path):
    h, account = _account_harness(tmp_path)
    try:
        assert h.call("account_sign_in")["result"]["state"] == "pending"
        assert h.call("account_cancel", request_id=2)["result"]["state"] == "signed_out"
        assert h.call("account_sign_out", request_id=3)["result"]["state"] == "signed_out"
        assert h.event("account_changed")["data"]["state"] == "signed_out"
    finally:
        h.backend.close()


def test_account_sign_in_unconfigured(tmp_path):
    h, _ = _account_harness(tmp_path, configured=False)
    try:
        assert h.call("account_sign_in")["error"]["code"] == "unconfigured"
    finally:
        h.backend.close()


def test_access_token_maps_errors(tmp_path):
    h, _ = _account_harness(tmp_path)
    try:
        with pytest.raises(be.ApiError) as error:
            h.backend.access_token()
        assert error.value.code == "offline"
    finally:
        h.backend.close()


def test_default_account_files_live_next_to_settings(tmp_path):
    backend = be.Backend(write=lambda _: None, settings_path=tmp_path / "settings.json", poster_dir=tmp_path / "cache" / "posters")
    try:
        assert backend._account._profiles.path == tmp_path / "account.json"
        assert backend._account._avatar_path == tmp_path / "cache" / "avatar.jpg"
    finally:
        backend.close()


class FakeSyncer:
    def __init__(self, on_state, on_reloaded):
        self.on_state = on_state
        self.on_reloaded = on_reloaded
        self.enabled_for = []
        self.disabled = []
        self.changes = 0
        self.enabled = False
        self.stopped = False

    def snapshot(self):
        return {"state": "idle" if self.enabled else "disabled", "pending": False, "last_synced_at": None, "message": None}

    def enable(self, email):
        self.enabled = True
        self.enabled_for.append(email)

    def disable(self, auth_required=False):
        self.enabled = False
        self.disabled.append(auth_required)

    def request(self):
        return self.enabled

    def local_changed(self):
        self.changes += 1

    def stop(self):
        self.stopped = True


def _sync_harness(tmp_path):
    harness, account = _account_harness(tmp_path)
    syncers = []

    def factory(on_state, on_reloaded):
        syncers.append(FakeSyncer(on_state, on_reloaded))
        return syncers[0]

    harness.backend.close()
    harness.lines = []
    accounts = []

    def account_factory(on_change):
        accounts.append(FakeAccount(on_change))
        return accounts[0]

    harness.backend = be.Backend(
        write=harness._write,
        driver_factory=harness._factory,
        settings_path=tmp_path / "settings.json",
        poster_dir=tmp_path / "posters",
        account_factory=account_factory,
        syncer_factory=factory,
    )
    return harness, accounts[0], syncers[0]


def test_sync_follows_account_state(tmp_path):
    h, account, syncer = _sync_harness(tmp_path)
    try:
        assert h.call("sync_get")["result"]["state"] == "disabled"
        assert h.call("sync_now", request_id=2)["error"]["code"] == "signed_out"
        account.on_change({"state": "signed_in", "account": {"email": "u@example.com"}})
        assert syncer.enabled_for == ["u@example.com"]
        assert h.call("sync_now", request_id=3)["result"]["state"] == "idle"
        account.on_change({"state": "expired", "account": None})
        account.on_change({"state": "signed_out", "account": None})
        assert syncer.disabled == [True, False]
    finally:
        h.backend.close()
    assert syncer.stopped


def test_sync_events_and_watchlist_changes(tmp_path):
    h, _account, syncer = _sync_harness(tmp_path)
    try:
        h.call("watchlist_set_status", {"title": SYNC_TITLE, "status": "planned"})
        assert syncer.changes == 1
        syncer.on_state({"state": "syncing", "pending": True, "last_synced_at": None, "message": None})
        assert h.event("sync_changed")["data"]["state"] == "syncing"
        syncer.on_reloaded()
        assert h.event("watchlist_reloaded")["data"] == {}
    finally:
        h.backend.close()


def test_default_syncer_store_next_to_watchlist(tmp_path):
    backend = be.Backend(write=lambda _: None, settings_path=tmp_path / "settings.json", poster_dir=tmp_path / "posters")
    try:
        assert backend._syncer._store.path == tmp_path / "sync.json"
    finally:
        backend.close()


SYNC_TITLE = {"title": "Фильм", "orig_title": "Film", "year": "2020", "kind": "film", "url": "https://example.com/f"}
