"""Модуль скраппинга фильмов, деталей, озвучек и m3u8-потоков с HDRezka."""

from __future__ import annotations

import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError as exc:
    print(f"Selenium недоступен: {exc}", file=sys.stderr)
    SELENIUM_AVAILABLE = False


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

DEFAULT_MIRRORS = [
    "https://rezka-ua.pub",
    "https://hdrezka.me",
    "https://rezka.ag",
    "https://hdrezka-home.tv",
]

BASE_URL = DEFAULT_MIRRORS[0]


def get_base_url() -> str:
    """Получить текущий базовый URL зеркала."""
    return BASE_URL


def set_base_url(url: str) -> None:
    """Установить текущий базовый URL зеркала."""
    global BASE_URL
    BASE_URL = url.rstrip("/")



@dataclass
class MovieSearchResult:
    """Элемент выдачи поиска."""
    title: str
    url: str
    poster_url: str | None = None
    info: str = ""
    source: str = "hdrezka"


MAX_ACTORS = 12
MAX_RELATED = 8


@dataclass
class Translator:
    """Озвучка / переводчик фильма."""
    id: str
    name: str
    active: bool = False


@dataclass
class Episode:
    """Серия. Идентификатор передаётся сайту как есть, поэтому строка."""
    id: str
    name: str


@dataclass
class Season:
    """Сезон. У KinoGo серии известны только у текущего сезона, у остальных список пуст."""
    id: str
    name: str
    episodes: list[Episode] = field(default_factory=list)


@dataclass
class SeriesInfo:
    """Сезоны и серии выбранной озвучки; ``moved``: запрошенной серии нет, выбрана ближайшая."""
    seasons: list[Season]
    season: str
    episode: str
    moved: bool = False


@dataclass
class MovieDetails:
    """Полные метаданные фильма, озвучки и найденные потоки по качествам."""
    title: str
    url: str
    orig_title: str | None = None
    poster_url: str | None = None
    description: str = ""
    info_table: dict[str, str] = field(default_factory=dict)
    translators: list[Translator] = field(default_factory=list)
    active_translator_id: str | None = None
    streams: dict[str, list[str]] = field(default_factory=dict)
    source: str = "hdrezka"
    referer: str = ""
    alternatives: list[MovieSearchResult] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    related: list[MovieSearchResult] = field(default_factory=list)
    series: SeriesInfo | None = None
    switched_from: str | None = None


def get_random_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def create_headless_driver():
    """Создать скрытый Chrome WebDriver с обходом проверок."""
    if not SELENIUM_AVAILABLE:
        return None

    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--mute-audio")  # реклама в плеерах сайтов не должна звучать
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-agent={USER_AGENTS[0]}")

    try:
        return webdriver.Chrome(options=options)
    except Exception as exc:
        print(f"Не удалось запустить Chrome: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def rank_search_results(items: list[MovieSearchResult], query: str) -> list[MovieSearchResult]:
    """Сортировка результатов поиска: точные совпадения названия идут первыми."""
    query_lower = query.lower().strip()
    words = [w for w in re.split(r"\s+", query_lower) if len(w) > 1]

    def score(item: MovieSearchResult) -> int:
        title = item.title.lower()
        if query_lower in title:
            return 3
        if any(w in title for w in words):
            return 2
        return 1

    return sorted(items, key=score, reverse=True)


class SiteUnavailable(Exception):
    """Ни одно зеркало не ответило: это не то же самое, что пустая выдача."""


def search_movies(
    query: str,
    driver=None,
    mirror_list: list[str] | None = None,
    raise_on_unavailable: bool = False,
    get_driver=None,
) -> list[MovieSearchResult]:
    """Поиск фильмов на HDRezka по названию с автоматическим перебором зеркал.

    ``get_driver`` запускает браузер только тогда, когда обычных запросов не хватило.
    """
    if not query.strip():
        return []

    # Формируем список для перебора: сначала текущий BASE_URL, затем остальные
    mirrors = mirror_list or ([BASE_URL] + [m for m in DEFAULT_MIRRORS if m != BASE_URL])
    content = ""

    # 1. Быстрый HTTP-запрос через requests (пробуем зеркала по очереди)
    for mirror in mirrors:
        search_url = f"{mirror}/search/?do=search&subaction=search&q={quote(query)}"
        try:
            resp = requests.get(search_url, headers=get_random_headers(), timeout=5)
            if resp.status_code == 200 and "anubis" not in resp.text.lower() and "loginform" not in resp.text.lower():
                resp.encoding = "utf-8"
                content = resp.text
                set_base_url(mirror)
                break
        except Exception:
            continue

    # 2. Если все дали ошибку или проверку Anubis — пробуем через Selenium
    if not content and driver is None and get_driver is not None:
        driver = get_driver()
    if not content and driver:
        for mirror in mirrors:
            search_url = f"{mirror}/search/?do=search&subaction=search&q={quote(query)}"
            try:
                driver.get(search_url)
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(2)
                src = driver.page_source
                if "anubis" not in src.lower() and "loginform" not in src.lower() and "b-content__inline_item" in src:
                    content = src
                    set_base_url(mirror)
                    break
            except Exception:
                continue

    if not content:
        if raise_on_unavailable:
            raise SiteUnavailable()
        return []

    soup = BeautifulSoup(content, "html.parser")
    results: list[MovieSearchResult] = []

    for item in soup.select(".b-content__inline_item"):
        a_tag = item.select_one(".b-content__inline_item-link a")
        if not a_tag:
            continue
        href = a_tag.get("href")
        if not href:
            continue

        full_url = urljoin(BASE_URL, href)
        title = a_tag.text.strip()
        img = item.select_one(".b-content__inline_item-cover img")
        poster = img.get("src") if img else None
        if poster and not poster.startswith("http"):
            poster = urljoin(BASE_URL, poster)

        info_div = item.select_one(".b-content__inline_item-link div")
        info = info_div.text.strip() if info_div else ""

        results.append(MovieSearchResult(
            title=title,
            url=full_url,
            poster_url=poster,
            info=info,
        ))

    return rank_search_results(results, query)


def parse_streams_with_qualities(text: str) -> dict[str, list[str]]:
    """Извлечь потоки с группировкой по качествам (1080p, 720p, 480p, 360p)."""
    clean_text = text.replace(r"\/", "/")
    quality_matches = re.findall(
        r"\[(\w+)\]([^,]+(?:\.m3u8|manifest\.m3u8)[^,]*)",
        clean_text,
        re.IGNORECASE
    )

    streams_by_quality: dict[str, list[str]] = {}
    for q_label, raw_urls in quality_matches:
        quality_name = q_label.upper() if not q_label.endswith("p") else q_label
        urls = []
        for part in re.split(r"\s+or\s+|\s+", raw_urls.strip()):
            clean = re.sub(r"^\[\w+\]", "", part).strip()
            clean = re.split(r"[\"'<>\s]", clean)[0]
            if ".m3u8" in clean.lower():
                urls.append(clean)
        if urls:
            if quality_name not in streams_by_quality:
                streams_by_quality[quality_name] = []
            for u in urls:
                if u not in streams_by_quality[quality_name]:
                    streams_by_quality[quality_name].append(u)

    if not streams_by_quality:
        raw_m3u8 = re.findall(
            r"(https?://[^,\"\'<>\s]+(?:\.m3u8|manifest\.m3u8)[^,\"\'<>\s]*)",
            clean_text,
            re.IGNORECASE
        )
        generic_urls = []
        for raw in raw_m3u8:
            clean = re.split(r"[\"'<>\s]", raw)[0]
            if ".m3u8" in clean.lower() and clean not in generic_urls:
                generic_urls.append(clean)
        if generic_urls:
            streams_by_quality["Auto"] = generic_urls

    return streams_by_quality


def _first_number(text: str | None) -> int | None:
    match = re.search(r"\d+", text or "")
    return int(match[0]) if match else None


def nearest_id(ids: list[str], wanted: str | None) -> str | None:
    """Тот же идентификатор, иначе ближайший по номеру, иначе первый."""
    if not ids:
        return None
    if wanted in ids:
        return wanted
    number = _first_number(wanted)
    if number is None:
        return ids[0]
    numbered = [(abs(_first_number(item) - number), item) for item in ids if _first_number(item) is not None]
    return min(numbered, key=lambda pair: pair[0])[1] if numbered else ids[0]


def nearest_episode(seasons: list[Season], season: str, episode: str | None) -> tuple[str, str, bool] | None:
    """Сезон, серия и признак замены. ``episode=None``: зритель выбрал сезон, это его первая серия."""
    usable = [item for item in seasons if item.episodes]
    season_id = nearest_id([item.id for item in usable], season)
    if season_id is None:
        return None
    episodes = [item.id for item in next(s for s in usable if s.id == season_id).episodes]
    if season_id != season:
        return season_id, episodes[0], True
    if episode is None:
        return season_id, episodes[0], False
    episode_id = nearest_id(episodes, episode)
    return season_id, episode_id, episode_id != episode


def parse_series(soup, seasons_soup=None) -> SeriesInfo | None:
    """Сезоны и серии. Разметка страницы и ответа ``get_episodes`` одна. У фильма серий нет."""
    names = {
        item["data-tab_id"]: item.get_text(strip=True)
        for item in (seasons_soup or soup).select(".b-simple_season__item[data-tab_id]")
    }
    grouped: dict[str, list[Episode]] = {}
    active: tuple[str, str] | None = None
    for item in soup.select(".b-simple_episode__item[data-season_id][data-episode_id]"):
        season_id, episode_id = item["data-season_id"], item["data-episode_id"]
        grouped.setdefault(season_id, []).append(Episode(episode_id, item.get_text(strip=True) or f"Серия {episode_id}"))
        if "active" in item.get("class", []):
            active = (season_id, episode_id)
    if not grouped:
        return None
    first_season = next(iter(grouped))
    season, episode = active or (first_season, grouped[first_season][0].id)
    return SeriesInfo(
        seasons=[Season(key, names.get(key) or f"Сезон {key}", episodes) for key, episodes in grouped.items()],
        season=season,
        episode=episode,
    )


def parse_translators(soup) -> list[Translator]:
    translators = []
    for item in soup.select(".b-translator__item"):
        translator_id = item.get("data-translator_id")
        if translator_id:
            translators.append(Translator(id=translator_id, name=item.text.strip(), active="active" in item.get("class", [])))
    return translators


def series_translator_id(html: str) -> str | None:
    """Озвучка сериала, если список озвучек не показан: у единственной озвучки его нет."""
    match = re.search(r"initCDNSeriesEvents\(\s*\d+\s*,\s*(\d+)", html)
    return match[1] if match else None


def parse_actors(soup) -> list[str]:
    names = (tag.get_text(strip=True) for tag in soup.select("[itemprop=actor] [itemprop=name]"))
    return [name for name in names if name][:MAX_ACTORS]


def parse_related(soup, page_url: str) -> list[MovieSearchResult]:
    """Рекомендации сайта. Он ссылается на другие зеркала, поэтому хост берётся у текущей страницы."""
    host = urlparse(page_url)
    related: list[MovieSearchResult] = []
    for item in soup.select(".b-sidelist .b-content__inline_item"):
        link = item.select_one(".b-content__inline_item-link a[href]")
        info = item.select_one(".b-content__inline_item-link div")
        info_text = info.get_text(strip=True) if info else ""
        if link is None:
            continue
        image = item.select_one(".b-content__inline_item-cover img")
        related.append(MovieSearchResult(
            title=link.get_text(strip=True),
            url=urlparse(link["href"])._replace(scheme=host.scheme, netloc=host.netloc).geturl(),
            poster_url=urljoin(page_url, image["src"]) if image and image.get("src") else None,
            info=info_text,
        ))
    return related[:MAX_RELATED]


def fetch_movie_details(url: str, driver=None) -> MovieDetails:
    """Загрузить страницу фильма через Selenium, извлечь детали, список озвучек и потоки."""
    close_driver = False
    if driver is None:
        driver = create_headless_driver()
        close_driver = True

    if not driver:
        return MovieDetails(title="Ошибка: нет Selenium", url=url)

    try:
        driver.get(url)

        # Ждем завершения проверки Anubis и появления плеера
        t0 = time.time()
        while time.time() - t0 < 12:
            time.sleep(1)
            title = (driver.title or "").lower()
            source = driver.page_source or ""
            if "проверка" not in title and ("manifest.m3u8" in source or "<video" in source or "player" in source):
                break

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # Название
        title_tag = soup.select_one(".b-post__title h1")
        title = title_tag.text.strip() if title_tag else (driver.title or "Фильм")

        # Оригинальное название
        orig_tag = soup.select_one(".b-post__origtitle")
        orig_title = orig_tag.text.strip() if orig_tag else None

        # Постер
        poster_tag = soup.select_one(".b-sidecover img")
        poster_url = poster_tag.get("src") if poster_tag else None
        if poster_url and not poster_url.startswith("http"):
            poster_url = urljoin(BASE_URL, poster_url)

        # Описание
        desc_tag = soup.select_one(".b-post__description_text")
        description = desc_tag.text.strip() if desc_tag else ""

        # Таблица характеристик
        info_table: dict[str, str] = {}
        for tr in soup.select(".b-post__info tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                key = tds[0].text.strip().rstrip(":")
                val = tds[1].text.strip()
                info_table[key] = val

        # Список доступных озвучек
        translators = parse_translators(soup)
        active_t_id = next((item.id for item in translators if item.active), None)
        if translators and not active_t_id:
            active_t_id = translators[0].id
        series = parse_series(soup)
        if series is not None and not active_t_id:
            active_t_id = series_translator_id(html)

        # Потоки текущей озвучки
        streams = parse_streams_with_qualities(html)

        return MovieDetails(
            title=title,
            url=url,
            orig_title=orig_title,
            poster_url=poster_url,
            description=description,
            info_table=info_table,
            translators=translators,
            active_translator_id=active_t_id,
            streams=streams,
            actors=parse_actors(soup),
            related=parse_related(soup, url),
            series=series,
        )
    finally:
        if close_driver:
            driver.quit()


_CDN_REQUEST = """
    const data = arguments[0];
    let post_id = document.querySelector('[data-post_id]') ?
                  document.querySelector('[data-post_id]').getAttribute('data-post_id') : null;
    if (!post_id) {
        const m = window.location.href.match(/\\/(\\d+)-/);
        post_id = m ? m[1] : null;
    }
    let result = null;
    $.ajax({
        url: '/ajax/get_cdn_series/?t=' + Date.now(),
        type: 'POST',
        data: {...data, id: post_id},
        async: false,
        success: function(resp) {
            result = resp;
        }
    });
    return result;
"""


def _cdn_request(driver, data: dict) -> dict:
    """Запрос к плееру в контексте страницы фильма."""
    raw = driver.execute_script(_CDN_REQUEST, data)
    if not raw:
        return {}
    return raw if isinstance(raw, dict) else json.loads(raw)


def _series_request(driver, data: dict) -> dict:
    """Сбой запроса (страница проверки, разрыв) можно повторить, в отличие от отказа сайта."""
    try:
        response = _cdn_request(driver, data)
    except Exception as exc:
        raise SiteUnavailable(type(exc).__name__) from exc
    if not response:
        raise SiteUnavailable("нет ответа")
    return response


def _streams_from(response: dict) -> dict[str, list[str]]:
    url_string = response.get("url")
    # На отказ сайт отвечает "url": false или "success": false. Сообщение «Время сессии истекло»
    # здесь не про сессию: так сайт отвечает на любые неверные параметры.
    if not isinstance(url_string, str):
        print(f"Сайт не отдал поток: {response.get('message', '')}", file=sys.stderr)
        return {}
    return parse_streams_with_qualities(url_string)


def fetch_translator_streams(url: str, translator_id: str, driver) -> dict[str, list[str]]:
    """Получить потоки озвучки фильма через AJAX запрос в контексте страницы."""
    if not driver:
        return {}
    return _streams_from(_cdn_request(driver, {
        "action": "get_movie",
        "translator_id": translator_id,
        "is_camrip": 0,
        "is_ads": 0,
        "is_director": 0,
    }))


def fetch_series_list(driver, translator_id: str) -> SeriesInfo | None:
    """Сезоны и серии озвучки: их набор у разных озвучек различается."""
    response = _series_request(driver, {"action": "get_episodes", "translator_id": translator_id})
    if not isinstance(response.get("episodes"), str):
        print(f"Сайт не отдал серии: {response.get('message', '')}", file=sys.stderr)
        return None
    seasons_html = response.get("seasons")
    return parse_series(
        BeautifulSoup(response["episodes"], "html.parser"),
        BeautifulSoup(seasons_html if isinstance(seasons_html, str) else "", "html.parser"),
    )


def fetch_episode_streams(driver, translator_id: str, season: str, episode: str) -> dict[str, list[str]]:
    return _streams_from(_series_request(driver, {
        "action": "get_stream",
        "translator_id": translator_id,
        "season": season,
        "episode": episode,
    }))


def fetch_episode(url: str, driver, translator_id: str | None, season: str, episode: str | None) -> MovieDetails:
    """Потоки серии в выбранной озвучке. Драйвер должен стоять на странице сериала."""
    html = driver.page_source
    translators = parse_translators(BeautifulSoup(html, "html.parser"))
    translator_id = translator_id or next((t.id for t in translators if t.active), None) or series_translator_id(html)
    details = MovieDetails(title="", url=url, active_translator_id=translator_id)
    details.translators = [Translator(t.id, t.name, t.id == translator_id) for t in translators]
    if not translator_id:
        return details

    series = fetch_series_list(driver, translator_id)
    chosen = nearest_episode(series.seasons, season, episode) if series else None
    if chosen is None:
        return details
    series.season, series.episode, series.moved = chosen
    details.series = series
    details.streams = fetch_episode_streams(driver, translator_id, series.season, series.episode)
    return details
