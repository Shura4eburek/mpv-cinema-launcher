"""Сериалы: разбор сезонов и серий, плеер KinoGo, запросы HDRezka, автооткрытие запасного источника."""

import json
from unittest import mock

import pytest
from bs4 import BeautifulSoup

from mpv_launcher import kinogo, scraper, sources
from mpv_launcher.scraper import Episode, MovieSearchResult, Season

REZKA_PAGE = """
<ul><li class="b-translator__item" data-translator_id="56">Дубляж</li>
<li class="b-translator__item active" data-translator_id="565">TVShows</li></ul>
<ul><li class="b-simple_season__item active" data-tab_id="1">Сезон 1</li>
<li class="b-simple_season__item" data-tab_id="2">Сезон 2</li></ul>
<ul><li class="b-simple_episode__item active" data-season_id="1" data-episode_id="1">Серия 1</li>
<li class="b-simple_episode__item" data-season_id="1" data-episode_id="2">Серия 2</li>
<li class="b-simple_episode__item" data-season_id="2" data-episode_id="1">Серия 1</li></ul>
<script>initCDNSeriesEvents(646, 565, 1, 1, false, 'rezka-ua.pub', false, true, {});</script>
"""


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def _seasons():
    return [
        Season("1", "Сезон 1", [Episode("1", "Серия 1"), Episode("7", "Серия 7")]),
        Season("5", "Сезон 5", [Episode("1", "Серия 1"), Episode("2", "Серия 2")]),
    ]


# --- ближайшая серия


@pytest.mark.parametrize(
    ("season", "episode", "expected"),
    [
        ("1", "7", ("1", "7", False)),
        ("1", None, ("1", "1", False)),
        ("1", "9", ("1", "7", True)),
        ("5", "99", ("5", "2", True)),
        ("4", "3", ("5", "1", True)),
        ("9", None, ("5", "1", True)),
    ],
)
def test_nearest_episode(season, episode, expected):
    assert scraper.nearest_episode(_seasons(), season, episode) == expected


def test_nearest_episode_skips_seasons_without_episodes_and_empty_list():
    seasons = [Season("1", "Сезон 1"), Season("3", "Сезон 3", [Episode("1", "Серия 1")])]
    assert scraper.nearest_episode(seasons, "1", "2") == ("3", "1", True)
    assert scraper.nearest_episode([], "1", "2") is None


@pytest.mark.parametrize(
    ("ids", "wanted", "expected"),
    [(["1", "2"], None, "1"), (["a", "b"], "c", "a"), (["1", "10"], "abc", "1"), (["a", "5"], "4", "5"), ([], "1", None)],
)
def test_nearest_id_with_unusual_values(ids, wanted, expected):
    assert scraper.nearest_id(ids, wanted) == expected


# --- HDRezka


def test_parse_series_from_page():
    series = scraper.parse_series(_soup(REZKA_PAGE))
    assert [s.name for s in series.seasons] == ["Сезон 1", "Сезон 2"]
    assert [e.id for e in series.seasons[0].episodes] == ["1", "2"]
    assert (series.season, series.episode, series.moved) == ("1", "1", False)


def test_film_page_has_no_series():
    assert scraper.parse_series(_soup('<li class="b-translator__item" data-translator_id="1">Дубляж</li>')) is None


def test_parse_series_without_season_names_and_active():
    html = '<li class="b-simple_episode__item" data-season_id="3" data-episode_id="4"></li>'
    series = scraper.parse_series(_soup(html))
    assert series.seasons[0].name == "Сезон 3"
    assert series.seasons[0].episodes[0].name == "Серия 4"
    assert (series.season, series.episode) == ("3", "4")


def test_series_translator_from_init_script():
    assert scraper.series_translator_id(REZKA_PAGE) == "565"
    assert scraper.series_translator_id("<script>initCDNMoviesEvents(1, 2);</script>") is None


def _driver(responses):
    """Драйвер на странице сериала; ответы сайта по значению action."""
    driver = mock.Mock()
    driver.page_source = REZKA_PAGE
    driver.requests = []

    def execute(_script, data):
        driver.requests.append(data)
        return responses[data["action"]]

    driver.execute_script.side_effect = execute
    return driver


GET_EPISODES = {
    "success": True,
    "seasons": '<li class="b-simple_season__item" data-tab_id="2">Сезон 2</li>',
    "episodes": '<li class="b-simple_episode__item active" data-season_id="2" data-episode_id="1">Серия 1</li>'
    '<li class="b-simple_episode__item" data-season_id="2" data-episode_id="2">Серия 2</li>',
}
GET_STREAM = {"success": True, "url": "[720p]https://cdn/a:hls:manifest.m3u8"}
REFUSED = {"success": False, "message": "Время сессии истекло"}


def test_episode_of_series_never_asks_for_film():
    driver = _driver({"get_episodes": GET_EPISODES, "get_stream": GET_STREAM})
    details = scraper.fetch_episode("https://r/1", driver, "56", "2", "2")
    assert [r["action"] for r in driver.requests] == ["get_episodes", "get_stream"]
    assert (driver.requests[1]["season"], driver.requests[1]["episode"]) == ("2", "2")
    assert details.streams == {"720p": ["https://cdn/a:hls:manifest.m3u8"]}
    assert (details.series.season, details.series.episode, details.series.moved) == ("2", "2", False)
    assert details.active_translator_id == "56"
    assert [t.active for t in details.translators] == [True, False]


def test_episode_missing_in_voice_moves_to_nearest():
    driver = _driver({"get_episodes": GET_EPISODES, "get_stream": GET_STREAM})
    details = scraper.fetch_episode("https://r/1", driver, "56", "2", "9")
    assert details.series.episode == "2" and details.series.moved is True


def test_episode_uses_active_voice_when_not_given():
    driver = _driver({"get_episodes": GET_EPISODES, "get_stream": GET_STREAM})
    assert scraper.fetch_episode("https://r/1", driver, None, "2", "1").active_translator_id == "565"


@pytest.mark.parametrize("responses", [
    {"get_episodes": REFUSED},
    {"get_episodes": GET_EPISODES, "get_stream": REFUSED},
])
def test_site_refusal_gives_no_streams_instead_of_error(responses):
    assert scraper.fetch_episode("https://r/1", _driver(responses), "56", "2", "1").streams == {}


def test_request_failure_is_site_unavailable_not_missing_video():
    with pytest.raises(scraper.SiteUnavailable):
        scraper.fetch_episode("https://r/1", _driver({"get_episodes": None}), "56", "2", "1")
    broken = _driver({})
    broken.execute_script.side_effect = RuntimeError("$ is not defined")
    with pytest.raises(scraper.SiteUnavailable):
        scraper.fetch_episode("https://r/1", broken, "56", "2", "1")


def test_film_voice_still_uses_film_request():
    driver = _driver({"get_movie": json.dumps(GET_STREAM)})
    assert scraper.fetch_translator_streams("https://r/1", "56", driver) == {"720p": ["https://cdn/a:hls:manifest.m3u8"]}
    assert driver.requests[0]["is_camrip"] == 0


# --- KinoGo: списки плеера


def _group(current, *items):
    return {"current": current, "items": list(items)}


SEASONS = _group("Сезон 1", "Сезон 1", "Сезон 2")
EPISODES = _group("Серия 1", "Серия 1", "Серия 2")
VOICES = _group("Дубляж", "Дубляж", "LostFilm")


def test_classify_series_regardless_of_order():
    assert kinogo.classify_groups([VOICES, EPISODES, SEASONS]) == (SEASONS, EPISODES, VOICES)


def test_classify_series_with_single_season_and_voice():
    season, voice = _group("Сезон 1", "Сезон 1"), _group("Любительский", "Любительский")
    assert kinogo.classify_groups([season, EPISODES, voice]) == (season, EPISODES, voice)


def test_classify_film_and_series_without_seasons():
    assert kinogo.classify_groups([VOICES]) == (None, None, VOICES)
    assert kinogo.classify_groups([EPISODES, VOICES]) == (None, EPISODES, VOICES)


def test_classify_ignores_foreign_single_button():
    assert kinogo.classify_groups([_group("Настройки", "Качество"), VOICES]).voices == VOICES


def test_series_from_lists_fills_current_season_only():
    series = kinogo.series_from_lists(kinogo.classify_groups([SEASONS, EPISODES, VOICES]))
    assert [len(s.episodes) for s in series.seasons] == [2, 0]
    assert (series.season, series.episode) == ("1", "1")


def test_series_without_season_list_gets_single_season():
    series = kinogo.series_from_lists(kinogo.classify_groups([EPISODES, VOICES]))
    assert [s.id for s in series.seasons] == ["1"]
    assert kinogo.series_from_lists(kinogo.classify_groups([VOICES])) is None


class FakePlayer:
    """Плеер сериала: смена сезона сбрасывает серию; «Кравец» есть только в сезоне 5."""

    def __init__(self):
        self.season, self.episode, self.voice = 1, 1, "Дубляж"
        self.clicks = []

    def execute_script(self, script, *args):
        if script == kinogo._READ_GROUPS:
            voices = ["Дубляж", "LostFilm"] + (["Кравец"] if self.season == 5 else [])
            return [
                _group(f"Сезон {self.season}", *[f"Сезон {n}" for n in (1, 2, 5)]),
                _group(f"Серия {self.episode}", *[f"Серия {n}" for n in range(1, 4)]),
                _group(self.voice, *voices),
            ]
        if script == kinogo._CLICK_ITEM:
            name = args[0]
            self.clicks.append(name)
            if name.startswith("Сезон"):
                self.season, self.episode = int(name.split()[1]), 1
            elif name.startswith("Серия"):
                self.episode = int(name.split()[1])
            elif name == "Кравец" and self.season != 5:
                return False
            else:
                self.voice = name
            return True
        return "текст"


@pytest.fixture
def stream_after_click():
    with mock.patch.object(kinogo, "_wait_for_master", return_value="https://new/hls.m3u8") as wait:
        yield wait


def _select(player, voice=None, season=None, episode=None, strict=True):
    return kinogo._select(player, "https://old/hls.m3u8", voice, strict, season, episode, kinogo.NO_PROGRESS)


def test_opening_series_does_not_click(stream_after_click):
    player = FakePlayer()
    captured = _select(player, strict=False)
    assert player.clicks == []
    assert captured.master == "https://old/hls.m3u8"
    assert captured.current == "Дубляж"
    assert captured.voices == ["Дубляж", "LostFilm"]
    assert captured.series.season == "1"


def test_select_episode_after_season(stream_after_click):
    player = FakePlayer()
    captured = _select(player, season="2", episode="3")
    assert player.clicks == ["Сезон 2", "Серия 3"]
    assert (captured.series.season, captured.series.episode, captured.series.moved) == ("2", "3", False)
    assert captured.master == "https://new/hls.m3u8"


def test_voice_of_one_season_needs_season_first(stream_after_click):
    player = FakePlayer()
    captured = _select(player, voice="Кравец", season="5", episode="2")
    assert player.clicks == ["Сезон 5", "Кравец", "Серия 2"]
    assert captured.current == "Кравец"


def test_season_selection_opens_first_episode(stream_after_click):
    player = FakePlayer()
    player.season, player.episode = 2, 3
    captured = _select(player, season="2", episode=None)
    assert player.clicks == ["Серия 1"]
    assert captured.series.moved is False


@pytest.mark.parametrize(
    ("season", "episode", "state"),
    [("1", "9", ("1", "3", True)), ("3", "2", ("2", "1", True))],
)
def test_missing_episode_and_season_move_to_nearest(stream_after_click, season, episode, state):
    series = _select(FakePlayer(), season=season, episode=episode).series
    assert (series.season, series.episode, series.moved) == state


def test_missing_voice_is_error_only_when_strict(stream_after_click):
    with pytest.raises(kinogo.NoVideo):
        _select(FakePlayer(), voice="Кравец", season="1")
    assert _select(FakePlayer(), voice="Кравец", strict=False).current == "Дубляж"


def test_failed_switch_is_no_video():
    with mock.patch.object(kinogo, "_wait_for_master", return_value=None):
        with pytest.raises(kinogo.NoVideo):
            _select(FakePlayer(), season="2")


# --- KinoGo: поток сериала

SERIES_SIGNED = "https://cfnd.cinemap.cc/1793-SIGN%3D/tvseries/abc/tok:2026/hls.m3u8"
MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=640x360
./360.mp4:hls:manifest.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1920x1080
./1080.mp4:hls:manifest.m3u8
"""
SHORT = "#EXTM3U\n#EXTINF:170.0,\ns.ts\n"


def _response(text, url):
    response = mock.Mock(ok=True, status_code=200, text=text, url=url)
    return response


def _network(dead=""):
    def get(url, **_kwargs):
        if url.endswith("/hls.m3u8"):
            return _response(MASTER, url)
        if dead and "atlas.host" in url and dead in url:
            raise kinogo.requests.ConnectTimeout()
        return _response(SHORT, url)

    return mock.patch.object(kinogo.requests, "get", side_effect=get)


def test_series_path_on_atlas_has_no_signature():
    url = kinogo._on_host(SERIES_SIGNED, "1080.mp4", kinogo.ATLAS_HOST, signed=False)
    assert url == "https://atlas.host.cinemap.cc/tvseries/abc/tok:2026/1080.mp4"


def test_any_signature_format_is_removed_for_atlas():
    url = kinogo._on_host("https://cfnd.cinemap.cc/abc-SIGN/movies/x/hls.m3u8", "1.mp4", kinogo.ATLAS_HOST, signed=False)
    assert url == "https://atlas.host.cinemap.cc/movies/x/1.mp4"


def test_best_quality_prefers_player_stream_when_top_is_lost():
    assert sources.best_quality({"480p": ["a"], kinogo.UNCONFIRMED: ["b"]}) == kinogo.UNCONFIRMED


def test_switch_waits_for_button_label_after_stream():
    player = mock.Mock()
    player.execute_script.side_effect = [True, [_group("Дубляж", "Дубляж", "LostFilm")], [_group("LostFilm", "Дубляж", "LostFilm")]]
    with mock.patch.object(kinogo, "_wait_for_master", return_value="https://new/hls.m3u8"), mock.patch.object(kinogo.time, "sleep"):
        assert kinogo._switch(player, "LostFilm", kinogo.NO_PROGRESS) == "https://new/hls.m3u8"
    assert player.execute_script.call_count == 3


def test_short_episode_is_accepted_but_short_film_is_not():
    with _network():
        assert list(kinogo.build_streams(SERIES_SIGNED, is_series=True)) == ["360p", "1080p"]
        with pytest.raises(kinogo.NoVideo):
            kinogo.build_streams(SERIES_SIGNED)


def test_series_keeps_player_stream_when_best_node_is_dead():
    with _network(dead="1080.mp4"):
        streams = kinogo.build_streams(SERIES_SIGNED, is_series=True)
    assert streams[kinogo.UNCONFIRMED] == [SERIES_SIGNED]
    assert "360p" in streams and "1080p" not in streams


def test_series_with_low_node_dead_has_no_extra_variant():
    with _network(dead="360.mp4"):
        assert list(kinogo.build_streams(SERIES_SIGNED, is_series=True)) == ["1080p"]


# --- автооткрытие HDRezka


def _rezka(title, info, path="films/drama"):
    return MovieSearchResult(title=title, url=f"https://r/{path}/1.html", info=info)


BREAKING_BAD = _rezka("Во все тяжкие", "2008-2013, США, Триллеры", "series/thriller")
MINI = _rezka("Во все тяжкие: Мини-эпизоды", "2009-2011, США", "series/drama")
BEARS = _rezka("Во все тяжкие: Медведи", "2026 - ..., США", "cartoons/comedy")
EL_CAMINO = _rezka("El Camino: Во все тяжкие", "2019, США, Драмы")
CARDS = [BREAKING_BAD, MINI, BEARS, EL_CAMINO]


@pytest.mark.parametrize(
    ("title", "clean"),
    [("Во все тяжкие (1-5 сезон)", "Во все тяжкие"), ("Т (1 сезон)", "Т"), ("Т (1 сезон) (2020)", "Т"), ("Сезон охоты (2006)", "Сезон охоты")],
)
def test_clean_title_removes_seasons(title, clean):
    assert sources.clean_title(title) == clean


@pytest.mark.parametrize(
    ("title", "is_series", "expected"),
    [
        ("Во все тяжкие (1-5 сезон)", True, BREAKING_BAD),
        ("Во все тяжкие: Мини-эпизоды (1 сезон)", True, MINI),
        ("El Camino: Во все тяжкие (2019)", False, EL_CAMINO),
        ("Во все тяжкие: Фильм (2020)", False, None),
        # Похожее название или другой тип не открываются сами.
        ("Во все", True, None),
        ("Во все тяжкие (2008)", False, None),
    ],
)
def test_single_match(title, is_series, expected):
    assert sources.single_match(CARDS, title, is_series) == expected


def test_single_match_splits_other_title_and_ignores_unknown_type():
    card = _rezka("Довод / Тенет", "2020, США")
    assert sources.single_match([card], "Тенет", None) == card


def test_single_match_rejects_other_year_with_margin():
    card = _rezka("Дюна", "1984, США")
    assert sources.single_match([card], "Дюна (2021)", False) is None
    assert sources.single_match([_rezka("Дюна", "2020, США")], "Дюна (2021)", False) is not None


def test_single_match_uses_year_between_namesakes_and_gives_up_otherwise():
    old, new = _rezka("Дюна", "1984, США"), _rezka("Дюна", "2021, США")
    assert sources.single_match([old, new], "Дюна (2021)", False) == new
    assert sources.single_match([old, new], "Дюна", False) is None


def test_running_series_fits_any_later_year():
    assert sources.single_match([BEARS], "Во все тяжкие: Медведи", None, "2027") == BEARS
    assert sources.single_match([MINI], "Во все тяжкие: Мини-эпизоды", None, "2020") is None


@pytest.mark.parametrize(
    ("url", "title", "expected"),
    [
        ("https://k/serialy/1.html", "Т", True),
        ("https://k/1.html", "Т (1-5 сезон)", True),
        ("https://k/filmy/1.html", "Сезон охоты", False),
        ("https://k/1.html", "Т (2020)", False),
        ("https://k/1.html", "Т", None),
    ],
)
def test_kinogo_page_type(url, title, expected):
    assert sources._kinogo_is_series(url, title) is expected


def _no_video(title):
    failure = kinogo.NoVideo("нет")
    failure.details = scraper.MovieDetails(title=title, url="https://k/serialy/1.html", description="о", source="kinogo")
    return mock.patch.object(sources.kinogo, "fetch_movie", side_effect=failure)


def _open(cards, page):
    with _no_video("Во все тяжкие (1-5 сезон)"), \
        mock.patch.object(sources.scraper, "search_movies", return_value=cards), \
        mock.patch.object(sources.scraper, "fetch_movie_details", **page) as fetch:
        return sources.open_movie("https://k/serialy/1.html", mock.Mock(), "https://k", source="kinogo"), fetch


def test_single_match_opens_backup_page_without_list():
    page = scraper.MovieDetails(title="Во все тяжкие", url=BREAKING_BAD.url, streams={"720p": ["https://s"]})
    details, fetch = _open(CARDS, {"return_value": page})
    assert details is page
    assert details.switched_from == "kinogo"
    assert details.alternatives == []
    assert fetch.call_args.args[0] == BREAKING_BAD.url


def test_ambiguous_result_keeps_list():
    details, fetch = _open([MINI, BEARS], {"return_value": None})
    fetch.assert_not_called()
    assert details.alternatives == [MINI, BEARS]
    assert details.switched_from is None


@pytest.mark.parametrize("page", [
    {"return_value": scraper.MovieDetails(title="Подождите", url="https://r/1")},
    {"side_effect": RuntimeError("сбой")},
])
def test_failed_backup_page_keeps_list(page):
    details, _fetch = _open(CARDS, page)
    assert details.alternatives == CARDS
    assert details.switched_from is None


def test_cancel_during_backup_page_is_not_swallowed():
    progress = mock.MagicMock()
    progress.check.side_effect = [None, sources.scraper.SiteUnavailable("отмена")]
    with _no_video("Во все тяжкие (1-5 сезон)"), \
        mock.patch.object(sources.scraper, "search_movies", return_value=CARDS), \
        mock.patch.object(sources.scraper, "fetch_movie_details", side_effect=RuntimeError("Chrome закрыт")):
        with pytest.raises(sources.scraper.SiteUnavailable):
            sources.open_movie("https://k/serialy/1.html", mock.Mock(), "https://k", source="kinogo", progress=progress)
