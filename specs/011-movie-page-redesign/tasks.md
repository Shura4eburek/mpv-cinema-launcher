# Tasks: Редизайн страницы фильма

**Input**: `specs/011-movie-page-redesign/` (plan.md, spec.md, research.md, data-model.md, contracts/movie-page-layout.md, quickstart.md)

**Tests**: Vitest для `titleFacts`, `neighbourEpisodes` и контраста палитры. Раскладка проверяется скриншотами по quickstart.md в браузере с заглушкой backend; встроенный плеер — в собранном приложении у владельца.

## Phase 1: Setup

- [X] T001 Прогнать `npx vitest run` и `npm run check` в app/ и записать исходный результат в конец specs/011-movie-page-redesign/research.md

## Phase 2: Foundational (палитра)

**Цель**: токены, на которых строятся все экраны.

- [X] T002 В app/src/styles/theme.css задать токены по research.md R4: `--bg: #000000`, `--surface: #161618`, `--surface-2: #222224`, `--border: #2c2c2f`, `--text: #e2e2e2`, `--muted: #8e8e93`, новые `--body: #a0a0a5`, `--input: #0d0d0e`, `--popover: #1a1a1c`; `--accent` и `--accent-hover` без изменений
- [X] T003 [P] Добавить в app/src/lib/logic.ts функцию `contrastRatio(foreground, background)` по формуле WCAG и тест в app/src/lib/logic.test.ts: `#e2e2e2`/`#222224` ≥ 4.5, `#a0a0a5`/`#161618` ≥ 4.5, `#8e8e93`/`#161618` ≥ 4.5, `#8e8e93`/`#222224` ≥ 4.5

## Phase 3: User Story 3 - Цвета и поверхности как у сайта (P3, но блокирует визуальную сверку остальных)

**Goal**: всё приложение в палитре сайта, акцент прежний.

**Independent Test**: quickstart.md, сценарий 7.

- [X] T004 [P] [US3] Заменить захардкоженные цвета токенами в app/src/App.svelte (граница шапки, затемнение под поиском `rgb(11 13 18 / 78%)` → `rgb(0 0 0 / 78%)`, поле поиска на `--input`)
- [X] T005 [P] [US3] Заменить захардкоженные цвета токенами в app/src/components/Dropdown.svelte (список на `--popover`, наведение `#272c3a` → производная от `--surface-2`), app/src/components/StatusPicker.svelte и app/src/components/EpisodePanel.svelte
- [X] T006 [P] [US3] Заменить захардкоженные цвета токенами в app/src/components/LampacSources.svelte, app/src/components/LoadProgress.svelte, app/src/components/MovieCard.svelte, app/src/components/PlayerOpening.svelte, app/src/components/Trailer.svelte
- [X] T007 [P] [US3] Заменить захардкоженные цвета токенами в app/src/screens/MirrorCheck.svelte, app/src/screens/Results.svelte, app/src/screens/Settings.svelte, app/src/screens/Watchlist.svelte; цвета статусов и смысловые цвета (ошибка, успех) оставить

## Phase 4: User Story 1 - Страница тайтла в три колонки (P1) 🎯 MVP

**Goal**: раскладка как у референса, все прежние действия доступны.

**Independent Test**: quickstart.md, сценарии 1–5, 8.

- [X] T008 [P] [US1] Добавить в app/src/lib/logic.ts `titleFacts(info, kind, episodeCount)` по data-model.md: `badges` (рейтинг «КП 7.1» / «IMDb 6.8» из первой пары «Рейтинги», тип «Фильм»/«Сериал», год как в `movieFacts`, «N эп.» при `episodeCount > 0` у сериала, «Время», «Возраст»), `chips` («Страна», «Режиссер» с подписью «Режиссёр», «Дата выхода»), `genres` (из «Жанр» по запятой, без пустых и повторов), `siteQuality` («В качестве»); пустые значения не дают бейджей и чипов; тесты в app/src/lib/logic.test.ts на данных KinoGo и HDRezka
- [X] T009 [P] [US1] Создать app/src/components/FactBadges.svelte: строка бейджей `badges` с тонами `rating` (зелёная звезда и число), `plain` (текст с разделителями «|»), `outline` (рамка), как в референсе
- [X] T010 [US1] В app/src/screens/Movie.svelte перестроить левую колонку: постер, `StatusPicker`, ряд «▶ Смотреть» (белая: фон `#fff`, текст `#000`) и «Трейлер» на `--surface-2`; «Закрыть плеер» на месте «Смотреть», пока идёт просмотр; до загрузки страницы — только «Трейлер»
- [X] T011 [US1] В app/src/screens/Movie.svelte перестроить центральную колонку по contracts/movie-page-layout.md: `FactBadges` над названием, название, оригинальное, чипы, полоса «Просмотрено», жанры-пилюли, озвучка (фильм) и качество, сообщения, описание в карточке (`--surface`, рамка, текст `--body`), актёры, «Скопировать ссылку на поток», Lampac; убрать таблицу фактов `dl`
- [X] T012 [US1] В app/src/screens/Movie.svelte сетка: сериал — `[левая] [центр] [Эпизоды]`, фильм — `[левая] [центр]`; до 1180 px панель на всю ширину под информацией, до 860 px всё в одну колонку; проверить отсутствие горизонтальной прокрутки при 700 px
- [X] T013 [US1] Проверить в app/src/screens/Movie.svelte состояния: загрузка (ход загрузки в центре), ошибка загрузки, нет видео с вариантами HDRezka, смена источника, перенесённая серия, ошибка потока — все в центральной колонке

## Phase 5: User Story 2 - Встроенный плеер в центральной колонке (P2)

**Goal**: видео в центре, шапка со стрелками, информация под колонками.

**Independent Test**: quickstart.md, сценарий 6.

- [X] T014 [P] [US2] Добавить в app/src/lib/logic.ts `neighbourEpisodes(episodes, current)` по data-model.md и тесты в app/src/lib/logic.test.ts (середина, первая, последняя, текущей нет в списке)
- [X] T015 [P] [US2] Создать app/src/components/PlayerBar.svelte: слева «‹», подпись («Серия N» по названию серии или название фильма), «›»; справа «✕»; стрелки недоступны без соседней серии и при `busy`; у фильма стрелок нет
- [X] T016 [US2] В app/src/screens/Movie.svelte перенести блок `.player` в центральную колонку под `PlayerBar`; при `watching` блок информации центральной колонки выводить под сеткой на всю ширину; постер со статусом и панель «Эпизоды» остаются; стрелки вызывают `loadEpisode(null, season, id)`, крестик — `stopWatching`; убедиться, что слежение `surface.move` работает без изменений

## Phase 6: Polish

- [X] T017 Прогнать `npx vitest run`, `npm run check`, `npm run build` в app/ и сверить с T001
- [X] T018 (скриншоты в браузере с заглушкой backend; встроенный плеер в собранном приложении — у владельца) Пройти сценарии 1–8 из specs/011-movie-page-redesign/quickstart.md в браузере с заглушкой backend, сделать скриншоты сериала и фильма при 1400, 1100 и 800 px и показать владельцу рядом со скриншотами референса
- [X] T019 [P] Обновить описание приложения в README.md (раздел «Возможности»: страница тайтла в три колонки, палитра)

## Dependencies

- Phase 2 (токены) → Phase 3 и Phase 4.
- US3 (Phase 3) не блокирует US1 по коду, но сверку скриншотов (T018) делать после неё.
- US2 (Phase 5) зависит от раскладки US1 (T010–T012).

## Parallel Example

- Phase 3: T004–T007 — разные файлы, параллельно.
- Phase 4: T008 и T009 параллельно, до T010–T011.
- Phase 5: T014 и T015 параллельно, до T016.

## Implementation Strategy

1. Phase 1–2 — токены.
2. Phase 4 (US1) — новая страница: уже можно показывать.
3. Phase 3 (US3) — палитра на остальных экранах.
4. Phase 5 (US2) — плеер в колонке.
5. Phase 6 — проверка и скриншоты для владельца.

## Phase 7: Convergence

- [X] T020 Перевести поля ввода на цвет полей сайта `var(--input)`: `.address` в app/src/screens/Settings.svelte и `input` в app/src/screens/MirrorCheck.svelte per FR-011, US3/AC1 (partial)
- [X] T021 Показывать ошибку загрузки страницы в центральной колонке, а постер карточки из поиска и «Трейлер» — слева, в app/src/screens/Movie.svelte per FR-012 (partial)
