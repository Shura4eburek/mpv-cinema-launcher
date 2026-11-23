# Tasks: Источники Lampac

**Input**: `specs/007-lampac-sources/` (plan.md, spec.md, research.md, data-model.md, contracts/)

**Tests**: для разбора ответов, состояния сервера и протокола; запуск и внешний вид проверяются по quickstart.md.

## Phase 1: Setup

- [x] T001 Проверить обрезанную сборку Lampac: без `.playwright`, чужих `runtimes` и лишних модулей; записать результат и итоговый размер в specs/007-lampac-sources/research.md
- [x] T002 Добавить загрузку версии 1.87.6 и рантайма 10.0.14 с проверкой сумм, обрезку и ресурсы в build/build_windows.ps1 и app/src-tauri/tauri.bundle.json
- [x] T003 [P] Добавить настройки сервера, текст лицензии и ссылку на исходный код в packaging/lampac/

## Phase 2: Foundational

- [x] T004 Добавить настройку `lampac_enabled`, по умолчанию `false`, в src/mpv_launcher/settings.py с тестом в tests/unit/test_settings.py

## Phase 3: User Story 2 - Включение Lampac (P1)

**Goal**: Lampac включается в настройках, состояние видно, процессы не остаются.

**Independent Test**: включить, дождаться «Работает», закрыть приложение, проверить процессы.

- [x] T005 [US2] Реализовать копирование в каталог данных, свободный порт, запуск на `127.0.0.1`, Job Object и состояния в src/mpv_launcher/lampac_server.py с тестами в tests/unit/test_lampac_server.py
- [x] T006 [US2] Подключить запуск, остановку, метод и событие `lampac_state` в src/mpv_launcher/backend.py с тестами в tests/unit/test_backend.py
- [x] T007 [US2] Добавить переключатель и состояние в app/src/screens/Settings.svelte и типы в app/src/lib/api.ts; скрыть их не на Windows
- [x] T008 [P] [US2] Показать состояние Lampac в app/src/screens/MirrorCheck.svelte

## Phase 4: User Story 1 - Другие источники фильма (P1)

**Goal**: источники Lampac на странице фильма запускаются в плеере.

**Independent Test**: выбрать источник у «Довод» и «Интерстеллар», дойти до воспроизведения.

- [x] T009 [P] [US1] Реализовать запросы и разбор в src/mpv_launcher/lampac.py: устойчивый `id` из названия и года, только `type: movie`, `similar` при точном совпадении, отбрасывание `abuse` и ответов не JSON; тесты в tests/unit/test_lampac.py на сохранённых ответах
- [x] T010 [US1] Добавить `lampac_sources`, `lampac_variants` с проверкой, что адрес локальный, и события в src/mpv_launcher/backend.py с тестами в tests/unit/test_backend.py
- [x] T011 [US1] Создать выбор источника, озвучки и качества с постепенным показом в app/src/components/LampacSources.svelte и логику в app/src/lib/logic.ts
- [x] T012 [US1] Подключить блок и запуск через `onplay` с обновлением ссылки перед стартом в app/src/screens/Movie.svelte; добавить `lampac` в `SourceId` в app/src/lib/api.ts

## Phase 5: User Story 3 - Сериалы (P2)

**Goal**: выбор сезона и серии.

**Independent Test**: запустить вторую серию второго сезона.

- [x] T013 [US3] Проверить формат сезонов и серий на запущенном Lampac и записать в specs/007-lampac-sources/research.md
- [x] T014 [US3] Разобрать сезоны и серии в src/mpv_launcher/lampac.py с тестами в tests/unit/test_lampac.py
- [x] T015 [US3] Добавить выбор сезона и серии в app/src/components/LampacSources.svelte

## Phase 6: Polish

- [x] T016 Обновить README.md и AI_DEVELOPER_GUIDE.md
- [x] T017 Собрать установщик и пройти specs/007-lampac-sources/quickstart.md в песочнице, включая 10 фильмов для SC-001

## Dependencies

T001 определяет T002. T002 и T003 нужны для T005. T005 перед T006, T007, T008. T009 перед T010, T010 перед T011, T011 перед T012. US3 после US1.

## Implementation Strategy

Сначала сервер (US2), без него источникам не с чем работать, затем источники (US1). После US1 можно остановиться и оценить пользу перед сериалами. Выполняет один исполнитель, по порядку.
