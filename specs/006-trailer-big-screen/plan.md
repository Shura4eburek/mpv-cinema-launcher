# Implementation Plan: Трейлер, большой экран и доводка интерфейса

**Branch**: `006-trailer-big-screen` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

## Summary

Страница фильма и остальные экраны масштабируются вместе с окном, на странице появляются фон из постера, актёры и рекомендации сайта. Кнопка «Трейлер» ищет ролик на YouTube и играет его поверх окна. Поле поиска стоит по центру шапки и при активации затемняет содержимое. Значок перерисован со сдвигом фигуры влево.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.9, Svelte 5, Rust (Tauri 2.12)

**Primary Dependencies**: существующие; новых нет. Pillow только разово для значка, в приложение не входит.

**Storage**: нет, трейлеры не сохраняются

**Testing**: pytest, Vitest, `npm run check`, проверка в песочнице через отладочный порт WebView2

**Target Platform**: Windows 11, WebView2

**Project Type**: настольное приложение

**Performance Goals**: трейлер начинает играть за 5 с; страница фильма не медленнее прежнего

**Constraints**: без ключа YouTube API и без маскировки браузера; интерфейсу по-прежнему недоступен запуск программ, адрес для браузера строит backend

**Scale/Scope**: 1 новый модуль Python, 1 новый компонент, правки 6 компонентов и настроек CSP

## Constitution Check

`.specify/memory/constitution.md` не заполнен (шаблон), проверок нет.

## Project Structure

### Documentation

```text
specs/006-trailer-big-screen/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/backend-protocol.md
└── checklists/requirements.md
```

### Source Code

```text
src/mpv_launcher/
├── trailers.py          # новый: поиск роликов и адрес для браузера
├── scraper.py           # MovieDetails: actors, related; разбор HDRezka
├── kinogo.py            # разбор актёров и рекомендаций
└── backend.py           # методы trailer, open_trailer_search

app/src/
├── lib/scale.ts         # новый: масштаб интерфейса по окну
├── lib/logic.ts, api.ts
├── components/Trailer.svelte  # новый
├── App.svelte           # шапка, затемнение, перелёт поля, окно трейлера
├── screens/Movie.svelte # фон, актёры, рекомендации, кнопка
├── screens/Settings.svelte, Home.svelte
└── main.ts              # подключение масштаба

app/src-tauri/
├── tauri.conf.json      # CSP: frame-src youtube-nocookie
└── icons/*              # пересобраны

tests/unit/test_trailers.py, test_kinogo*.py, test_backend.py
```

## Решения

Подробности и альтернативы в [research.md](research.md).

- **Масштаб**: `zoom` на корне, число считает `uiScale(ширина, высота)`: `min(w/1800, h/1000)` в границах 1–1,75.
- **Трейлер**: `youtube-nocookie.com/embed` с `enablejsapi`; кандидаты до 5, при `onError` следующий.
- **Перелёт поля с главной**: View Transitions.
- **Рекомендации**: честный заголовок «Рекомендации сайта», потому что сайты показывают не похожие фильмы.

## Complexity Tracking

Нарушений нет.
