"""Разбор аргументов и главный поток лаунчера."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Коды выхода (контракт — см. specs/.../contracts/cli.md).
EXIT_OK = 0
EXIT_ARGS = 2
EXIT_NO_URL = 3
EXIT_NO_MPV = 4


@dataclass
class Options:
    """Разобранные аргументы командной строки."""

    url: str | None = None
    profile: str = "auto"
    content: str = "film"
    interpolation: bool | None = None
    upscale_quality: str = "max"
    referer: str | None = None
    user_agent: str | None = None
    headers: list[str] = field(default_factory=list)
    dry_run: bool = False
    search: str | None = None
    title: str | None = None
    ready_file: str | None = None
    vsr: bool = False
    wid: int | None = None
    ipc_server: str | None = None
    start: float | None = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mpvplay",
        description="Запуск HLS-потока (.m3u8) в mpv с апскейлом под железо.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="ссылка на поток; если не указана — поиск или буфер обмена",
    )
    parser.add_argument(
        "--search",
        "-s",
        dest="search",
        default=None,
        help="поиск фильма по названию и запуск потока",
    )
    parser.add_argument(
        "--profile",
        choices=["auto", "desktop-4070ti", "air-m1", "generic"],
        default="auto",
        help="класс машины / профиль апскейла (по умолчанию auto)",
    )
    content = parser.add_mutually_exclusive_group()
    content.add_argument(
        "--film", dest="content", action="store_const", const="film",
        help="пресет кино/сериалы (по умолчанию)",
    )
    content.add_argument(
        "--anime", dest="content", action="store_const", const="anime",
        help="пресет аниме/анимация",
    )
    parser.set_defaults(content="film")
    
    interp = parser.add_mutually_exclusive_group()
    interp.add_argument(
        "--interpolation", dest="interpolation", action="store_true", default=None,
        help="принудительно включить интерполяцию кадров",
    )
    interp.add_argument(
        "--no-interpolation", dest="interpolation", action="store_false",
        help="отключить интерполяцию кадров",
    )
    
    parser.add_argument(
        "--upscale",
        dest="upscale_quality",
        choices=["max", "balanced", "basic"],
        default="max",
        help="качество апскейла: max или basic (balanced оставлен для совместимости и равен max)",
    )
    parser.add_argument("--referer", default=None, help="заголовок Referer")
    parser.add_argument(
        "--user-agent", dest="user_agent", default=None, help="заголовок User-Agent"
    )
    parser.add_argument(
        "--header",
        dest="headers",
        action="append",
        default=[],
        metavar='"Name: Value"',
        help="произвольный HTTP-заголовок; можно повторять",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="напечатать команду mpv и выйти, не запуская",
    )
    return parser


def parse(argv) -> Options:
    """Разобрать argv в Options. При ошибке argparse делает sys.exit(2)."""
    namespace = _build_parser().parse_args(argv)
    return Options(
        url=namespace.url,
        search=namespace.search,
        profile=namespace.profile,
        content=namespace.content,
        interpolation=namespace.interpolation,
        upscale_quality=namespace.upscale_quality,
        referer=namespace.referer,
        user_agent=namespace.user_agent,
        headers=list(namespace.headers),
        dry_run=namespace.dry_run,
    )


def main(argv=None) -> int:
    """Точка входа console-script `mpvplay`."""
    if argv is None:
        argv = sys.argv[1:]

    options = parse(argv)

    from . import clipboard, machine, presets, runner
    from . import url as url_mod
    from . import scraper, settings, sources

    fallback_urls: list[str] = []

    # Если передан флаг --search
    if options.search:
        print(f"Поиск фильма: '{options.search}'...")
        kinogo_base = settings.load()["kinogo_url"]
        try:
            results = sources.search(options.search, kinogo_base)
        except scraper.SiteUnavailable:
            results = []
        if not results:
            print("Фильмы не найдены.", file=sys.stderr)
            return EXIT_NO_URL
        print(f"Найдено фильмов: {len(results)}")
        for idx, r in enumerate(results[:5], 1):
            print(f"{idx}. {r.title} ({r.info})")
            
        target = results[0]
        print(f"\nЗагрузка потоков для: {target.title}...")
        driver = scraper.create_headless_driver()
        try:
            details = sources.open_movie(
                target.url, driver, kinogo_base, source=target.source, title=target.title
            )
        except scraper.SiteUnavailable:
            print("Не удалось открыть страницу фильма.", file=sys.stderr)
            return EXIT_NO_URL
        finally:
            if driver:
                driver.quit()
        # Похожее название может оказаться другим фильмом, поэтому сами его не запускаем.
        if not details.streams and details.alternatives:
            print("Видео не найдено. Похожие фильмы в запасном источнике:", file=sys.stderr)
            for item in details.alternatives[:5]:
                print(f"  {item.title} ({item.info}): {item.url}", file=sys.stderr)
            return EXIT_NO_URL
        options.referer = options.referer or details.referer or None
        if not details.streams:
            print("Не удалось найти потоки для выбранного фильма.", file=sys.stderr)
            return EXIT_NO_URL
            
        quality = sources.best_quality(details.streams)
        chosen_stream, *fallback_urls = details.streams[quality]
        print(f"Выбрано качество: {quality}")

        options.url = chosen_stream
        options.title = details.title or target.title

    if not options.url:
        options.url = clipboard.read()

    if not url_mod.validate(options.url):
        print(
            "Не найдена пригодная ссылка на поток (.m3u8). Передайте её "
            "аргументом, через --search или скопируйте в буфер обмена.",
            file=sys.stderr,
        )
        return EXIT_NO_URL

    options.url = options.url.strip()
    profile = machine.resolve(options.profile)
    plan = presets.build_plan(options, profile)
    return runner.run_with_fallback(plan, fallback_urls, dry_run=options.dry_run)


if __name__ == "__main__":
    sys.exit(main())
