"""--search использует порядок источников и запасной вариант."""

from unittest import mock

from mpv_launcher import cli, runner, scraper, settings, sources

CARD = scraper.MovieSearchResult(title="Довод (2020)", url="https://k.test/1.html", source="kinogo")


def _run(details, fallback_details=None):
    driver = mock.Mock()
    with mock.patch.object(sources, "search", return_value=[CARD]) as search, \
        mock.patch.object(settings, "load", return_value={"kinogo_url": "https://k.test"}), \
        mock.patch.object(scraper, "create_headless_driver", return_value=driver), \
        mock.patch.object(sources, "open_movie", return_value=details), \
        mock.patch.object(scraper, "fetch_movie_details", return_value=fallback_details), \
        mock.patch.object(runner, "run_with_fallback", return_value=0) as run:
        code = cli.main(["--search", "Довод"])
    driver.quit.assert_called_once()
    return code, search, run


def test_search_plays_best_kinogo_quality_with_player_referer():
    details = scraper.MovieDetails(
        title="Довод (2020)", url=CARD.url, source="kinogo", referer="https://cinemar.cc/",
        streams={"720p": ["https://a/720.m3u8"], "1080p": ["https://a/1080.m3u8", "https://c/1080.m3u8"]},
    )
    code, search, run = _run(details)
    assert code == 0
    assert search.call_args.args == ("Довод", "https://k.test")
    plan, fallback = run.call_args.args
    assert plan.mpv_args[-1] == "https://a/1080.m3u8"
    assert fallback == ["https://c/1080.m3u8"]
    assert any("Referer: https://cinemar.cc/" in a for a in plan.mpv_args)
    assert "--force-media-title=Довод (2020)" in plan.mpv_args


def test_movie_without_video_lists_candidates_and_does_not_autoplay(capsys):
    empty = scraper.MovieDetails(
        title="Дюна", url=CARD.url, source="kinogo",
        alternatives=[scraper.MovieSearchResult(title="Дюна (1984)", url="https://r.test/1.html")],
    )
    code, _, run = _run(empty)
    assert code == cli.EXIT_NO_URL
    run.assert_not_called()
    assert "Дюна (1984)" in capsys.readouterr().err


def test_highest_quality_wins_regardless_of_order():
    details = scraper.MovieDetails(
        title="Т", url=CARD.url, source="kinogo",
        streams={"240p": ["https://a/240"], "360p": ["https://a/360"]},
    )
    _, _, run = _run(details)
    assert run.call_args.args[0].mpv_args[-1] == "https://a/360"
