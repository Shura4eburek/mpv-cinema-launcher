# Implementation Plan: Поддержка сериалов

**Branch**: `008-series-support` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-series-support/spec.md`

## Summary

Страница сериала получает выбор сезона и серии на KinoGo и HDRezka. Backend возвращает сезоны и серии вместе со страницей, а новый метод `episode` отдаёт потоки выбранной пары «серия + озвучка». KinoGo управляет плеером кликами, HDRezka использует запросы `get_episodes` и `get_stream`. Если KinoGo не дал видео, а на HDRezka одно точное совпадение, страница открывается оттуда сразу.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.9, Svelte 5

**Primary Dependencies**: selenium, requests, BeautifulSoup; новых нет

**Storage**: кеш страниц в памяти; настройки не меняются

**Testing**: pytest, Vitest, `npm run check`; ручная проверка на живых сайтах по [quickstart.md](quickstart.md)

**Target Platform**: Windows x64, macOS (как у приложения)

**Project Type**: настольное приложение (Tauri + Python backend)

**Performance Goals**: смена серии за 10 с на HDRezka и за 30 с на KinoGo. Замеры: запрос HDRezka 0,1 с; плеер KinoGo открывается за 1,5 с, клик даёт новый поток за 0,4 с.

**Constraints**: операции браузера идут по одной через очередь Selenium; данные сайтов недоверенные, без `{@html}`; поведение фильмов не меняется, кроме автооткрытия

**Scale/Scope**: правки в `kinogo.py`, `scraper.py`, `sources.py`, `backend.py`, `Movie.svelte`, `api.ts`, `logic.ts`; новых модулей нет

## Constitution Check

`.specify/memory/constitution.md` не заполнен (шаблон), проверок нет. После дизайна без изменений.

## Project Structure

### Documentation (this feature)

```text
specs/008-series-support/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/backend-protocol.md
└── tasks.md             # создаёт /speckit-tasks
```

### Source Code (repository root)

```text
src/mpv_launcher/
├── scraper.py     # Season, Episode, SeriesInfo, nearest_episode; разбор сериала; get_episodes, get_stream; рекомендации
├── kinogo.py      # чтение групп плеера, клики, путь /tvseries/, порог длительности; рекомендации
├── sources.py     # очистка названия, однозначное совпадение, автооткрытие HDRezka
└── backend.py     # метод episode, кеш, обновление ссылок, _forget_page

app/src/
├── screens/Movie.svelte   # списки сезона и серии, отмена, заголовок, сообщения
└── lib/api.ts, logic.ts   # типы, api.episode, episodeTitle, шаги

tests/unit/        # test_kinogo, test_scraper_and_launcher, test_sources, test_backend
```

**Structure Decision**: Сезоны и серии живут рядом с `MovieDetails` в `scraper.py`, потому что `kinogo.py` уже импортирует оттуда общие типы.

## Этапы

1. **HDRezka (US1, US2)**: разбор сериала, метод `episode`, интерфейс. Сразу даёт рабочие сериалы и снимает ошибку озвучки.
2. **KinoGo (US3)**: `/tvseries/`, группы плеера, клики, порог длительности.
3. **Обновление ссылок и кеш**: ключи с сезоном и серией (FR-009, FR-010).
4. **Автооткрытие HDRezka (FR-007a, FR-007b)**.
5. **Рекомендации (US4)** и обновление `AI_DEVELOPER_GUIDE.md` и протокола.

## Риски

- Часть узлов `atlas` не отвечает постоянно, поэтому часть серий будет с подписью «Качество не подтверждено» (см. [research.md](research.md)).
- Сериал без сезонов в плеере KinoGo на живом примере не проверен: разбор обрабатывает отсутствие группы сезонов, подтверждение — в quickstart.
