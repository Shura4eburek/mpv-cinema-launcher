"""Тесты нового функционала скраппера, парсинга качеств, озвучек и параметров апскейла/интерполяции."""

from mpv_launcher import presets, scraper
from mpv_launcher.cli import Options, parse


def test_parse_streams_with_qualities():
    raw_text = (
        r"[1080p]https:\/\/prx.net\/v1080.mp4:hls:manifest.m3u8 or "
        r"https:\/\/stream.org\/v1080.mp4:hls:manifest.m3u8,"
        r"[720p]https:\/\/prx.net\/v720.mp4:hls:manifest.m3u8"
    )
    result = scraper.parse_streams_with_qualities(raw_text)
    assert "1080p" in result
    assert "720p" in result
    assert len(result["1080p"]) == 2
    assert "https://prx.net/v1080.mp4:hls:manifest.m3u8" in result["1080p"]
    assert "https://stream.org/v1080.mp4:hls:manifest.m3u8" in result["1080p"]
    assert result["720p"] == ["https://prx.net/v720.mp4:hls:manifest.m3u8"]


def test_parse_streams_fallback_auto():
    raw_text = r"https:\/\/cdn.example.com\/stream.m3u8"
    result = scraper.parse_streams_with_qualities(raw_text)
    assert "Auto" in result
    assert result["Auto"] == ["https://cdn.example.com/stream.m3u8"]


def test_rank_search_results():
    items = [
        scraper.MovieSearchResult(title="Другой фильм", url="http://1"),
        scraper.MovieSearchResult(title="Довод / Тенет", url="http://2"),
        scraper.MovieSearchResult(title="Паутина", url="http://3"),
    ]
    ranked = scraper.rank_search_results(items, "Тенет")
    assert ranked[0].title == "Довод / Тенет"


def test_movie_details_structure():
    details = scraper.MovieDetails(
        title="Тест",
        url="http://test",
        translators=[
            scraper.Translator(id="56", name="Дубляж", active=True),
            scraper.Translator(id="55", name="Закадровый", active=False),
        ]
    )
    assert len(details.translators) == 2
    assert details.translators[0].id == "56"
    assert details.translators[0].name == "Дубляж"


def test_interpolation_enabled():
    opts = Options(url="https://h/x.m3u8", interpolation=True)
    plan = presets.build_plan(opts, "generic")
    assert "--video-sync=display-resample" in plan.mpv_args
    assert "--interpolation=yes" in plan.mpv_args
    assert "--tscale=mitchell" in plan.mpv_args


def test_interpolation_disabled():
    opts = Options(url="https://h/x.m3u8", interpolation=False)
    plan = presets.build_plan(opts, "generic")
    assert "--interpolation=no" in plan.mpv_args
    assert "--video-sync=display-resample" not in plan.mpv_args


def test_upscale_quality_basic():
    opts = Options(url="https://h/x.m3u8", upscale_quality="basic")
    plan = presets.build_plan(opts, "desktop-4070ti")
    assert "--profile=gpu-hq" in plan.mpv_args


def test_cli_search_argument():
    opts = parse(["--search", "Тенет", "--no-interpolation", "--upscale", "basic"])
    assert opts.search == "Тенет"
    assert opts.interpolation is False
    assert opts.upscale_quality == "basic"


def test_mirrors_configuration():
    assert len(scraper.DEFAULT_MIRRORS) >= 3
    assert "https://rezka-ua.pub" in scraper.DEFAULT_MIRRORS
    scraper.set_base_url("https://custom-mirror.tv")
    assert scraper.get_base_url() == "https://custom-mirror.tv"
    # Восстанавливаем дефолт
    scraper.set_base_url(scraper.DEFAULT_MIRRORS[0])
    assert scraper.get_base_url() == scraper.DEFAULT_MIRRORS[0]

