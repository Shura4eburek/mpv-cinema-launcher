"""Порядок источников: KinoGo основной, HDRezka запасной. Общий для приложения и CLI."""

from __future__ import annotations

import re
import sys
from typing import Callable
from urllib.parse import urlparse

from . import kinogo, scraper
from .progress import NO_PROGRESS, Progress


MAX_CARDS_FOR_TITLES = 5
MAX_ALTERNATIVE_TITLES = 3


def _log(message: str) -> None:
    print(f"sources: {message}", file=sys.stderr)


def is_kinogo(url: str, kinogo_base: str, source: str | None = None) -> bool:
    """Источник карточки надёжнее адреса: сайт может сменить домен, пока открыта выдача."""
    if source in ("kinogo", "hdrezka", "lampac"):
        return source == "kinogo"
    host = urlparse(url).netloc
    return host in {urlparse(site).netloc for site in (kinogo_base, *kinogo.DEFAULT_MIRRORS)}


def best_quality(streams: dict[str, list[str]]) -> str | None:
    """Подпись варианта с наибольшим разрешением."""
    # Рядом с другими вариантами он бывает, только когда верхние недоступны: остальные заметно хуже.
    if kinogo.UNCONFIRMED in streams:
        return kinogo.UNCONFIRMED

    def rank(label: str) -> int:
        lowered = label.lower()
        if lowered == "4k":
            return 2160
        if lowered == "2k":
            return 1440
        match = re.match(r"(\d+)p", lowered)
        return int(match[1]) if match else 0

    return max(streams, key=rank, default=None)


def clean_title(title: str) -> str:
    """Название для поиска на другом сайте: без года и сезонов в скобках."""
    return re.sub(r"(\s*\((?:\d{4}|\d+(?:\s*-\s*\d+)?\s*сезон\w*)\))+\s*$", "", title, flags=re.I).strip()


def _normalized(title: str) -> str:
    return re.sub(r"\W+", " ", clean_title(title).lower().replace("ё", "е")).strip()


def _alternative_titles(query: str, cards: list[scraper.MovieSearchResult]) -> list[str]:
    """Другие названия фильма из карточек вида «Довод / Тенет», где одно из них совпало с запросом."""
    wanted = _normalized(query)
    titles: list[str] = []
    for card in cards[:MAX_CARDS_FOR_TITLES]:
        parts = [part.strip() for part in card.title.split(" / ")]
        if any(_normalized(part) == wanted for part in parts):
            titles += [part for part in parts if _normalized(part) != wanted]
    return list(dict.fromkeys(titles))[:MAX_ALTERNATIVE_TITLES]


def _kinogo_is_series(url: str, title: str) -> bool | None:
    """Тип страницы KinoGo; ``None``, если его не видно: у части зеркал в адресе нет раздела."""
    if "/serialy/" in url or re.search(r"\d\s*сезон|сезон\s*\d", title, re.I):
        return True
    if "/filmy/" in url or re.search(r"\(\d{4}\)\s*$", title):
        return False
    return None


def _card_is_series(card: scraper.MovieSearchResult) -> bool:
    return "/series/" in card.url or re.match(r"\d{4}\s*-", card.info) is not None


def _card_years(card: scraper.MovieSearchResult) -> tuple[int, int | None] | None:
    """Первый и последний год. Сериал, который ещё идёт, последнего года не имеет."""
    match = re.match(r"(\d{4})(\s*-\s*(\d{4})?)?", card.info)
    if not match:
        return None
    first = int(match[1])
    if match[2] is None:
        return first, first
    return first, int(match[3]) if match[3] else None


def _year_fits(card: scraper.MovieSearchResult, year: int) -> bool:
    """Запас в год: сайты расходятся в дате выхода."""
    years = _card_years(card)
    if years is None:
        return True
    return years[0] - 1 <= year and (years[1] is None or year <= years[1] + 1)


def single_match(
    cards: list[scraper.MovieSearchResult],
    title: str,
    is_series: bool | None,
    year_text: str | None = None,
) -> scraper.MovieSearchResult | None:
    """Единственная карточка того же фильма или сериала; при сомнении ``None``, тогда выбирает зритель."""
    wanted = {_normalized(part) for part in title.split(" / ")}
    found = [card for card in cards if wanted & {_normalized(part) for part in card.title.split(" / ")}]
    if is_series is not None:
        found = [card for card in found if _card_is_series(card) == is_series]
    match = re.search(r"\d{4}", year_text or "") or re.search(r"\d{4}(?=\)\s*$)", title)
    if match:
        year = int(match[0])
        found = [card for card in found if _year_fits(card, year)]
        if len(found) > 1:
            found = [card for card in found if (_card_years(card) or (None,))[0] == year]
    return found[0] if len(found) == 1 else None


# Адрес из настроек -> зеркало, ответившее последним: мёртвый сайт не задерживает каждый поиск.
_working_mirror: dict[str, str] = {}


def _search_kinogo(query: str, kinogo_base: str) -> list[scraper.MovieSearchResult]:
    """Следующее зеркало пробуется, только если сайт недоступен: пустая выдача — это ответ."""
    mirrors = [_working_mirror.get(kinogo_base, kinogo_base), kinogo_base, *kinogo.DEFAULT_MIRRORS]
    failure: scraper.SiteUnavailable | None = None
    for mirror in dict.fromkeys(mirrors):
        try:
            results = kinogo.search(query, mirror)
        except scraper.SiteUnavailable as exc:
            _log(f"зеркало KinoGo недоступно: {urlparse(mirror).netloc}")
            failure = exc
            continue
        _working_mirror[kinogo_base] = mirror
        return results
    raise failure


def _search_kinogo_by_titles(titles: list[str], kinogo_base: str) -> list[scraper.MovieSearchResult]:
    """Только точные совпадения: похожее название здесь скорее окажется другим фильмом."""
    for title in titles:
        try:
            found = _search_kinogo(title, kinogo_base)
        except scraper.SiteUnavailable:
            return []
        exact = [card for card in found if _normalized(card.title) == _normalized(title)]
        if exact:
            _log("KinoGo нашёл фильм по другому названию из HDRezka")
            return exact
    return []


def search(query: str, kinogo_base: str, get_driver: Callable | None = None) -> list[scraper.MovieSearchResult]:
    kinogo_down = False
    try:
        results = _search_kinogo(query, kinogo_base)
    except scraper.SiteUnavailable as exc:
        _log(f"KinoGo недоступен при поиске: {exc}")
        kinogo_down = True
        results = []
    if results:
        return results

    _log("поиск через HDRezka")
    try:
        backup = scraper.search_movies(query, get_driver=get_driver, raise_on_unavailable=True)
    except scraper.SiteUnavailable:
        if kinogo_down:
            raise
        return []
    # На KinoGo у фильма может быть только одно из названий: там же лучше качество.
    if not kinogo_down:
        found = _search_kinogo_by_titles(_alternative_titles(query, backup), kinogo_base)
        if found:
            return found
    return backup


def _open_backup(url: str, driver, get_driver: Callable | None, progress: Progress) -> scraper.MovieDetails | None:
    """Страница HDRezka вместо списка; при сбое остаётся список."""
    progress.check()
    try:
        with progress.step("page", browser=True):
            opened = scraper.fetch_movie_details(url, driver=driver or (get_driver() if get_driver else None))
    except Exception as exc:
        # Отмена могла закрыть Chrome: тогда это не сбой сайта, и список уже не нужен.
        progress.check()
        _log(f"страница HDRezka не открылась: {type(exc).__name__}")
        return None
    if not (opened.translators or opened.streams or opened.series):
        _log("страница HDRezka без видео, остаётся список")
        return None
    opened.switched_from = "kinogo"
    _log("открыта страница HDRezka вместо KinoGo")
    return opened


def open_movie(
    url: str,
    driver,
    kinogo_base: str,
    get_driver: Callable | None = None,
    source: str | None = None,
    title: str | None = None,
    voice: str | None = None,
    progress: Progress = NO_PROGRESS,
) -> scraper.MovieDetails:
    """Страница фильма. Если KinoGo не дал видео, открывается то же название на HDRezka,
    а при сомнении в alternatives попадают её фильмы на выбор."""
    if not is_kinogo(url, kinogo_base, source):
        with progress.step("page", browser=True):
            return scraper.fetch_movie_details(url, driver=driver or (get_driver() if get_driver else None))

    try:
        return kinogo.fetch_movie(
            url, driver, kinogo_base, voice=voice, strict=False, progress=progress, get_driver=get_driver
        )
    except kinogo.NoVideo as exc:
        _log(f"KinoGo без видео: {exc}")
        details = exc.details or scraper.MovieDetails(title=title or "Фильм", url=url, source="kinogo")
    except scraper.SiteUnavailable as exc:
        _log(f"страница KinoGo недоступна: {exc}")
        # Без названия искать на другом сайте нечего.
        if not title:
            raise
        details = scraper.MovieDetails(title=title, url=url, source="kinogo")

    # Отмена могла закрыть Chrome: это не повод идти на запасной источник.
    progress.check()
    try:
        with progress.step("fallback", browser=True):
            details.alternatives = scraper.search_movies(
                clean_title(details.title),
                driver=driver,
                get_driver=get_driver,
                raise_on_unavailable=True,
            )
    except scraper.SiteUnavailable as exc:
        _log(f"HDRezka недоступна: {exc}")

    match = single_match(
        details.alternatives,
        details.title,
        _kinogo_is_series(url, details.title),
        details.info_table.get("Год"),
    )
    if match is not None:
        opened = _open_backup(match.url, driver, get_driver, progress)
        if opened is not None:
            return opened
    if not (details.description or details.alternatives):
        raise scraper.SiteUnavailable("оба источника недоступны")
    return details
