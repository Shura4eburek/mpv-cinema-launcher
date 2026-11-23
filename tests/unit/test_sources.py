"""Порядок источников: KinoGo → HDRezka."""

from unittest import mock

import pytest

from mpv_launcher import kinogo, scraper, sources

BASE = "https://kinogo.test"
CARD_K = scraper.MovieSearchResult(title="Довод (2020)", url=f"{BASE}/filmy/1.html", source="kinogo")
CARD_H = scraper.MovieSearchResult(title="Довод", url="https://rezka.test/1.html")


def _patches(kinogo_search, hdrezka_search):
    return (
        mock.patch.object(sources.kinogo, "search", **kinogo_search),
        mock.patch.object(sources.scraper, "search_movies", **hdrezka_search),
    )


def test_search_uses_kinogo_first():
    k, h = _patches({"return_value": [CARD_K]}, {"return_value": [CARD_H]})
    with k, h as hdrezka:
        assert sources.search("Довод", BASE) == [CARD_K]
    hdrezka.assert_not_called()


@pytest.mark.parametrize("kinogo_search", [{"return_value": []}, {"side_effect": scraper.SiteUnavailable()}])
def test_search_falls_back_to_hdrezka(kinogo_search):
    k, h = _patches(kinogo_search, {"return_value": [CARD_H]})
    with k, h:
        assert sources.search("Довод", BASE) == [CARD_H]


@pytest.fixture
def mirrors():
    sources._working_mirror.clear()
    with mock.patch.object(sources.kinogo, "DEFAULT_MIRRORS", ["https://m1.test", "https://m2.test"]):
        yield
    sources._working_mirror.clear()


def test_next_mirror_is_used_when_site_is_down(mirrors):
    def search(query, base):
        if base == "https://m2.test":
            return [CARD_K]
        raise scraper.SiteUnavailable("HTTP 403")

    with mock.patch.object(sources.kinogo, "search", side_effect=search) as k:
        assert sources.search("Довод", BASE) == [CARD_K]
        assert [call.args[1] for call in k.call_args_list] == [BASE, "https://m1.test", "https://m2.test"]
        k.reset_mock()
        # Рабочее зеркало запомнено, но настройка не забыта: при его сбое снова идёт адрес из настроек.
        sources.search("Довод", BASE)
        assert [call.args[1] for call in k.call_args_list] == ["https://m2.test"]


def test_empty_results_do_not_go_to_next_mirror(mirrors):
    with mock.patch.object(sources.kinogo, "search", return_value=[]) as k, \
        mock.patch.object(sources.scraper, "search_movies", return_value=[CARD_H]):
        sources.search("Довод", BASE)
    assert {call.args[1] for call in k.call_args_list} == {BASE}


def test_hdrezka_is_used_when_all_mirrors_are_down(mirrors):
    with mock.patch.object(sources.kinogo, "search", side_effect=scraper.SiteUnavailable()) as k, \
        mock.patch.object(sources.scraper, "search_movies", return_value=[CARD_H]):
        assert sources.search("Довод", BASE) == [CARD_H]
    assert k.call_count == 3


def test_mirror_card_is_recognized_without_source(mirrors):
    assert sources.is_kinogo("https://m2.test/1.html", BASE)
    assert not sources.is_kinogo("https://rezka.test/1.html", BASE)


def _card(title, source="hdrezka"):
    return scraper.MovieSearchResult(title=title, url=f"https://{source}.test/{title}.html", source=source)


def _kinogo_by_query(results):
    return {"side_effect": lambda query, base: results.get(query, [])}


def test_kinogo_is_searched_again_by_other_title_from_hdrezka():
    tenet = _card("Довод (2020)", "kinogo")
    other = _card("Доводы рассудка (2007)", "kinogo")
    k, h = _patches(_kinogo_by_query({"Довод": [tenet, other]}), {"return_value": [_card("Довод / Тенет"), _card("Паутина")]})
    with k as search, h:
        assert sources.search("Тенет", BASE) == [tenet]
    assert [c.args[0] for c in search.call_args_list] == ["Тенет", "Довод"]


def test_only_card_matching_query_gives_other_titles():
    k, h = _patches(_kinogo_by_query({}), {"return_value": [_card("Сети зла / Бредень")]})
    with k as search, h:
        assert len(sources.search("Тенет", BASE)) == 1
    assert [c.args[0] for c in search.call_args_list] == ["Тенет"]


def test_similar_title_on_kinogo_is_not_used_instead_of_hdrezka():
    backup = [_card("Довод / Тенет")]
    k, h = _patches(_kinogo_by_query({"Довод": [_card("Доводы рассудка (2007)", "kinogo")]}), {"return_value": backup})
    with k, h:
        assert sources.search("Тенет", BASE) == backup


def test_retry_failure_keeps_hdrezka_results():
    backup = [_card("Довод / Тенет")]

    def search(query, base):
        if query == "Довод":
            raise scraper.SiteUnavailable()
        return []

    k, h = _patches({"side_effect": search}, {"return_value": backup})
    with k, h:
        assert sources.search("Тенет", BASE) == backup


def test_no_retry_when_kinogo_is_down():
    backup = [_card("Довод / Тенет")]
    k, h = _patches({"side_effect": scraper.SiteUnavailable()}, {"return_value": backup})
    with k as search, h, mock.patch.object(sources.kinogo, "DEFAULT_MIRRORS", []):
        assert sources.search("Тенет", BASE) == backup
    assert search.call_count == 1


def test_title_comparison_ignores_case_yo_and_year():
    k, h = _patches(_kinogo_by_query({"Ёлки": [_card("елки (2010)", "kinogo")]}), {"return_value": [_card("Ёлки / Yolki")]})
    with k, h:
        assert sources.search("YOLKI", BASE)[0].source == "kinogo"


def test_search_reports_unavailable_only_when_both_are_down():
    k, h = _patches({"side_effect": scraper.SiteUnavailable()}, {"side_effect": scraper.SiteUnavailable()})
    with k, h, pytest.raises(scraper.SiteUnavailable):
        sources.search("Довод", BASE)


def test_nothing_found_when_kinogo_empty_and_hdrezka_down():
    k, h = _patches({"return_value": []}, {"side_effect": scraper.SiteUnavailable()})
    with k, h:
        assert sources.search("Довод", BASE) == []


@pytest.mark.parametrize(("title", "clean"), [("Довод (2020)", "Довод"), ("1917 (2019) ", "1917"), ("Без года", "Без года")])
def test_clean_title(title, clean):
    assert sources.clean_title(title) == clean


@pytest.mark.parametrize(
    ("labels", "best"),
    [
        (["240p", "1080p", "720p"], "1080p"),
        (["1080p", "4K", "2K"], "4K"),
        (["Качество не подтверждено", "360p"], "Качество не подтверждено"),
        (["Auto"], "Auto"),
        ([], None),
    ],
)
def test_best_quality(labels, best):
    assert sources.best_quality({label: ["u"] for label in labels}) == best


def test_card_source_beats_address_after_domain_change():
    assert sources.is_kinogo("https://new-domain.test/1.html", BASE, "kinogo") is True
    assert sources.is_kinogo(f"{BASE}/1.html", BASE, "hdrezka") is False
    assert sources.is_kinogo(f"{BASE}/1.html", BASE) is True


def test_broken_movie_page_offers_hdrezka_by_card_title():
    with mock.patch.object(sources.kinogo, "fetch_movie", side_effect=scraper.SiteUnavailable()), \
        mock.patch.object(sources.scraper, "search_movies", return_value=[CARD_H]) as search:
        details = sources.open_movie(f"{BASE}/2.html", mock.Mock(), BASE, source="kinogo", title="Дюна (2024)")
    assert search.call_args.args[0] == "Дюна"
    assert details.alternatives == [CARD_H]


def test_broken_movie_page_without_alternatives_is_unavailable():
    with mock.patch.object(sources.kinogo, "fetch_movie", side_effect=scraper.SiteUnavailable()), \
        mock.patch.object(sources.scraper, "search_movies", return_value=[]):
        with pytest.raises(scraper.SiteUnavailable):
            sources.open_movie(f"{BASE}/2.html", mock.Mock(), BASE, title="Дюна")


def test_open_movie_routes_by_address():
    driver = mock.Mock()
    with mock.patch.object(sources.scraper, "fetch_movie_details", return_value="h") as hdrezka, \
        mock.patch.object(sources.kinogo, "fetch_movie", return_value="k") as kg:
        assert sources.open_movie(f"{BASE}/filmy/1.html", driver, BASE) == "k"
        assert sources.open_movie("https://rezka.test/1.html", driver, BASE) == "h"
    kg.assert_called_once()
    hdrezka.assert_called_once()


def test_movie_without_video_offers_hdrezka_results_and_does_not_autoplay():
    error = kinogo.NoVideo("нет плеера")
    error.details = scraper.MovieDetails(title="Дюна (2024)", url=f"{BASE}/2.html", source="kinogo")
    with mock.patch.object(sources.kinogo, "fetch_movie", side_effect=error), \
        mock.patch.object(sources.scraper, "search_movies", return_value=[CARD_H]) as search:
        details = sources.open_movie(f"{BASE}/2.html", mock.Mock(), BASE)
    assert search.call_args.args[0] == "Дюна"
    assert details.alternatives == [CARD_H]
    assert details.streams == {}


def test_movie_without_video_when_hdrezka_is_down_has_no_alternatives():
    error = kinogo.NoVideo("нет плеера")
    error.details = scraper.MovieDetails(title="Дюна", url=f"{BASE}/2.html", source="kinogo", description="Описание")
    with mock.patch.object(sources.kinogo, "fetch_movie", side_effect=error), \
        mock.patch.object(sources.scraper, "search_movies", side_effect=scraper.SiteUnavailable()):
        assert sources.open_movie(f"{BASE}/2.html", mock.Mock(), BASE).alternatives == []
