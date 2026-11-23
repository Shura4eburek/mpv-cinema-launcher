"""KinoGo: разбор страниц, подписи по реальной ширине, порядок адресов, отсев не-фильмов."""

from types import SimpleNamespace
from unittest import mock

import pytest

from mpv_launcher import kinogo, scraper

BASE = "https://kinogo.test"
SIGNED = "https://cfnd.cinemap.cc/1793-SIGN%3D/movies/abc/tok:2026/hls-v1-a3.m3u8"
ATLAS = "https://atlas.host.cinemap.cc/movies/abc/tok:2026"

SEARCH_HTML = """
<aside><a href="/novinki/1-sidebar.html" title="Чужой (2020)">Чужой</a></aside>
<div id="dle-content">
  <article class="shortStory">
    <h2><a href="https://kinogo.test/filmy/12-gladiator.html" title="Гладиатор (2000)">Гладиатор (2000) </a></h2>
    <div class="sPoster"><img class="lazy" data-src="/uploads/g.jpg" src="data:image/gif;base64,x"/></div>
    <div class="sInfo"><span><b>Рік випуску:</b><a>2000</a></span></div>
  </article>
  <article class="shortStory">
    <h2><a href="/filmy/13-gladiator-2.html">Гладиатор 2 (2024)</a></h2>
  </article>
</div>
"""
EMPTY_HTML = '<div id="dle-content">Ничего не найдено</div>'
MOVIE_HTML = """
<article class="fullStory">
  <h1>Гладиатор (2000) </h1>
  <div class="sPoster"><img src="/uploads/full.jpg"/></div>
  <div class="sInfo">
    <span><b>Рік випуску:</b><a>2000</a></span>
    <span><b>Зарубіжна назва:</b>Gladiator</span>
    <span><b>Країна:</b><a>Марокко</a> / <a>США</a></span>
    <span><b>Жанр:</b><a>Драма</a></span>
    <div class="fullRatings"><div><b>КиноПоиск:</b>8.6</div><div><b>IMDB:</b>8.50</div></div>
    <div class="castInfo"><span><b>Режисер:</b>Ридли Скотт</span><span><b>Актори:</b>Рассел Кроу</span></div>
  </div>
  <div class="sDesc">Римский генерал становится гладиатором и возвращается, чтобы отомстить императору за свою семью.</div>
</article>
"""
MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=352000,RESOLUTION=426x240
./240.mp4:hls:manifest-v1-a3.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2692000,RESOLUTION=1280x534
./720.mp4:hls:manifest-v1-a3.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5192000,RESOLUTION=1920x800
./1080.mp4:hls:manifest-v1-a3.m3u8
"""


def _media(seconds=7200):
    return "#EXTM3U\n" + f"#EXTINF:{seconds}.0,\nseg.ts\n#EXT-X-ENDLIST\n"


def _resp(text="", status=200, url=""):
    return SimpleNamespace(status_code=status, ok=status < 400, text=text, url=url, encoding=None)


def _network(fail_atlas=False, seconds=7200):
    def get(url, **_kwargs):
        if url.endswith("/hls-v1-a3.m3u8"):
            return _resp(MASTER, url=url)
        if "atlas.host" in url:
            if fail_atlas:
                raise kinogo.requests.ConnectionError()
            return _resp(_media(seconds), url=url.replace("atlas.host", "emerald.host"))
        return _resp(_media(seconds), url=url)

    return mock.patch.object(kinogo.requests, "get", side_effect=get)


def test_search_reads_only_results_and_makes_full_urls():
    with mock.patch.object(kinogo.requests, "get", return_value=_resp(SEARCH_HTML)) as get:
        cards = kinogo.search("Гладиатор", BASE)
    assert "story=" in get.call_args.args[0]
    assert [c.title for c in cards] == ["Гладиатор (2000)", "Гладиатор 2 (2024)"]
    assert cards[0].url == "https://kinogo.test/filmy/12-gladiator.html"
    assert cards[1].url == "https://kinogo.test/filmy/13-gladiator-2.html"
    assert cards[0].poster_url == "https://kinogo.test/uploads/g.jpg"
    assert cards[0].info == "2000"
    assert cards[1].info == "2024"
    assert all(c.source == "kinogo" for c in cards)


def test_relative_addresses_use_the_site_of_the_card():
    page = '<article class="fullStory"><h1>Т</h1><div class="sPoster"><img src="/p.jpg"/></div></article>'
    with mock.patch.object(kinogo, "_get_page", return_value=page):
        with pytest.raises(kinogo.NoVideo) as failure:
            kinogo.fetch_movie("https://other.test/filmy/1.html", mock.Mock(), BASE)
    assert failure.value.details.poster_url == "https://other.test/p.jpg"


def test_player_is_found_by_container_without_lazy_class():
    frame = mock.Mock()
    frame.get_attribute.side_effect = lambda name: {"class": "", "src": "https://cinemar.cc/embed/1"}[name]
    driver = mock.Mock()
    driver.find_elements.return_value = [frame]
    with mock.patch.object(kinogo, "_wait_for_master", return_value=None), \
        mock.patch.object(kinogo, "ActionChains"), \
        mock.patch.object(kinogo.time, "sleep"):
        with pytest.raises(kinogo.NoVideo, match="плеер не выдал поток"):
            kinogo.capture_stream(driver, f"{BASE}/1.html")
    driver.execute_script.assert_any_call("arguments[0].scrollIntoView({block:'center'})", frame)


def test_search_with_no_results_is_empty():
    with mock.patch.object(kinogo.requests, "get", return_value=_resp(EMPTY_HTML)):
        assert kinogo.search("zzz", BASE) == []


@pytest.mark.parametrize("response", [_resp("", 503), _resp("<html>Just a moment...</html>")])
def test_search_blocked_or_broken_page_is_unavailable(response):
    with mock.patch.object(kinogo.requests, "get", return_value=response):
        with pytest.raises(scraper.SiteUnavailable):
            kinogo.search("x", BASE)


def test_search_network_error_is_unavailable():
    with mock.patch.object(kinogo.requests, "get", side_effect=kinogo.requests.ConnectionError()):
        with pytest.raises(scraper.SiteUnavailable):
            kinogo.search("x", BASE)


def test_parse_movie_page():
    details = kinogo.parse_movie(MOVIE_HTML, f"{BASE}/filmy/12.html", BASE)
    assert details.title == "Гладиатор (2000)"
    assert details.orig_title == "Gladiator"
    assert details.poster_url == "https://kinogo.test/uploads/full.jpg"
    assert details.description.startswith("Римский генерал")
    assert details.info_table["Год"] == "2000"
    assert details.info_table["Страна"] == "Марокко / США"
    assert details.info_table["Жанр"] == "Драма"
    assert details.info_table["Режиссер"] == "Ридли Скотт"
    assert details.info_table["Рейтинги"] == "КиноПоиск: 8.6, IMDb: 8.50"
    assert details.source == "kinogo"


@pytest.mark.parametrize(
    ("width", "label"),
    [(1920, "1080p"), (1916, "1080p"), (1280, "720p"), (854, "480p"), (640, "360p"), (426, "240p"), (3840, "2160p")],
)
def test_label_is_based_on_width(width, label):
    assert kinogo.label_for_width(width) == label


def test_streams_prefer_checked_node_then_atlas_then_player_server():
    with _network():
        streams = kinogo.build_streams(SIGNED)
    assert list(streams) == ["240p", "720p", "1080p"]
    name = "1080.mp4:hls:manifest-v1-a3.m3u8"
    assert streams["1080p"] == [
        f"https://emerald.host.cinemap.cc/movies/abc/tok:2026/{name}",
        f"{ATLAS}/{name}",
        f"https://cfnd.cinemap.cc/1793-SIGN%3D/movies/abc/tok:2026/{name}",
    ]


def test_unreachable_full_quality_server_is_not_labelled_as_full_hd():
    with _network(fail_atlas=True):
        streams = kinogo.build_streams(SIGNED)
    assert streams == {kinogo.UNCONFIRMED: [SIGNED]}


def test_dead_full_hd_node_hides_that_variant_and_keeps_the_rest():
    def get(url, **_kwargs):
        if url.endswith("/hls-v1-a3.m3u8"):
            return _resp(MASTER, url=url)
        if "atlas.host" in url and "1080.mp4" in url:
            raise kinogo.requests.ConnectTimeout()
        return _resp(_media(), url=url)

    with mock.patch.object(kinogo.requests, "get", side_effect=get):
        streams = kinogo.build_streams(SIGNED)
    assert list(streams) == ["240p", "720p"]


def test_transient_failure_does_not_cost_full_hd():
    attempts = {}

    def get(url, **_kwargs):
        if url.endswith("/hls-v1-a3.m3u8"):
            return _resp(MASTER, url=url)
        attempts[url] = attempts.get(url, 0) + 1
        if "atlas.host" in url and attempts[url] == 1:
            raise kinogo.requests.ConnectionError()
        return _resp(_media(), url=url)

    with mock.patch.object(kinogo.requests, "get", side_effect=get):
        assert "1080p" in kinogo.build_streams(SIGNED)


def test_short_video_is_not_a_movie():
    with _network(seconds=90):
        with pytest.raises(kinogo.NoVideo):
            kinogo.build_streams(SIGNED)


def test_master_failure_is_no_video():
    with mock.patch.object(kinogo.requests, "get", return_value=_resp("", 403)):
        with pytest.raises(kinogo.NoVideo):
            kinogo.build_streams(SIGNED)


def test_fetch_movie_without_player_frame_is_no_video():
    page = _resp(MOVIE_HTML)
    with mock.patch.object(kinogo.requests, "get", return_value=page):
        with pytest.raises(kinogo.NoVideo):
            kinogo.fetch_movie(f"{BASE}/filmy/12.html", mock.Mock(), BASE)


def test_fetch_movie_combines_page_stream_and_voice():
    page = _resp(MOVIE_HTML.replace("</article>", '<div class="js-player-container"><iframe data-src="https://cinemar.cc/e/1"></iframe></div></article>'))
    streams = {"1080p": ["https://a/1.m3u8"]}
    with mock.patch.object(kinogo.requests, "get", return_value=page), \
        mock.patch.object(kinogo, "capture_stream", return_value=kinogo.Captured(SIGNED, "Гаврилов", ["Дубляж", "Гаврилов"])) as capture, \
        mock.patch.object(kinogo, "build_streams", return_value=streams):
        details = kinogo.fetch_movie(f"{BASE}/filmy/12.html", mock.Mock(), BASE, voice="Гаврилов")
    assert capture.call_args.args[2] == "Гаврилов"
    assert details.streams == streams
    assert details.referer == "https://cinemar.cc/"
    assert [t.name for t in details.translators] == ["Дубляж", "Гаврилов"]
    assert [t.active for t in details.translators] == [False, True]
    assert details.active_translator_id == "Гаврилов"
    assert details.translators[1].id == "Гаврилов"


def test_unexpected_player_failure_becomes_no_video_with_details():
    page = _resp(MOVIE_HTML.replace("</article>", '<div class="js-player-container"><iframe data-src="https://cinemar.cc/e/1"></iframe></div></article>'))
    with mock.patch.object(kinogo.requests, "get", return_value=page), \
        mock.patch.object(kinogo, "capture_stream", side_effect=ValueError("новый формат")):
        with pytest.raises(kinogo.NoVideo) as error:
            kinogo.fetch_movie(f"{BASE}/filmy/12.html", mock.Mock(), BASE)
    assert error.value.details.title == "Гладиатор (2000)"


def test_chrome_start_failure_is_not_swallowed():
    def no_chrome():
        raise RuntimeError("нет Chrome")

    with pytest.raises(RuntimeError):
        kinogo.capture_stream(None, f"{BASE}/1.html", get_driver=no_chrome)


def test_voice_list_removes_blanks_and_duplicates():
    assert kinogo.voices_from_list(["Дубляж", "", "Дубляж", "Гаврилов"]) == ["Дубляж", "Гаврилов"]


def test_page_request_is_retried_once():
    page = _resp(EMPTY_HTML)
    with mock.patch.object(kinogo.requests, "get", side_effect=[kinogo.requests.ConnectionError(), page]):
        assert kinogo.search("x", BASE) == []


@pytest.mark.parametrize(
    ("text", "voice"),
    [
        ("0:00 / 02:30:09 Масштаб 100% Скорость Обычная Дубляж (iTunes) Реклама 1/2 Пропустить через 5", "Дубляж (iTunes)"),
        ("Скорость Обычная Дубляж", "Дубляж"),
        ("без подписи", None),
    ],
)
def test_voice_name_from_player_text(text, voice):
    assert kinogo.voice_from_text(text) == voice


ATLAS_URL = "https://atlas.host/hls/index.m3u8"


def test_dead_atlas_node_is_not_retried():
    with mock.patch.object(kinogo.requests, "get", side_effect=kinogo.requests.ConnectTimeout()) as get:
        assert kinogo._fetch_with_retries(ATLAS_URL) is None
    assert get.call_count == 1


def test_atlas_read_timeout_is_retried():
    with mock.patch.object(kinogo.requests, "get", side_effect=kinogo.requests.ReadTimeout()) as get:
        assert kinogo._fetch_with_retries(ATLAS_URL) is None
    assert get.call_count == 2


def test_atlas_http_error_is_retried():
    ok = _resp(MASTER)
    with mock.patch.object(kinogo.requests, "get", side_effect=[_resp(status=503), ok]):
        assert kinogo._fetch_with_retries(ATLAS_URL) is ok


def test_atlas_request_uses_short_connect_timeout():
    with mock.patch.object(kinogo.requests, "get", return_value=_resp(MASTER)) as get:
        kinogo._fetch_with_retries(ATLAS_URL)
    assert get.call_args.kwargs["timeout"] == (1.5, 4)


def test_master_playlist_keeps_long_connect_timeout():
    with mock.patch.object(kinogo.requests, "get", return_value=_resp(MASTER)) as get:
        kinogo._fetch_playlist(SIGNED)
    assert get.call_args.kwargs["timeout"] == (4, 4)


def test_dropped_connection_is_retried_but_silent_node_is_not():
    with mock.patch.object(kinogo.requests, "get", side_effect=[kinogo.requests.ConnectionError(), _resp(_media())]) as get:
        assert kinogo._fetch_with_retries("https://atlas.host.cinemap.cc/a/1080.m3u8") is not None
    assert get.call_count == 2


def _player_page():
    return _resp(MOVIE_HTML.replace("</article>", '<div class="js-player-container"><iframe data-src="https://cinemar.cc/e/1"></iframe></div></article>'))


def test_without_optional_module_browser_is_used(monkeypatch):
    import sys
    import mpv_launcher
    monkeypatch.delattr(mpv_launcher, "fastload", raising=False)
    with mock.patch.dict(sys.modules, {"mpv_launcher.fastload": None}), \
        mock.patch.object(kinogo.requests, "get", return_value=_player_page()), \
        mock.patch.object(kinogo, "capture_stream", return_value=kinogo.Captured(SIGNED, None, [])) as capture, \
        mock.patch.object(kinogo, "build_streams", return_value={"1080p": ["https://a/1.m3u8"]}):
        kinogo.fetch_movie(f"{BASE}/filmy/12.html", mock.Mock(), BASE)
    capture.assert_called_once()


def test_failing_optional_module_falls_back_to_browser(monkeypatch):
    import sys
    import types
    import mpv_launcher
    broken = types.SimpleNamespace(capture=mock.Mock(side_effect=AttributeError("новый формат")))
    monkeypatch.setattr(mpv_launcher, "fastload", broken, raising=False)
    with mock.patch.dict(sys.modules, {"mpv_launcher.fastload": broken}), \
        mock.patch.object(kinogo.requests, "get", return_value=_player_page()), \
        mock.patch.object(kinogo, "capture_stream", return_value=kinogo.Captured(SIGNED, None, [])) as capture, \
        mock.patch.object(kinogo, "build_streams", return_value={"1080p": ["https://a/1.m3u8"]}):
        details = kinogo.fetch_movie(f"{BASE}/filmy/12.html", mock.Mock(), BASE)
    capture.assert_called_once()
    broken.capture.assert_called_once()
    assert details.streams == {"1080p": ["https://a/1.m3u8"]}
