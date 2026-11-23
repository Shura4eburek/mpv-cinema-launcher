# Implementation Plan: Редизайн страницы фильма

**Branch**: `011-movie-page-redesign` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-movie-page-redesign/spec.md`

## Summary

Только интерфейс: backend и протокол не меняются. Страница тайтла раскладывается в три колонки: постер с действиями, информация, панель «Эпизоды» из 010. Факты из `info_table` раскладываются на бейджи, чипы и жанры новой функцией в `logic.ts`. Встроенный плеер переезжает в центральную колонку. Окно mpv уже следует за своим блоком на каждом кадре, поэтому достаточно перенести сам блок. Палитра сайта задаётся через токены `theme.css`, а захардкоженные цвета в компонентах заменяются токенами.

## Technical Context

**Language/Version**: TypeScript 5.9, Svelte 5

**Primary Dependencies**: Tauri 2 (без изменений), новых зависимостей нет

**Storage**: нет

**Testing**: Vitest (раскладка фактов, соседние серии, контраст палитры), `npm run check`, сравнение скриншотов с референсом в браузере с заглушкой backend и в собранном приложении

**Target Platform**: Windows 11 x64, macOS (встроенный плеер только на Windows)

**Project Type**: настольное приложение

**Performance Goals**: без изменений; видео следует за блоком, как в 009

**Constraints**: элементы страницы не перекрывают встроенное видео (вывод 009: интерфейс поверх видео невозможен); акцентный цвет прежний; ширина окна от 700 px без горизонтальной прокрутки

**Scale/Scope**: `styles/theme.css`, `screens/Movie.svelte`, `lib/logic.ts`; новые `components/FactBadges.svelte`, `components/PlayerBar.svelte`; замена цветов в остальных компонентах и экранах

## Constitution Check

`.specify/memory/constitution.md` не заполнен (шаблон), проверок нет. После дизайна без изменений.

## Project Structure

### Documentation (this feature)

```text
specs/011-movie-page-redesign/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/movie-page-layout.md
└── tasks.md             # создаёт /speckit-tasks
```

### Source Code (repository root)

```text
app/src/
├── styles/theme.css               # палитра сайта токенами
├── lib/logic.ts                   # titleFacts(): бейджи, чипы, жанры; neighbourEpisodes()
├── lib/logic.test.ts
├── components/FactBadges.svelte   # новый: строка бейджей над названием
├── components/PlayerBar.svelte    # новый: шапка встроенного плеера «‹ Серия N ›» и закрытие
├── components/*.svelte            # цвета → токены
├── screens/Movie.svelte           # три колонки, кнопки под постером, плеер в центре
├── screens/*.svelte               # цвета → токены
└── App.svelte                     # цвета → токены
```

**Structure Decision**: Разбор фактов — чистая функция в `logic.ts`, чтобы её покрывал Vitest. Разметка остаётся в `Movie.svelte`, наружу выносятся только самостоятельные блоки: бейджи и шапка плеера.

## Этапы

1. **Палитра (US3)**: токены в `theme.css`, замена захардкоженных цветов, проверка контраста.
2. **Раскладка (US1)**: колонки, кнопки под постером, бейджи, чипы, жанры, карточка описания, адаптивность.
3. **Плеер (US2)**: блок плеера в центральной колонке, информация под колонками, шапка со стрелками.
4. **Сверка**: скриншоты с референсом, все состояния страницы.
