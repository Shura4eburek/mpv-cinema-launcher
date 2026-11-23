"""Проверка зеркал для экрана диагностики: один поисковый запрос к каждому адресу, без браузера."""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import kinogo, scraper

_TIMEOUT_SECONDS = 10


def _base_report(site: str, base: str) -> dict:
    return {
        "site": site,
        "url": base,
        "state": "checking",
        "http": None,
        "ms": None,
        "final_host": None,
        "server": None,
        "count": 0,
        "matches": 0,
        "first": None,
        "first_url": None,
        "detail": "",
    }


def _kinogo_cards(html: str, base: str) -> list[tuple[str, str]] | None:
    try:
        return [(card.title, card.url) for card in kinogo.parse_search(html, base)]
    except scraper.SiteUnavailable:
        return None


def _hdrezka_cards(html: str, base: str) -> list[tuple[str, str]]:
    links = BeautifulSoup(html, "html.parser").select(".b-content__inline_item .b-content__inline_item-link a[href]")
    return [(link.get_text(strip=True), link["href"]) for link in links]


def _blocked_reason(response: requests.Response) -> str | None:
    text = response.text[:20000].lower()
    if "cf-mitigated" in response.headers or "just a moment" in text:
        return "Проверка Cloudflare: обычным запросам приложения сайт не отвечает"
    if "anubis" in text:
        return "Проверка Anubis: приложение открывает такой сайт через браузер, здесь браузер не запускается"
    if "loginform" in text:
        return "Сайт требует вход"
    return None


def check(site: str, base: str, query: str) -> dict:
    report = _base_report(site, base)
    url = kinogo.search_url(query, base) if site == "kinogo" else f"{base}/search/?do=search&subaction=search&q={requests.utils.quote(query)}"
    started = time.monotonic()
    try:
        response = requests.get(url, headers=scraper.get_random_headers(), timeout=_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        report.update(state="down", ms=round((time.monotonic() - started) * 1000), detail=f"Нет соединения: {type(exc).__name__}")
        return report

    response.encoding = "utf-8"
    final_host = urlparse(response.url).netloc
    report.update(
        http=response.status_code,
        ms=round((time.monotonic() - started) * 1000),
        final_host=final_host,
        server=response.headers.get("server"),
    )
    notes = [f"Перенаправляет на {final_host}"] if final_host != urlparse(base).netloc else []

    blocked = _blocked_reason(response)
    if blocked:
        report.update(state="blocked", detail=" ".join([blocked, *notes]))
        return report
    if response.status_code != 200:
        report.update(state="error", detail=" ".join([f"Сайт ответил ошибкой HTTP {response.status_code}", *notes]))
        return report

    cards = _kinogo_cards(response.text, base) if site == "kinogo" else _hdrezka_cards(response.text, base)
    if cards is None:
        report.update(state="empty", detail=" ".join(["Нет блока результатов: другая вёрстка или заглушка", *notes]))
        return report
    wanted = query.lower()
    report.update(count=len(cards), matches=sum(wanted in title.lower() for title, _ in cards))
    if cards:
        report.update(state="ok", first=cards[0][0], first_url=cards[0][1], detail=" ".join(notes))
    else:
        report.update(state="empty", detail=" ".join(["Страница открылась, но карточек нет", *notes]))
    return report


def mirrors(kinogo_base: str) -> list[tuple[str, str]]:
    addresses = dict.fromkeys(base.rstrip("/") for base in [kinogo_base, *kinogo.DEFAULT_MIRRORS])
    return [("kinogo", base) for base in addresses] + [("hdrezka", base) for base in scraper.DEFAULT_MIRRORS]


def pending(site: str, base: str) -> dict:
    return _base_report(site, base)
