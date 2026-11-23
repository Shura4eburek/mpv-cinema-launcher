from unittest import mock

import pytest
import requests

from mpv_launcher import trailers


def _video(video_id, title):
    return f'"videoRenderer":{{"videoId":"{video_id}","thumbnail":{{}},"title":{{"runs":[{{"text":"{title}"}}]}}}}'


def test_only_trailers_stay_and_film_name_goes_first():
    html = ",".join([
        _video("aaaaaaaaaaa", "Интервью с режиссёром"),
        _video("ccccccccccc", "Tenet - Official Trailer"),
        _video("bbbbbbbbbbb", "ДОВОД - финальный трейлер"),
        _video("ddddddddddd", "Довод - трейлер 2"),
    ])
    assert [v["id"] for v in trailers.parse_videos(html, "Довод")] == ["bbbbbbbbbbb", "ddddddddddd", "ccccccccccc"]


def test_film_name_is_not_taken_for_reaction():
    html = ",".join([
        _video("aaaaaaaaaaa", "Цепная реакция - трейлер"),
        _video("bbbbbbbbbbb", "Реакция на трейлер Цепная реакция"),
        _video("ccccccccccc", "Official Trailer Preview"),
    ])
    assert [v["id"] for v in trailers.parse_videos(html, "Цепная реакция")] == ["aaaaaaaaaaa", "ccccccccccc"]


def test_bad_title_does_not_break_the_rest():
    html = ",".join([_video("aaaaaaaaaaa", "Трейлер \\x22"), _video("bbbbbbbbbbb", "Трейлер")])
    assert [v["id"] for v in trailers.parse_videos(html)] == ["bbbbbbbbbbb"]


def test_consent_page_is_a_failure_not_an_empty_result():
    with mock.patch.object(trailers.requests, "get", return_value=mock.Mock(status_code=200, text="<html>consent</html>")):
        with pytest.raises(trailers.TrailerUnavailable):
            trailers.find("Довод", "2020")


def test_reactions_are_dropped_and_duplicates_merged():
    html = ",".join([
        _video("aaaaaaaaaaa", "Реакция на трейлер Довод"),
        _video("bbbbbbbbbbb", "Трейлер"),
        _video("bbbbbbbbbbb", "Трейлер"),
    ])
    assert trailers.parse_videos(html) == [{"id": "bbbbbbbbbbb", "title": "Трейлер"}]


def test_at_most_five_videos_and_escapes_are_decoded():
    html = ",".join(_video(f"{i}" * 11, 'Трейлер \\"Довод\\"') for i in range(7))
    videos = trailers.parse_videos(html)
    assert len(videos) == 5
    assert videos[0]["title"] == 'Трейлер "Довод"'


def test_page_without_videos_gives_nothing():
    assert trailers.parse_videos("<html>consent</html>") == []


@pytest.mark.parametrize(
    ("title", "year", "query"),
    [
        ("Довод (2020)", None, "Довод+2020"),
        ("Довод / Тенет", "2020", "Довод+2020"),
        ("Довод", None, "Довод+"),
    ],
)
def test_search_url_uses_clean_title_and_year(title, year, query):
    url = requests.utils.unquote(trailers.search_url(title, year).replace("%2B", "+"))
    assert query.rstrip("+") in url
    assert url.endswith("трейлер")
    assert "Тенет" not in url
    assert "(" not in url


def test_network_failure_is_reported():
    with mock.patch.object(trailers.requests, "get", side_effect=requests.ConnectionError()):
        with pytest.raises(trailers.TrailerUnavailable):
            trailers.find("Довод", "2020")
    with mock.patch.object(trailers.requests, "get", return_value=mock.Mock(status_code=429)):
        with pytest.raises(trailers.TrailerUnavailable):
            trailers.find("Довод", "2020")
