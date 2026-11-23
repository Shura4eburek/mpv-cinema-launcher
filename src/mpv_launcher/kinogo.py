"""Источник KinoGo: поиск и страница — обычные запросы, поток — из плеера в Chrome.

Плеер раздаёт поток через сервер ``cfnd``, где вариант 1080 на деле 720p. Настоящее качество
отдаёт сервер ``atlas``. Это недокументированный путь, поэтому ``cfnd`` и HDRezka — запасные.
"""

from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import NamedTuple
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .progress import NO_PROGRESS, Cancelled, Progress
from .scraper import MAX_ACTORS, MAX_RELATED, Episode, MovieDetails, MovieSearchResult, Season, SeriesInfo, SiteUnavailable, Translator, get_random_headers, nearest_id

try:
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
except ImportError:
    ActionChains = None
    By = None

# Первые три проверены полным путём: поиск, страница фильма и поток. Остальные добавлены по просьбе
# пользователя: на момент добавления они отвечали 403 от Cloudflare, состояние показывает экран проверки зеркал.
DEFAULT_MIRRORS = [
    "https://uakinogo.io",
    "https://uakinogo.org",
    "https://uakinogo.tv",
    "https://kinogo.luxury",
    "https://kinogo.no",
    "https://go3.kinogo.cc",
    "https://kinogo.biz",
    "https://kinogo.media",
    "https://kinogo4.com",
]

# У зеркал две вёрстки: uakinogo.io и .org (первый селектор) и uakinogo.tv (второй).
_SEARCH_CARD = "article.shortStory, .shortstory"
_CARD_LINK = "h2 a[href], .shortstory__title a[href]"
_CARD_POSTER = ".sPoster img, .shortstory__poster img"
_MOVIE_POSTER = ".sPoster img, .movie_poster img"
_MOVIE_FACTS = ".sInfo b, .movie__info b"
_PLAYER_FRAME = ".js-player-container iframe, .kg-video-container iframe"
_RELATED_LINK = ".relatedItem a[href], a.related-item[href]"

ATLAS_HOST = "atlas.host.cinemap.cc"
STREAM_HOST_MARK = "cinemap"
PLAYER_HOST_MARK = "cinemar"
PLAYER_REFERER = "https://cinemar.cc/"
UNCONFIRMED = "Качество не подтверждено"
MIN_MOVIE_SECONDS = 1200
REQUEST_TIMEOUT = 5
PAGE_ATTEMPTS = 2
VOICE_SWITCH_WAIT_SECONDS = 15
LIST_UPDATE_SECONDS = 1
STREAM_REQUEST_TIMEOUT = 4
ATLAS_CONNECT_TIMEOUT = 1.5
ATLAS_ATTEMPTS = 2
FRAME_WAIT_SECONDS = 10
STREAM_WAIT_SECONDS = 15
POLL_SECONDS = 0.4

# Нижние границы ширины: кадр бывает обрезан (например, 1916×800), а метка должна остаться честной.
_LABEL_BY_MIN_WIDTH = ((3000, "2160p"), (2200, "1440p"), (1600, "1080p"), (1100, "720p"), (760, "480p"), (560, "360p"))
_INFO_KEYS = {
    "Рік випуску": "Год",
    "Вышел в": "Год",
    "Сняли в": "Страна",
    "Жанры": "Жанр",
    "Год выпуска": "Год",
    "Країна": "Страна",
    "Страна": "Страна",
    "Жанр": "Жанр",
    "Режисер": "Режиссер",
    "Режиссер": "Режиссер",
}
_ORIG_TITLE_KEYS = ("Зарубіжна назва", "Зарубежное название", "Оригинальное название")


class NoVideo(Exception):
    """Фильм на сайте есть, но видео получить нельзя (трейлер, другой плеер, сбой)."""

    details: MovieDetails | None = None


def _log(message: str) -> None:
    print(f"kinogo: {message}", file=sys.stderr)


def _get_page(url: str, progress: Progress = NO_PROGRESS) -> str:
    # Сайт иногда разово обрывает соединение: без повтора приложение зря ушло бы на запасной источник.
    response = None
    for attempt in range(PAGE_ATTEMPTS):
        progress.check()
        try:
            response = requests.get(url, headers=get_random_headers(), timeout=REQUEST_TIMEOUT)
            break
        except requests.RequestException as exc:
            if attempt == PAGE_ATTEMPTS - 1:
                raise SiteUnavailable(type(exc).__name__) from exc
    if response.status_code != 200:
        raise SiteUnavailable(f"HTTP {response.status_code}")
    response.encoding = "utf-8"
    return response.text


def search_url(query: str, base: str) -> str:
    return f"{base.rstrip('/')}/index.php?do=search&subaction=search&story={quote(query)}"


def search(query: str, base: str) -> list[MovieSearchResult]:
    return parse_search(_get_page(search_url(query, base)), base)


def parse_search(html: str, base: str) -> list[MovieSearchResult]:
    content = BeautifulSoup(html, "html.parser").select_one("#dle-content")
    if content is None:
        raise SiteUnavailable("нет блока результатов")

    results: list[MovieSearchResult] = []
    for card in content.select(_SEARCH_CARD):
        link = card.select_one(_CARD_LINK)
        if link is None:
            continue
        title = re.sub(r"\s+", " ", link.get_text()).strip()
        image = card.select_one(_CARD_POSTER)
        poster = (image.get("data-src") or image.get("src")) if image else None
        year = re.search(r"\((\d{4})\)\s*$", title)
        results.append(MovieSearchResult(
            title=title,
            url=urljoin(base, link["href"]),
            poster_url=urljoin(base, poster) if poster and not poster.startswith("data:") else None,
            info=year[1] if year else "",
            source="kinogo",
        ))
    return results


def _description(article) -> str:
    block = article.select_one(".description__block")
    if block is not None:
        return re.sub(r"\s+", " ", block.get_text()).strip()
    for block in article.select("div, p"):
        if block.find_parent(class_="sInfo") or "sInfo" in (block.get("class") or []):
            continue
        if block.find(["div", "p", "iframe", "article", "h1", "h2"]):
            continue
        text = re.sub(r"\s+", " ", block.get_text()).strip()
        if len(text) >= 60:
            return text
    return ""


def _cast_names(article, section: str) -> list[str]:
    """Вёрстка с фотографиями: раздел человека виден по адресу его страницы."""
    images = article.select(f'a.cast-item[href*="/{section}/"] img[alt]')
    return [image["alt"].strip() for image in images if image["alt"].strip()]


def _actors(article) -> list[str]:
    from_photos = _cast_names(article, "actors")
    if from_photos:
        return from_photos[:MAX_ACTORS]
    for row in article.select(".castInfo span"):
        label = row.find("b")
        if label and label.get_text().strip().startswith("Акт"):
            names = (link.get_text(strip=True) for link in row.select("a"))
            return [name for name in names if name][:MAX_ACTORS]
    return []


def _related(soup, base: str) -> list[MovieSearchResult]:
    related: list[MovieSearchResult] = []
    for link in soup.select(_RELATED_LINK):
        text = re.sub(r"\s+", " ", link.get_text()).strip()
        title = link.get("title") or text
        if not title:
            continue
        image = link.select_one("img")
        poster = (image.get("data-src") or image.get("src")) if image else None
        year = re.search(r"\((\d{4})\)", title)
        related.append(MovieSearchResult(
            title=title,
            url=urljoin(base, link["href"]),
            poster_url=urljoin(base, poster) if poster and not poster.startswith("data:") else None,
            info=year[1] if year else "",
            source="kinogo",
        ))
    return related[:MAX_RELATED]


def parse_movie(html: str, url: str, base: str) -> MovieDetails:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article.fullStory") or soup.select_one("#dle-content article")
    if article is None:
        raise SiteUnavailable("нет страницы фильма")

    heading = article.find("h1")
    image = article.select_one(_MOVIE_POSTER)
    poster = (image.get("data-src") or image.get("src")) if image else None

    info: dict[str, str] = {}
    orig_title = None
    ratings = []
    for bold in article.select(_MOVIE_FACTS):
        key = bold.get_text().strip().rstrip(":")
        value = re.sub(r"\s+", " ", bold.parent.get_text()).replace(bold.get_text(), "", 1).strip()
        if not value:
            continue
        if key in _ORIG_TITLE_KEYS:
            orig_title = value
        elif key == "КиноПоиск":
            ratings.append(f"КиноПоиск: {value}")
        elif key == "IMDB":
            ratings.append(f"IMDb: {value}")
        elif key in _INFO_KEYS:
            info[_INFO_KEYS[key]] = value
    if ratings:
        info["Рейтинги"] = ", ".join(ratings)
    directors = _cast_names(article, "directors")
    if directors and "Режиссер" not in info:
        info["Режиссер"] = ", ".join(directors)

    return MovieDetails(
        title=re.sub(r"\s+", " ", heading.get_text()).strip() if heading else "Фильм",
        url=url,
        orig_title=orig_title,
        poster_url=urljoin(base, poster) if poster and not poster.startswith("data:") else None,
        description=_description(article),
        info_table=info,
        source="kinogo",
        referer=PLAYER_REFERER,
        actors=_actors(article),
        related=_related(soup, base),
    )


def voice_from_text(text: str) -> str | None:
    """Название озвучки из текста плеера: она идёт сразу за значением скорости."""
    match = re.search(r"Обычная\s+(.{1,60}?)(?:\s+Реклама\b|\s*$)", re.sub(r"\s+", " ", text))
    return match[1].strip() if match else None


# Списки плеера: у сериала сезоны, серии и озвучки, у фильма только озвучки. Перед каждым списком
# кнопка с текущим значением. Роль списка определяется в classify_groups по его содержимому.
_READ_GROUPS = """
const player = document.getElementById('player');
if (!player) return [];
const groups = new Map();
for (const button of player.querySelectorAll('button')) {
  const text = button.textContent.trim();
  const toggle = button.parentElement.previousElementSibling;
  if (!text || !toggle || toggle.tagName !== 'BUTTON') continue;
  if (!groups.has(button.parentElement)) groups.set(button.parentElement, {current: toggle.textContent.trim(), items: []});
  groups.get(button.parentElement).items.push(text);
}
return [...groups.values()];
"""

_CLICK_ITEM = """
const name = arguments[0];
performance.clearResourceTimings();
for (const button of document.getElementById('player').querySelectorAll('button')) {
  const toggle = button.parentElement.previousElementSibling;
  if (button.textContent.trim() === name && toggle && toggle.tagName === 'BUTTON') {
    for (const type of ['mousedown', 'mouseup', 'click']) {
      button.dispatchEvent(new MouseEvent(type, {bubbles: true}));
    }
    return true;
  }
}
return false;
"""

_SEASON_NAME = re.compile(r"^Сезон\s*\d", re.I)
_EPISODE_NAME = re.compile(r"^Серия\s*\d", re.I)


class PlayerLists(NamedTuple):
    seasons: dict | None
    episodes: dict | None
    voices: dict | None


def classify_groups(groups: list[dict]) -> PlayerLists:
    """Роль списка по кнопкам: порядок и число списков у сериала без сезонов другие."""
    # Одна кнопка считается списком, только если она совпадает с текущим значением: это отсекает чужие кнопки.
    usable = [g for g in groups if len(g.get("items") or []) >= 2 or g.get("current") in (g.get("items") or [])]

    def first(pattern):
        return next((g for g in usable if any(pattern.match(item) for item in g["items"])), None)

    seasons, episodes = first(_SEASON_NAME), first(_EPISODE_NAME)
    voices = next((g for g in usable if g is not seasons and g is not episodes), None)
    return PlayerLists(seasons, episodes, voices)


def _item_id(name: str) -> str:
    """Плеер переключается по названию, а номер нужен, чтобы найти ближайшую серию."""
    match = re.search(r"\d+", name)
    return match[0] if match else name


def series_from_lists(lists: PlayerLists) -> SeriesInfo | None:
    if lists.episodes is None:
        return None
    current_season = lists.seasons["current"] if lists.seasons else "Сезон 1"
    episodes = [Episode(_item_id(name), name) for name in voices_from_list(lists.episodes["items"])]
    season_names = voices_from_list(lists.seasons["items"]) if lists.seasons else [current_season]
    return SeriesInfo(
        seasons=[
            Season(_item_id(name), name, episodes if name == current_season else [])
            for name in season_names
        ],
        season=_item_id(current_season),
        episode=_item_id(lists.episodes["current"]),
    )


def voices_from_list(names: list[str]) -> list[str]:
    """Список без пропусков и повторов; у первой кнопки может быть то же имя, что и у текущей."""
    return list(dict.fromkeys(name for name in names if name))


def _read_lists(driver) -> PlayerLists:
    return classify_groups(driver.execute_script(_READ_GROUPS) or [])


@dataclass
class Captured:
    master: str
    current: str | None
    voices: list[str]
    series: SeriesInfo | None = None


def _wait_for_master(driver, deadline_seconds: float, progress: Progress = NO_PROGRESS) -> str | None:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        progress.check()
        time.sleep(POLL_SECONDS)
        for name in driver.execute_script("return performance.getEntriesByType('resource').map(r=>r.name)"):
            parsed = urlparse(name)
            if STREAM_HOST_MARK in parsed.netloc and re.search(r"/hls[^/]*\.m3u8$", parsed.path):
                return name
    return None


def _player_frame(driver):
    for frame in driver.find_elements(By.TAG_NAME, "iframe"):
        if PLAYER_HOST_MARK in (frame.get_attribute("src") or ""):
            return frame
    return None


def _close_popups(driver, main_window: str) -> None:
    for handle in driver.window_handles:
        if handle != main_window:
            driver.switch_to.window(handle)
            driver.close()
    driver.switch_to.window(main_window)


def capture_stream(
    driver,
    url: str,
    voice: str | None = None,
    strict: bool = True,
    progress: Progress = NO_PROGRESS,
    get_driver=None,
    season: str | None = None,
    episode: str | None = None,
) -> Captured:
    """Открыть плеер и вернуть поток, озвучки и серии, не показывая рекламу.

    Если задана ``voice``, плеер переключается на неё, как при выборе зрителем. При ``strict=False``
    (сохранённая в настройках озвучка) неудача не считается ошибкой: остаётся озвучка по умолчанию.
    ``season`` без ``episode`` означает первую серию сезона.
    """
    main_window = None
    try:
        with progress.step("player", browser=True):
            # Запуск Chrome занимает секунды, поэтому он тоже входит в видимый шаг.
            if driver is None:
                driver = get_driver()
            main_window = driver.current_window_handle
            driver.get(url)
            # Плеер подгружается при прокрутке. Скрипт зеркала снимает класс lazy раньше, чем задаёт адрес,
            # поэтому ни по классу, ни по адресу его найти нельзя, только по контейнеру.
            frames = driver.find_elements(By.CSS_SELECTOR, _PLAYER_FRAME)
            if not frames:
                raise NoVideo("нет плеера на странице")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'})", frames[0])

            frame = None
            deadline = time.monotonic() + FRAME_WAIT_SECONDS
            while frame is None and time.monotonic() < deadline:
                progress.check()
                time.sleep(POLL_SECONDS)
                frame = _player_frame(driver)
            if frame is None:
                raise NoVideo("плеер другого типа")

            driver.switch_to.frame(frame)
            ActionChains(driver).move_to_element(driver.find_element(By.TAG_NAME, "body")).click().perform()

        with progress.step("stream", browser=True):
            master = _wait_for_master(driver, STREAM_WAIT_SECONDS, progress)
            if master is None:
                raise NoVideo("плеер не выдал поток")

        return _select(driver, master, voice, strict, season, episode, progress)
    finally:
        # Ошибка уборки не должна подменять причину сбоя выше.
        try:
            if main_window is not None:  # иначе Chrome не запустился и убирать нечего
                driver.switch_to.default_content()
                _close_popups(driver, main_window)
                driver.get("about:blank")  # останавливает плеер вместе с рекламой
        except Exception as exc:
            _log(f"не удалось остановить плеер: {type(exc).__name__}")


def _switch(driver, name: str, progress: Progress) -> str | None:
    """Нажать кнопку списка и дождаться нового потока."""
    if not driver.execute_script(_CLICK_ITEM, name):
        return None
    master = _wait_for_master(driver, VOICE_SWITCH_WAIT_SECONDS, progress)
    if master is None:
        return None
    # Подпись кнопки может обновиться позже, чем придёт поток.
    deadline = time.monotonic() + LIST_UPDATE_SECONDS
    while time.monotonic() < deadline:
        if any(group.get("current") == name for group in driver.execute_script(_READ_GROUPS) or []):
            break
        progress.check()
        time.sleep(POLL_SECONDS)
    return master


def _go_to(driver, master: str, group: dict | None, item: str | None, what: str, progress: Progress) -> str:
    """Выбрать в списке значение с этим номером, если оно есть и ещё не выбрано."""
    names = {_item_id(name): name for name in (group["items"] if group else [])}
    if item not in names or names[item] == group["current"]:
        return master
    with progress.step("episode", browser=True):
        switched = _switch(driver, names[item], progress)
        if switched is None:
            raise NoVideo(f"плеер не переключил {what}")
    return switched


def _select(driver, master: str, voice: str | None, strict: bool, season: str | None, episode: str | None, progress: Progress) -> Captured:
    """Переключить плеер. Набор озвучек зависит от сезона, а набор сезонов от озвучки, поэтому
    сезон выбирается и до озвучки, и после неё. Смена сезона сбрасывает серию, поэтому она последняя."""
    master = _go_to(driver, master, _read_lists(driver).seasons, season, "сезон", progress)

    lists = _read_lists(driver)
    voices = voices_from_list(lists.voices["items"]) if lists.voices else []
    current = lists.voices["current"] if lists.voices else None
    if current is None and lists.episodes is None:
        current = voice_from_text(driver.execute_script("return document.body.innerText"))
        voices = voices or ([current] if current else [])

    if voice and voice != current and (strict or voice in voices):
        with progress.step("voice", browser=True):
            switched = _switch(driver, voice, progress)
        if switched is not None:
            master, current = switched, voice
        elif strict:
            raise NoVideo("плеер не переключил озвучку")
        else:
            _log("сохранённая озвучка не включилась, остаётся озвучка по умолчанию")

    lists = _read_lists(driver)
    moved = False
    if season is not None and lists.seasons is not None:
        ids = [_item_id(name) for name in lists.seasons["items"]]
        target = nearest_id(ids, season)
        if target != season:
            # Нужного сезона в этой озвучке нет: ближайший и его первая серия.
            moved, episode = True, None
        master = _go_to(driver, master, lists.seasons, target, "сезон", progress)
        lists = _read_lists(driver)

    if lists.episodes is not None and (season is not None or episode is not None):
        ids = [_item_id(name) for name in lists.episodes["items"]]
        target = nearest_id(ids, episode)
        moved = moved or (episode is not None and target != episode)
        master = _go_to(driver, master, lists.episodes, target, "серию", progress)
        lists = _read_lists(driver)

    series = series_from_lists(lists)
    if series is not None:
        series.moved = moved
    if lists.voices:
        voices = voices_from_list(lists.voices["items"])
        current = lists.voices["current"]
    return Captured(master, current, voices, series)


def is_player_server(url: str) -> bool:
    """Сервер плеера: под именем 1080 там может быть качество ниже заявленного."""
    host = urlparse(url).netloc
    return host.endswith(".cinemap.cc") and not host.endswith(".host.cinemap.cc")


def label_for_width(width: int) -> str:
    for minimum, label in _LABEL_BY_MIN_WIDTH:
        if width >= minimum:
            return label
    return "240p"


def _on_host(url: str, name: str, host: str, signed: bool) -> str:
    """Адрес файла ``name`` рядом с ``url``; без подписи, если сервер не тот, что выдал ссылку."""
    parsed = urlparse(url)
    # Первый сегмент — подпись сервера плеера; за ней /movies/ у фильмов и /tvseries/ у сериалов.
    path = parsed.path if signed else "/" + parsed.path.split("/", 2)[2]
    return f"https://{host}{path.rsplit('/', 1)[0]}/{name}"


def _try_playlist(url: str, connect_timeout: float = STREAM_REQUEST_TIMEOUT) -> tuple[requests.Response | None, bool]:
    """Ответ и признак, есть ли смысл повторять. Узел, к которому не подключиться, повтор не спасёт."""
    try:
        response = requests.get(
            url,
            headers={**get_random_headers(), "Referer": PLAYER_REFERER},
            timeout=(connect_timeout, STREAM_REQUEST_TIMEOUT),
        )
    except requests.ConnectTimeout:  # узел молчит: повтор стоил бы ещё столько же
        return None, False
    except requests.RequestException:  # обрыв, отказ, ReadTimeout: быстрые разовые сбои
        return None, True
    if response.ok and response.text.startswith("#EXTM3U"):
        return response, False
    return None, True


def _fetch_playlist(url: str) -> requests.Response | None:
    """Мастер-плейлист и запасной вариант: единственная попытка, поэтому без короткого таймаута."""
    return _try_playlist(url)[0]


def _fetch_with_retries(url: str) -> requests.Response | None:
    """Повтор от разовых сбоев. Постоянно недоступный узел файла он не вылечит."""
    for _ in range(ATLAS_ATTEMPTS):
        # Короткое ожидание соединения: мёртвый узел варианта не должен держать весь шаг.
        response, retry = _try_playlist(url, ATLAS_CONNECT_TIMEOUT)
        if response is not None or not retry:
            return response
    return None


def _parse_variants(master: str) -> list[tuple[int, str]]:
    lines = master.splitlines()
    variants = []
    for index, line in enumerate(lines[:-1]):
        match = re.search(r"RESOLUTION=(\d+)x\d+", line)
        if match:
            variants.append((int(match[1]), lines[index + 1].strip().removeprefix("./")))
    return sorted(variants)


def _playlist_seconds(text: str) -> float:
    return sum(float(value) for value in re.findall(r"#EXTINF:([\d.]+)", text))


def _fetch_all(urls: list[str], progress: Progress) -> list[requests.Response | None]:
    """Параллельные запросы, которые не задерживают отмену."""
    pool = ThreadPoolExecutor(max_workers=len(urls))
    try:
        futures = [pool.submit(_fetch_with_retries, url) for url in urls]
        while not all(future.done() for future in futures):
            progress.check()
            time.sleep(0.1)
        return [future.result() for future in futures]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def build_streams(signed_master: str, progress: Progress = NO_PROGRESS, is_series: bool = False) -> dict[str, list[str]]:
    """Варианты качества: проверенный узел, затем ``atlas``, затем сервер плеера.

    Минимальная длина отсекает трейлер вместо фильма; у сериала серия может быть короткой.
    """
    min_seconds = 0 if is_series else MIN_MOVIE_SECONDS
    master = _fetch_playlist(signed_master)
    if master is None:
        raise NoVideo("мастер-плейлист недоступен")
    variants = _parse_variants(master.text)
    if not variants:
        raise NoVideo("нет вариантов качества")

    host = urlparse(signed_master).netloc
    atlas_urls = [_on_host(signed_master, name, ATLAS_HOST, signed=False) for _, name in variants]
    checked = _fetch_all(atlas_urls, progress)

    available = [(v, url, r) for v, url, r in zip(variants, atlas_urls, checked) if r is not None]
    if not available:
        _log(f"сервер {ATLAS_HOST} недоступен, используется сервер плеера")
        fallback = _fetch_playlist(_on_host(signed_master, variants[-1][1], host, signed=True))
        if fallback is None or _playlist_seconds(fallback.text) < min_seconds:
            raise NoVideo("поток не похож на фильм")
        return {UNCONFIRMED: [signed_master]}
    if _playlist_seconds(available[-1][2].text) < min_seconds:
        raise NoVideo("поток не похож на фильм")
    if len(available) < len(variants):
        lost = [label_for_width(v[0]) for v, r in zip(variants, checked) if r is None]
        _log(f"узлы недоступны для вариантов {lost}")

    # Вариант с недоступным узлом не показывается: на сервере плеера под его именем другое качество.
    streams: dict[str, list[str]] = {}
    for (width, name), atlas_url, response in available:
        urls = [response.url, atlas_url, _on_host(signed_master, name, host, signed=True)]
        streams[label_for_width(width)] = list(dict.fromkeys(urls))
    # Узлы некоторых серий не отвечают постоянно: без этого варианта осталось бы только низкое качество.
    if is_series and checked[-1] is None:
        streams[UNCONFIRMED] = [signed_master]
    return streams


def _has_player(html: str) -> bool:
    frame = BeautifulSoup(html, "html.parser").select_one(_PLAYER_FRAME)
    return frame is not None and PLAYER_HOST_MARK in (frame.get("data-src") or frame.get("src") or "")


def _optional_capture(html, url, voice, strict, season, episode, progress) -> Captured | None:
    """Необязательный модуль загрузки; без него и при любом его сбое работает путь через Chrome."""
    try:
        from . import fastload
    except ImportError:
        return None
    try:
        return fastload.capture(html, url, voice, strict, season, episode, progress)
    except Cancelled:
        raise
    except Exception as exc:
        _log(f"необязательный модуль не сработал: {type(exc).__name__}")
        return None


def fetch_movie(
    url: str,
    driver,
    base: str,
    voice: str | None = None,
    strict: bool = True,
    progress: Progress = NO_PROGRESS,
    get_driver=None,
    season: str | None = None,
    episode: str | None = None,
) -> MovieDetails:
    """Страница фильма с потоками. При отсутствии видео NoVideo.details содержит описание фильма."""
    with progress.step("page"):
        html = _get_page(url, progress)
        # Карточка могла прийти с другого зеркала: относительные адреса считаются от её сайта.
        site = urlparse(url)
        details = parse_movie(html, url, f"{site.scheme}://{site.netloc}" if site.netloc else base)
    try:
        if not _has_player(html):
            raise NoVideo("на странице нет плеера фильма")
        captured = _optional_capture(html, url, voice, strict, season, episode, progress)
        if captured is None:
            captured = capture_stream(driver, url, voice, strict, progress=progress, get_driver=get_driver, season=season, episode=episode)
        with progress.step("quality"):
            details.streams = build_streams(captured.master, progress, captured.series is not None)
    except Cancelled:
        raise
    except NoVideo as exc:
        exc.details = details
        raise
    except Exception as exc:
        # Изменения сайта и плеера не должны мешать переходу на запасной источник.
        _log(f"сбой получения потока: {type(exc).__name__}")
        failure = NoVideo(type(exc).__name__)
        failure.details = details
        raise failure from exc
    # Идентификатор озвучки — её название: плеер переключается только по нему.
    details.translators = [Translator(id=name, name=name, active=name == captured.current) for name in captured.voices]
    details.active_translator_id = captured.current
    details.series = captured.series
    _log(f"поток получен: {urlparse(captured.master).netloc}, вариантов {len(details.streams)}")
    return details
