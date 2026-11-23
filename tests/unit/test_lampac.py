from unittest import mock

import pytest

from mpv_launcher import lampac

BASE = "http://127.0.0.1:19118"


def _play(**extra):
    return {"method": "play", "url": "https://cdn/a.m3u8", "translate": "По умолчанию", **extra}


def test_stable_id_differs_by_film_and_is_repeatable():
    assert lampac.stable_id("Довод", "2020") == lampac.stable_id("Довод", "2020")
    assert lampac.stable_id("Довод", "2020") != lampac.stable_id("Брат", "1997")
    assert lampac.stable_id("Довод", "2020") > 0


def test_single_stream_without_quality_is_auto():
    variants = lampac.parse_variants({"type": "movie", "data": [_play()]}, "u")
    assert variants["items"] == [{"voice": "По умолчанию", "qualities": [{"label": "Авто", "url": "https://cdn/a.m3u8"}], "subtitles": [], "episode": None}]
    assert variants["voices"] == []


def test_quality_map_and_max_quality():
    data = {"type": "movie", "data": [_play(quality={"1080p": "https://c/1", "720p": "https://c/2"}), _play(maxquality="720p")]}
    items = lampac.parse_variants(data, "u")["items"]
    assert [q["label"] for q in items[0]["qualities"]] == ["1080p", "720p"]
    assert items[1]["qualities"][0]["label"] == "720p"


def test_active_voice_names_item_instead_of_long_translate_list():
    data = {
        "type": "movie",
        "voice": [{"name": "Дубляж", "url": "v1", "active": True}, {"name": "Сербин", "url": "v2"}, {"url": "без имени"}],
        "data": [_play(translate="Дубляж, Сербин, Есарев")],
    }
    variants = lampac.parse_variants(data, "u")
    assert variants["items"][0]["voice"] == "Дубляж"
    assert [v["name"] for v in variants["voices"]] == ["Дубляж", "Сербин"]


def test_voice_name_field_wins():
    data = {"type": "movie", "data": [_play(voice_name="Гаврилов")]}
    assert lampac.parse_variants(data, "u")["items"][0]["voice"] == "Гаврилов"


def test_subtitles_are_kept():
    data = {"type": "movie", "data": [_play(subtitles=[{"method": "link", "url": "https://c/ua.vtt", "label": "Українські"}, {"label": "без адреса"}])]}
    assert lampac.parse_variants(data, "u")["items"][0]["subtitles"] == [{"label": "Українські", "url": "https://c/ua.vtt"}]


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"type": "similar", "data": [{"method": "link", "url": "x"}]},
        {"type": "movie", "data": []},
        {"type": "movie", "data": [{"method": "link", "url": "x"}]},
        {"type": "movie", "data": [{"method": "play", "url": "https://c/s/abc/abuse_480.mp4"}]},
        {"type": "movie", "data": [{"method": "play", "quality": {"480p": "https://c/abuse_480.mp4"}}]},
    ],
)
def test_nothing_to_watch(data):
    assert lampac.parse_variants(data, "u") is None


def test_rjson_replaces_existing_flag():
    url = lampac._as_json_url(f"{BASE}/lite/x?rjson=True&uri=a%20b")
    assert url.count("rjson") == 1
    assert url.endswith("rjson=true")
    assert "uri=a+b" in url


SEASONS = {"type": "season", "data": [{"method": "link", "id": 1, "url": f"{BASE}/lite/s?s=1", "name": "1 сезон"}, {"method": "link", "id": 2, "url": f"{BASE}/lite/s?s=2", "name": "2 сезон"}]}
EPISODES = {
    "type": "episode",
    "voice": [{"name": "Кубик в кубе", "url": "v1", "active": True}],
    "data": [_play(s=1, e=1, name="1 серия", quality={"720p": "https://c/e1"}), _play(s=1, e=2, name="2 серия")],
}


def test_stable_id_differs_for_series_with_same_name():
    assert lampac.stable_id("Дюна", "2021", True) != lampac.stable_id("Дюна", "2021", False)


def test_episodes_are_parsed():
    variants = lampac.parse_variants(EPISODES, "u")
    assert variants["kind"] == "episode"
    assert variants["items"][0]["episode"] == {"season": 1, "number": 1, "name": "1 серия"}
    assert variants["items"][1]["episode"]["number"] == 2
    assert variants["items"][0]["voice"] == "Кубик в кубе"


def test_seasons_open_first_season():
    with mock.patch.object(lampac.requests, "get", side_effect=[_response(SEASONS), _response(EPISODES)]) as get:
        variants = lampac.load_variants(f"{BASE}/lite/s", serial=True)
    assert "s=1" in get.call_args_list[1].args[0]
    assert [s["name"] for s in variants["seasons"]] == ["1 сезон", "2 сезон"]
    assert len(variants["items"]) == 2


@pytest.mark.parametrize(
    ("data", "serial"),
    [({"type": "movie", "data": [_play()]}, True), (EPISODES, False), (SEASONS, False), ({"type": "season", "data": []}, True)],
)
def test_wrong_kind_of_title_is_dropped(data, serial):
    with mock.patch.object(lampac.requests, "get", return_value=_response(data)):
        assert lampac.load_variants(f"{BASE}/lite/s", serial=serial) is None


def test_search_removes_seasons_note_and_marks_serial():
    polls = [{"ready": True, "online": []}]
    with mock.patch.object(lampac.requests, "get", side_effect=_server(polls, {})) as get:
        lampac.search(BASE, "Проект Лазарь (1-2 сезон)", None, "2025", lambda s: None, lambda: None, serial=True)
    params = get.call_args_list[0].kwargs["params"]
    assert params["title"] == "Проект Лазарь"
    assert params["serial"] == 1


def _response(data=None, ok=True, bad_json=False):
    response = mock.Mock(ok=ok, status_code=200 if ok else 500)
    response.json.side_effect = ValueError() if bad_json else None
    response.json.return_value = data
    return response


SIMILAR = {
    "type": "similar",
    "data": [
        {"method": "link", "url": f"{BASE}/lite/h?id=1", "title": "Довод", "year": 2021},
        {"method": "link", "url": f"{BASE}/lite/h?id=2", "title": "Доводы рассудка", "year": 2020},
        {"method": "link", "url": f"{BASE}/lite/h?id=3", "title": "Довод", "year": 2020},
    ],
}


def test_similar_is_followed_only_for_exact_film():
    responses = [_response(SIMILAR), _response({"type": "movie", "data": [_play()]})]
    with mock.patch.object(lampac.requests, "get", side_effect=responses) as get:
        variants = lampac.load_variants(f"{BASE}/lite/h", ["Довод"], "2020")
    assert "id=3" in get.call_args_list[1].args[0]
    assert "id=3" in variants["url"]


@pytest.mark.parametrize(("titles", "year"), [(["Другой"], "2020"), (["Довод"], "1999"), (["Довод"], None)])
def test_similar_without_exact_match_is_dropped(titles, year):
    with mock.patch.object(lampac.requests, "get", return_value=_response(SIMILAR)) as get:
        assert lampac.load_variants(f"{BASE}/lite/h", titles, year) is None
    assert get.call_count == 1


@pytest.mark.parametrize("response", [_response(ok=False), _response(bad_json=True)])
def test_bad_answer_is_unavailable(response):
    with mock.patch.object(lampac.requests, "get", return_value=response):
        with pytest.raises(lampac.Unavailable):
            lampac.load_variants(f"{BASE}/lite/h")


def _server(polls, sources):
    """Сервер Lampac: ключ, затем ответы проверки, затем варианты по имени источника."""
    answers = iter(polls)

    def get(url, params=None, timeout=None):
        if url.endswith("/lite/events"):
            return _response({"life": True, "memkey": "k"})
        if url.endswith("/lifeevents"):
            return _response(next(answers))
        name = url.split("/lite/")[1].split("?")[0]
        return sources[name] if isinstance(sources[name], mock.Mock) else _response(sources[name])

    return get


def _item(name, show=True):
    return {"name": f"{name} ~ 1080p", "url": f"{BASE}/lite/{name}", "show": show, "balanser": name}


def test_search_reports_sources_as_they_arrive_and_skips_bad_ones():
    polls = [
        {"ready": False, "online": [_item("a"), _item("off", show=False)]},
        {"ready": True, "online": [_item("a"), _item("off", show=False), _item("b"), _item("c")]},
    ]
    sources = {
        "a": {"type": "movie", "data": [_play()]},
        "b": _response(bad_json=True),
        "c": {"type": "similar", "data": []},
    }
    reported = []
    with mock.patch.object(lampac.requests, "get", side_effect=_server(polls, sources)) as get:
        found = lampac.search(BASE, "Довод (2020)", "Tenet", "2020", reported.append, lambda: None)
    assert found == 1
    assert [(s["id"], s["name"]) for s in reported] == [("a", "a")]
    events = next(c for c in get.call_args_list if c.args[0].endswith("/lite/events"))
    assert events.kwargs.get("params", events.args[1] if len(events.args) > 1 else None)["title"] == "Довод"
    assert not any("/lite/off" in c.args[0] for c in get.call_args_list)


def test_failed_poll_keeps_sources_already_requested():
    answers = iter([{"ready": False, "online": [_item("a")]}])

    def get(url, params=None, timeout=None):
        if url.endswith("/lite/events"):
            return _response({"life": True, "memkey": "k"})
        if url.endswith("/lifeevents"):
            try:
                return _response(next(answers))
            except StopIteration:
                return _response(ok=False)
        return _response({"type": "movie", "data": [_play()]})

    reported = []
    with mock.patch.object(lampac.requests, "get", side_effect=get):
        assert lampac.search(BASE, "Довод", None, None, reported.append, lambda: None) == 1
    assert len(reported) == 1


def test_failed_poll_without_sources_is_unavailable():
    def get(url, params=None, timeout=None):
        if url.endswith("/lite/events"):
            return _response({"life": True, "memkey": "k"})
        return _response(ok=False)

    with mock.patch.object(lampac.requests, "get", side_effect=get):
        with pytest.raises(lampac.Unavailable):
            lampac.search(BASE, "Довод", None, None, lambda s: None, lambda: None)


def test_unexpected_source_answer_does_not_stop_search():
    polls = [{"ready": True, "online": [_item("bad"), _item("good")]}]
    sources = {"bad": mock.Mock(ok=True, json=mock.Mock(side_effect=TypeError("сбой"))), "good": {"type": "movie", "data": [_play()]}}
    reported = []
    with mock.patch.object(lampac.requests, "get", side_effect=_server(polls, sources)):
        assert lampac.search(BASE, "Довод", None, None, reported.append, lambda: None) == 1
    assert reported[0]["id"] == "good"


def test_non_text_quality_url_is_ignored():
    data = {"type": "movie", "data": [_play(quality={"1080p": None, "720p": 5, "480p": "https://c/ok"})]}
    assert lampac.parse_variants(data, "u")["items"][0]["qualities"] == [{"label": "480p", "url": "https://c/ok"}]


def test_search_stops_when_cancelled():
    class Stop(Exception):
        pass

    def cancelled():
        raise Stop()

    with mock.patch.object(lampac.requests, "get", side_effect=_server([], {})):
        with pytest.raises(Stop):
            lampac.search(BASE, "Довод", None, None, lambda s: None, cancelled)


def test_search_without_key_is_unavailable():
    with mock.patch.object(lampac.requests, "get", return_value=_response({"online": []})):
        with pytest.raises(lampac.Unavailable):
            lampac.search(BASE, "Довод", None, None, lambda s: None, lambda: None)
