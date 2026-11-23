# Tasks: Трейлер, большой экран и доводка интерфейса

**Input**: `specs/006-trailer-big-screen/` (plan.md, spec.md, research.md, data-model.md, contracts/)

**Tests**: только для логики разбора, протокола и чистых функций; внешний вид проверяется по quickstart.md.

## Phase 1: Foundational

- [x] T001 Добавить поля `actors: list[str]` и `related: list[MovieSearchResult]` в `MovieDetails` в src/mpv_launcher/scraper.py и типы в app/src/lib/api.ts

## Phase 2: User Story 1 - Страница на большом экране (P1)

**Goal**: все экраны соразмерны окну, страница фильма заполнена.

**Independent Test**: снимки одного фильма при 1000×700, 1920×1080, 2560×1440.

- [x] T002 [P] [US1] Разбирать актёров (до 12) и рекомендации (до 8, без сериалов) KinoGo в src/mpv_launcher/kinogo.py с тестами в tests/unit/test_kinogo_extras.py
- [x] T003 [P] [US1] Разбирать актёров и рекомендации HDRezka с приведением адреса к хосту страницы в src/mpv_launcher/scraper.py с тестами в tests/unit/test_kinogo_extras.py
- [x] T004 [P] [US1] Добавить `uiScale` и подключение к окну в app/src/lib/scale.ts, тесты в app/src/lib/scale.test.ts, вызов в app/src/main.ts
- [x] T005 [US1] Добавить фон из постера, описание целиком, актёров и «Рекомендации сайта» в app/src/screens/Movie.svelte; добавить компактный режим в app/src/components/PosterGrid.svelte
- [x] T006 [P] [US1] Отцентровать настройки в app/src/screens/Settings.svelte

## Phase 3: User Story 2 - Трейлер (P2)

**Goal**: трейлер играет поверх окна.

**Independent Test**: трейлер у «Довод», закрытие, запуск фильма.

- [x] T007 [P] [US2] Реализовать поиск роликов и адрес поиска в src/mpv_launcher/trailers.py с тестами в tests/unit/test_trailers.py
- [x] T008 [US2] Добавить методы `trailer` и `open_trailer_search` в src/mpv_launcher/backend.py с тестами в tests/unit/test_backend.py и вызовы в app/src/lib/api.ts
- [x] T009 [US2] Разрешить `frame-src https://www.youtube-nocookie.com` в app/src-tauri/tauri.conf.json
- [x] T010 [US2] Создать окно трейлера: кандидаты, `onError`, Esc, крестик, щелчок вокруг, «Открыть в браузере», сообщение об ошибке в app/src/components/Trailer.svelte
- [x] T011 [US2] Подключить окно трейлера в app/src/App.svelte и кнопку «Трейлер» в app/src/screens/Movie.svelte, с годом из `yearFrom` в app/src/lib/logic.ts
- [x] T012 [US2] Проверить звук настоящим кликом; при необходимости добавить аргумент автозвука в app/src-tauri/tauri.conf.json

## Phase 4: User Story 3 - Плавный поиск (P3)

**Goal**: поле по центру сверху, затемнение и плавные переходы.

**Independent Test**: Esc на странице фильма не меняет её; поиск с главной перелетает.

- [x] T013 [US3] Поставить поле по центру шапки, добавить затемнение, Esc и щелчок мимо в app/src/App.svelte
- [x] T014 [US3] Добавить перелёт поля с главной через View Transitions в app/src/App.svelte и app/src/screens/Home.svelte

## Phase 5: User Story 4 - Значок (P3)

**Independent Test**: все размеры значка при увеличении.

- [x] T015 [P] [US4] Перерисовать значок и пересобрать набор в app/src-tauri/icons/
- [x] T016 [US4] Заменить символ логотипа на SVG в app/src/App.svelte

## Phase 6: Polish

- [x] T017 Обновить README.md и AI_DEVELOPER_GUIDE.md
- [x] T018 Пройти specs/006-trailer-big-screen/quickstart.md в песочнице, включая проверку 10 фильмов для SC-006

## Dependencies

T001 перед T002, T003, T005. T008 перед T010. T010 перед T011. Истории независимы и делаются по порядку приоритета.

## Implementation Strategy

Сначала US1 как главная проблема, затем трейлер, затем поиск и значок. Параллельные задачи выполняются последовательно одним исполнителем.
