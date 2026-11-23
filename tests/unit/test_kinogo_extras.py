from unittest import mock

from bs4 import BeautifulSoup

from mpv_launcher import kinogo, scraper

BASE = "https://uakinogo.io"

KINOGO_PAGE = """
<article class="fullStory"><h1>Довод (2020)</h1>
<div class="castInfo">
<span><b>Режисер:</b>Кристофер Нолан</span>
<span><b>Актори:</b><a href="/a">Джон Дэвид Вашингтон</a>, <a href="/b">Роберт Паттинсон</a></span>
</div></article>
<div class="viewMore-wrap">
<div class="relatedItem"><a href="https://uakinogo.io/filmy/1-a.html" title="Фильм А (2007)">
<img class="lazy" data-src="/uploads/a.webp" src="data:image/gif;base64,R0"/><span>Фильм А (2007)</span></a></div>
<div class="relatedItem"><a href="https://uakinogo.io/serialy/2-b.html" title="Проект (1-2 сезон)">
<img data-src="/uploads/b.webp"/><span>Проект (1-2 сезон)</span></a></div>
<div class="relatedItem"><a href="/multfilmy/3-c.html" title="Без постера"><span>Без постера</span></a></div>
</div>
"""

REZKA_PAGE = """
<table class="b-post__info">
<tr><td><div class="persons-list-holder"><span itemprop="director"><span itemprop="name">Кристофер Нолан</span></span></div></td></tr>
<tr><td><div class="persons-list-holder">
<span itemprop="actor"><a><span itemprop="name">Джон Дэвид Вашингтон</span></a></span>
<span itemprop="actor"><a><span itemprop="name">Роберт Паттинсон</span></a></span>
</div></td></tr>
</table>
<div class="b-sidelist">
<div class="b-content__inline_item"><div class="b-content__inline_item-cover"><img src="https://static/a.jpg"/></div>
<div class="b-content__inline_item-link"><a href="https://rezka-ag.net/films/action/1-a-2008.html">Каменный дождь</a><div>2008, США, Боевики</div></div></div>
<div class="b-content__inline_item"><div class="b-content__inline_item-link"><a href="https://rezka-ag.net/series/drama/2-b.html">Сериал</a><div>2010</div></div></div>
</div>
<div class="b-content__inline_item"><div class="b-content__inline_item-link"><a href="https://rezka-ag.net/films/x.html">Не из блока</a></div></div>
"""


TV_BASE = "https://uakinogo.tv"

TV_SEARCH = """
<div id="dle-content"><div class="js-lightsearch-form"></div>
<div class="shortstory" id="2065"><div class="shortstory__header"><div class="shortstory__title">
<a href="https://uakinogo.tv/2065--dovod-2020.html"><h2>Довод (2020)</h2></a></div></div>
<div class="shortstory__body"><div class="shortstory__poster"><a href="https://uakinogo.tv/2065--dovod-2020.html">
<img class="lazy" data-src="/uploads/d.webp" src="data:image/gif;base64,R0"/></a></div></div></div></div>
"""

TV_MOVIE = """
<div id="dle-content"><article>
<div class="fullstory__title"><h1>Довод (2020)</h1></div>
<div class="movie__info"><div class="movie_poster"><img src="/uploads/m.webp"/></div>
<div class="d-flex"><b>Вышел в:</b>2020</div>
<div class="d-flex country"><b>Сняли в:</b>США, Великобритания</div>
<div class="nd-flex"><b>Жанры:</b>Фильмы / Боевик</div></div>
<div class="cast-block">
<a class="cast-item" href="https://uakinogo.tv/actors/588-v.html"><div class="cast-poster"><img alt="Джон Дэвид Вашингтон"/></div></a>
<a class="cast-item" href="https://uakinogo.tv/directors/597-n.html"><div class="cast-poster"><img alt="Кристофер Нолан"/></div></a>
</div>
<div class="description__block"><div>События начинаются в Киеве.</div></div>
<div class="section"><div class="video-container kg-video-container"><iframe class="lazy" data-src="https://cinemar.cc/embed/1"></iframe></div></div>
<div class="related-items">
<a class="related-item" href="https://uakinogo.tv/1-film.html" title="Фильм"><img class="lazy" data-src="/uploads/r.webp"/><div class="rel related-name">Фильм</div></a>
<a class="related-item" href="https://uakinogo.tv/2-serial.html" title="Последний довод"><div class="related-serie">1 сезон</div></a>
</div>
</article></div>
"""


def test_tv_layout_search_cards():
    with mock.patch.object(kinogo, "_get_page", return_value=TV_SEARCH):
        cards = kinogo.search("Довод", TV_BASE)
    assert [(c.title, c.url, c.info) for c in cards] == [("Довод (2020)", f"{TV_BASE}/2065--dovod-2020.html", "2020")]
    assert cards[0].poster_url == f"{TV_BASE}/uploads/d.webp"


def test_tv_layout_movie_page():
    details = kinogo.parse_movie(TV_MOVIE, f"{TV_BASE}/2065.html", TV_BASE)
    assert details.title == "Довод (2020)"
    assert details.poster_url == f"{TV_BASE}/uploads/m.webp"
    assert details.description == "События начинаются в Киеве."
    assert details.info_table == {"Год": "2020", "Страна": "США, Великобритания", "Жанр": "Фильмы / Боевик", "Режиссер": "Кристофер Нолан"}
    assert details.actors == ["Джон Дэвид Вашингтон"]
    assert [r.title for r in details.related] == ["Фильм", "Последний довод"]
    assert details.related[0].poster_url == f"{TV_BASE}/uploads/r.webp"
    assert kinogo._has_player(TV_MOVIE)


def test_kinogo_actors_skip_director():
    details = kinogo.parse_movie(KINOGO_PAGE, f"{BASE}/filmy/28.html", BASE)
    assert details.actors == ["Джон Дэвид Вашингтон", "Роберт Паттинсон"]


def test_kinogo_related_keeps_series_and_drops_lazy_placeholder():
    related = kinogo.parse_movie(KINOGO_PAGE, f"{BASE}/filmy/28.html", BASE).related
    assert [r.title for r in related] == ["Фильм А (2007)", "Проект (1-2 сезон)", "Без постера"]
    assert related[0].poster_url == f"{BASE}/uploads/a.webp"
    assert related[0].info == "2007"
    assert related[0].source == "kinogo"
    assert related[1].url == f"{BASE}/serialy/2-b.html"
    assert related[2].url == f"{BASE}/multfilmy/3-c.html"
    assert related[2].poster_url is None


def test_kinogo_film_with_season_in_title_stays():
    page = '<article class="fullStory"></article><div class="relatedItem"><a href="/filmy/1.html"><span>Сезон охоты (2006)</span></a></div>'
    assert [r.title for r in kinogo.parse_movie(page, f"{BASE}/x.html", BASE).related] == ["Сезон охоты (2006)"]


def test_rezka_related_keeps_animation_and_series():
    page = """<div class="b-sidelist">
    <div class="b-content__inline_item"><div class="b-content__inline_item-link"><a href="https://r/animation/1.html">Аниме</a><div>2010</div></div></div>
    <div class="b-content__inline_item"><div class="b-content__inline_item-link"><a href="https://r/cartoons/2.html">Мультсериал</a><div>2008 - 2012, США</div></div></div>
    <div class="b-content__inline_item"><div class="b-content__inline_item-link"><a href="https://r/cartoons/3.html">Мультфильм</a><div>2008, США</div></div></div>
    </div>"""
    related = scraper.parse_related(BeautifulSoup(page, "html.parser"), "https://rezka-ua.pub/films/1.html")
    assert [r.title for r in related] == ["Аниме", "Мультсериал", "Мультфильм"]


def test_kinogo_page_without_extras():
    details = kinogo.parse_movie('<article class="fullStory"><h1>Т</h1></article>', f"{BASE}/x.html", BASE)
    assert details.actors == []
    assert details.related == []


def test_kinogo_limits():
    actors = "".join(f"<a>Актёр {i}</a>" for i in range(20))
    items = "".join(f'<div class="relatedItem"><a href="/filmy/{i}.html"><span>Ф {i}</span></a></div>' for i in range(20))
    page = f'<article class="fullStory"><div class="castInfo"><span><b>Актори:</b>{actors}</span></div></article>{items}'
    details = kinogo.parse_movie(page, f"{BASE}/x.html", BASE)
    assert len(details.actors) == 12
    assert len(details.related) == 8


def test_rezka_actors_only():
    soup = BeautifulSoup(REZKA_PAGE, "html.parser")
    assert scraper.parse_actors(soup) == ["Джон Дэвид Вашингтон", "Роберт Паттинсон"]


def test_rezka_related_uses_page_host_and_keeps_series():
    soup = BeautifulSoup(REZKA_PAGE, "html.parser")
    related = scraper.parse_related(soup, "https://rezka-ua.pub/films/fiction/34878-dovod-2020.html")
    assert [r.title for r in related] == ["Каменный дождь", "Сериал"]
    assert related[0].url == "https://rezka-ua.pub/films/action/1-a-2008.html"
    assert related[0].poster_url == "https://static/a.jpg"
    assert related[0].info == "2008, США, Боевики"
    assert related[0].source == "hdrezka"
