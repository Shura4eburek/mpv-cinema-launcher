from unittest import mock

import pytest
import requests

from mpv_launcher import kinogo, mirror_check, scraper

BASE = "https://k.test"
KINOGO_PAGE = """<div id="dle-content"><article class="shortStory"><h2><a href="/1.html">Довод (2020)</a></h2></article>
<article class="shortStory"><h2><a href="/2.html">Другое</a></h2></article></div>"""


def _response(text="", status=200, headers=None, url=f"{BASE}/search"):
    response = mock.Mock(status_code=status, text=text, headers=headers or {"server": "nginx"}, url=url)
    return response


def _check(response, site="kinogo", base=BASE, query="Довод"):
    with mock.patch.object(mirror_check.requests, "get", return_value=response):
        return mirror_check.check(site, base, query)


def test_working_kinogo_mirror():
    report = _check(_response(KINOGO_PAGE))
    assert report["state"] == "ok"
    assert (report["count"], report["matches"]) == (2, 1)
    assert report["first"] == "Довод (2020)"
    assert report["first_url"] == f"{BASE}/1.html"
    assert (report["http"], report["server"], report["final_host"]) == (200, "nginx", "k.test")


def test_cloudflare_check_is_named():
    report = _check(_response("<title>Just a moment...</title>", 403, {"server": "cloudflare", "cf-mitigated": "challenge"}))
    assert report["state"] == "blocked"
    assert "Cloudflare" in report["detail"]


def test_other_layout_is_empty_with_reason():
    report = _check(_response("<html>заглушка</html>"))
    assert report["state"] == "empty"
    assert "другая вёрстка" in report["detail"]


def test_page_without_cards():
    report = _check(_response('<div id="dle-content"></div>'))
    assert report["state"] == "empty"
    assert "карточек нет" in report["detail"]


def test_http_error():
    report = _check(_response("oops", 500))
    assert report["state"] == "error"
    assert "500" in report["detail"]


def test_network_failure():
    with mock.patch.object(mirror_check.requests, "get", side_effect=requests.ConnectTimeout()):
        report = mirror_check.check("kinogo", BASE, "Довод")
    assert report["state"] == "down"
    assert "ConnectTimeout" in report["detail"]
    assert report["http"] is None


def test_redirect_is_reported():
    report = _check(_response(KINOGO_PAGE, url="https://other.test/search"))
    assert "other.test" in report["detail"]


@pytest.mark.parametrize(("text", "word"), [("<p>Anubis check</p>", "Anubis"), ('<form id="loginform">', "вход")])
def test_hdrezka_blocks(text, word):
    report = _check(_response(text), site="hdrezka")
    assert report["state"] == "blocked"
    assert word in report["detail"]


def test_hdrezka_cards():
    page = '<div class="b-content__inline_item"><div class="b-content__inline_item-link"><a href="https://r/1.html">Довод</a></div></div>'
    report = _check(_response(page), site="hdrezka")
    assert (report["state"], report["count"], report["first"]) == ("ok", 1, "Довод")


def test_mirror_list_has_setting_first_without_duplicates():
    with mock.patch.object(kinogo, "DEFAULT_MIRRORS", ["https://a.test", "https://b.test"]), \
        mock.patch.object(scraper, "DEFAULT_MIRRORS", ["https://r.test"]):
        assert mirror_check.mirrors("https://b.test") == [
            ("kinogo", "https://b.test"),
            ("kinogo", "https://a.test"),
            ("hdrezka", "https://r.test"),
        ]
