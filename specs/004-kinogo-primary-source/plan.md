# Implementation Plan: KinoGo как основной источник фильмов

**Branch**: `004-kinogo-primary-source` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-kinogo-primary-source/spec.md`

## Summary

Новый модуль `kinogo.py` ищет фильмы обычными запросами, а ссылку на поток получает из плеера в Chrome за несколько секунд, не показывая рекламу. Качество берётся с сервера `atlas`, где разрешение настоящее; сервер плеера `cfnd` остаётся запасным. Модуль `sources.py` задаёт порядок KinoGo → HDRezka для приложения и CLI.

## Technical Context

**Language/Version**: Python 3.10+, TypeScript 5.9, Svelte 5

**Primary Dependencies**: requests, BeautifulSoup, Selenium, mpv; новых зависимостей нет

**Storage**: новое поле `kinogo_url` в настройках

**Testing**: pytest и Vitest; реальные сайты и разрешение проверяются вручную по [quickstart.md](./quickstart.md)

**Target Platform**: Windows 11 (основная), macOS без регрессий

**Project Type**: desktop-app

**Performance Goals**: ссылка на поток за ~5 секунд; переход на запасной вариант до 30 секунд (SC-003)

**Constraints**: без маскировки браузера; `ffprobe` не входит в приложение и не используется в коде; реклама не показывается и не звучит

**Scale/Scope**: 2 новых модуля Python, правки backend, CLI и экрана фильма

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Конституция проекта — незаполненный шаблон, формальных гейтов нет. После проектирования нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/004-kinogo-primary-source/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/backend-changes.md
└── tasks.md
```

### Source Code (repository root)

```text
src/mpv_launcher/
├── kinogo.py        # новое: поиск, страница фильма, ссылка на поток, варианты качества
├── sources.py       # новое: порядок источников и переход на запасной
├── scraper.py       # поля source и referer, звук Chrome выключен
├── backend.py       # источники, обновление ссылки, referer
├── settings.py      # kinogo_url
├── presets.py       # network-timeout
└── cli.py           # тот же порядок источников

app/src/
├── lib/api.ts · lib/logic.ts
├── screens/Movie.svelte · Results.svelte · Settings.svelte
└── App.svelte

tests/unit/test_kinogo.py · test_sources.py   # новые
```

**Structure Decision**: источник — отдельный модуль рядом с `scraper.py`. Выбор источника вынесен в `sources.py`, чтобы приложение и CLI вели себя одинаково.

## Риски

| Риск | Что делаем |
|------|------------|
| Сервер `atlas` закроют или изменят | вариант с `cfnd`, затем HDRezka; причина в журнале |
| Узел файла на `atlas` не отвечает (наблюдалось) | вариант скрывается, остаётся лучший доступный; `--network-timeout` |
| Изменится разметка списка озвучек плеера | показываем только текущую озвучку, просмотр продолжает работать |
| Разрешение нельзя проверить в приложении без `ffprobe` | подписи берутся из плейлиста `atlas`; реальный размер показывает плеер, соответствие проверено вручную на 9 фильмах |
