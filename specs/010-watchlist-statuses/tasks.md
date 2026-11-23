# Tasks: Мой список со статусами просмотра

**Input**: `specs/010-watchlist-statuses/` (plan.md, spec.md, research.md, data-model.md, contracts/backend-watchlist.md, quickstart.md)

**Tests**: pytest для хранилища, протокола, поиска IMDb и конца просмотра; Vitest для фильтров и счётчиков — как в прежних функциях проекта. Без тестов не подтвердить SC-002, SC-004, SC-005. Интерфейс проверяется по quickstart.md.

## Phase 1: Setup

- [X] T001 Прогнать `python -m pytest`, `npm test` и `npm run check` в app/ на ветке `010-watchlist-statuses` и записать исходный результат в конец specs/010-watchlist-statuses/research.md

## Phase 2: Foundational (хранилище)

**Цель**: модуль списка без интерфейса и сети; на нём строятся все истории.

- [X] T002 Создать src/mpv_launcher/watchlist.py: константы `STATUSES = ("watching", "planned", "completed")`, `KINDS = ("film", "series")`; `default_path()` = `settings.data_dir() / "watchlist.json"`; `fallback_key(title, orig_title, year, kind)` → `t:<kind>:<год>:<название>` по research.md R3 (оригинальное название, иначе русское без «(… сезон …)» и части после « / »; нижний регистр, ё→е, только буквы и цифры через один пробел); проверка `title`-описания из contracts/backend-watchlist.md (`title` и `url` обязательны, `url` http(s), `kind` ∈ `film|series`, `year` 4 цифры или null) с `ValueError`
- [X] T003 В src/mpv_launcher/watchlist.py реализовать класс `Watchlist(path)`: загрузка `{"version": 1, "items": {}, "lookups": {}}`; нечитаемый или неверный файл переименовывается в `watchlist.broken-<время>.json`, список пустой, `warning = "watchlist_reset"` (FR-015); запись целиком через `tempfile.mkstemp` в том же каталоге и `os.replace`, временный файл удаляется при сбое (FR-008, как `settings.update`); все операции под одним `threading.Lock`
- [X] T004 В src/mpv_launcher/watchlist.py реализовать поиск записи по описанию тайтла в порядке data-model.md «Поиск записи по странице» (id из `lookups[fallback_key].imdb` → `items[fallback_key]` → запись с таким `fallback_key` под любым ключом) и `entries()` — записи без `deleted_at`, по `updated_at` убыв.; `updated_at`/`deleted_at` — ISO 8601 UTC
- [X] T005 В src/mpv_launcher/watchlist.py реализовать `set_status(title, status)`, `remove(title)` и `on_play_started(title)` по таблице переходов data-model.md: удаление ставит `deleted_at`, `status = null`, очищает `episodes`; повторное добавление снимает `deleted_at` с пустыми `episodes`; запуск ставит `watching` только если записи нет, она удалена или `planned`; каждое изменение обновляет данные тайтла (название, постер, адрес) и `updated_at`
- [X] T006 [P] Написать tests/unit/test_watchlist.py: ключи и нормализация (ё, регистр, «(1-2 сезон)», « / »), переходы статусов, удаление и повторное добавление, сортировка, повреждённый файл → копия и пустой список, сбой записи (`os.replace` бросает) не меняет прежний файл, перезагрузка из файла даёт те же записи

## Phase 3: User Story 1 - Поставить статус фильму или сериалу (P1) 🎯 MVP

**Goal**: выпадающий список статуса под постером, сохранение между перезапусками.

**Independent Test**: quickstart.md, сценарии 1, 2, 4, 10.

- [X] T007 [US1] В src/mpv_launcher/backend.py добавить параметр `watchlist_path` в `Backend.__init__` и методы `watchlist_get`, `watchlist_set_status`, `watchlist_remove` (очередь «сразу») по contracts/backend-watchlist.md; неверный `title` или статус → `ApiError("invalid_params")`, сбой записи → `internal`; в ответах запись без `fallback_key`
- [X] T008 [P] [US1] Добавить тесты методов из T007 в tests/unit/test_backend.py: создание, смена, удаление, неверные параметры, один и тот же тайтл с разными `url` одного зеркала и одинаковыми названием и годом даёт одну запись (FR-004)
- [X] T009 [US1] В app/src/lib/api.ts добавить типы `WatchStatus`, `WatchTitle`, `WatchEntry` и методы `watchlistGet`, `watchlistSetStatus`, `watchlistRemove`; константы подписей и цветов статусов: `watching` «Смотрю» `#3d3475`, `planned` «Запланировано» `#23436f`, `completed` «Просмотрено» `#2c5e2c`
- [X] T010 [US1] Создать app/src/components/StatusPicker.svelte на основе app/src/components/Dropdown.svelte: без записи — «Добавить в список» нейтрального цвета; с записью — подпись в цвете статуса; пункты трёх статусов и «Удалить из списка» (только у записи); выбор за 2 клика (SC-001); на время запроса кнопка недоступна, ошибка показывается через `StatusMessage`
- [X] T011 [US1] В app/src/screens/Movie.svelte собрать `WatchTitle` из данных страницы (название, оригинальное, год из `info_table["Год"]`, `kind` = `series`, если есть `series`, адрес страницы, постер), вызвать `watchlistGet` при открытии и показать `StatusPicker` под постером

## Phase 4: User Story 2 - Экран «Мой список» (P1)

**Goal**: все тайтлы списка с фильтром по статусу и переходом на страницу.

**Independent Test**: quickstart.md, сценарии 5, 11.

- [X] T012 [US2] В src/mpv_launcher/backend.py добавить метод `watchlist_list` (очередь «сразу»): `{ items, warning? }`, `warning` передаётся один раз после сброса повреждённого файла; тест в tests/unit/test_backend.py
- [X] T013 [P] [US2] В app/src/lib/logic.ts добавить `filterWatchlist(items, filter)` и `countByStatus(items)` (фильтры `all|watching|planned|completed`), тесты в app/src/lib/logic.test.ts, включая 500 записей
- [X] T014 [US2] В app/src/lib/api.ts добавить `watchlistList`; создать app/src/screens/Watchlist.svelte: вкладки «Все / Смотрю / Запланировано / Просмотрено» со счётчиками, сетка постеров через app/src/components/PosterGrid.svelte (без постера — заглушка с названием), цветная метка статуса на карточке, пустое состояние с подсказкой «Откройте фильм и выберите статус под постером»
- [X] T015 [US2] В app/src/App.svelte добавить экран `watchlist` и кнопку «Мой список» в шапке рядом с «Настройки»; клик по карточке открывает страницу тайтла с адресом, переведённым на текущее зеркало из настроек (research.md R7); предупреждение `watchlist_reset` показывается один раз через `StatusMessage`

## Phase 5: Поиск id IMDb (FR-003, FR-016)

**Goal**: записи переходят на id IMDb, один тайтл — одна запись.

**Independent Test**: quickstart.md, сценарий 3.

- [X] T016 [P] (отличие: сбой сети — исключение `imdb.Unavailable`, а не `None`, чтобы не запоминать его как «не найдено») Создать src/mpv_launcher/imdb.py: `find_id(title, year, kind, timeout=5) -> str | None` через `https://v3.sg.media-imdb.com/suggestion/x/<запрос>.json`; принять кандидата, только если совпадает нормализованное `l` (та же нормализация, что в `watchlist.fallback_key`), `y` равен году (±1 для сериалов), тип по `qid` (`movie`/`tvMovie` → film, `tvSeries`/`tvMiniSeries` → series) и подходящий кандидат ровно один; сбой сети и неверный ответ → `None` без исключения
- [X] T017 [P] Написать tests/unit/test_imdb.py на сохранённых ответах: точное совпадение, другой год, другой тип, два подходящих кандидата → None, сбой сети → None
- [X] T018 В src/mpv_launcher/watchlist.py реализовать `needs_lookup(title)` (нет `lookups` или «не найдено» старше 7 дней) и `apply_id(title, imdb_id | None)`: запись в `lookups[fallback_key]` с `checked_at`; перенос записи на id по data-model.md «Перенос на id» (свежий `updated_at` побеждает, `episodes` объединяются, старый ключ получает `deleted_at`); тесты в tests/unit/test_watchlist.py
- [X] T019 В src/mpv_launcher/backend.py добавить метод `watchlist_resolve` (очередь `io`) по контракту; в app/src/screens/Movie.svelte вызвать его в фоне после открытия страницы, не задерживая её, и обновить запись по ответу; тест в tests/unit/test_backend.py с подменой `imdb.find_id`

## Phase 6: User Story 3 - Отметки просмотренных серий (P2)

**Goal**: отметки серий по сезонам и «N / M».

**Independent Test**: quickstart.md, сценарий 6.

- [X] T020 [US3] В src/mpv_launcher/watchlist.py реализовать `set_episode(title, season, episode, watched)`: только для `kind == "series"`, иначе `ValueError`; серии без повторов, по возрастанию номера; отметка ставит статус как при запуске просмотра, снятие статус не меняет; тесты в tests/unit/test_watchlist.py
- [X] T021 [US3] В src/mpv_launcher/backend.py добавить метод `watchlist_set_episode`, в app/src/lib/api.ts — `watchlistSetEpisode`; тест в tests/unit/test_backend.py
- [X] T022 [US3] В app/src/screens/Movie.svelte добавить отметку «просмотрено» у каждой серии выбранного сезона и «N / M» рядом с `StatusPicker`; при смене сезона показываются его отметки; M — число серий сезона у текущего источника

## Phase 6а: Панель «Эпизоды» и полоса прогресса (добавлено по решению владельца 2026-11-16)

- [X] T031 [US3] Создать app/src/components/EpisodePanel.svelte: заголовок «Эпизоды» со счётчиком «N / M», выбор сезона, список серий (номер, название, качество у текущей, кружок-отметка), текущая серия подсвечена, просмотренные зачёркнуты; клик по строке выбирает серию, по кружку — ставит или снимает отметку
- [X] T032 [US3] В app/src/screens/Movie.svelte заменить выпадающие «Сезон»/«Серия» и кнопку отметки панелью в третьей колонке (до 1180 px — под страницей) и добавить полосу «Просмотрено N / M» под фактами о тайтле
- [X] T033 [US3] Выбор озвучки сериала перенести в панель «Эпизоды» (app/src/components/EpisodePanel.svelte); метка «N эп.» у озвучек — число серий выбранного сезона (пилюли в app/src/components/Dropdown.svelte через `badges`). Сайт число серий других озвучек не сообщает: они подгружаются в фоне по одной через `episode` после 1,5 с простоя страницы в app/src/screens/Movie.svelte; загрузка серии, запуск и уход со страницы отменяют фоновую загрузку

## Phase 7: User Story 4 - Автоматические статусы при просмотре (P2)

**Goal**: «Смотрю» при запуске, отметка досмотренной серии, предложение «Просмотрено».

**Independent Test**: quickstart.md, сценарии 7, 8.

- [X] T023 [US4] В src/mpv_launcher/player_ipc.py наблюдать также `duration` и `eof-reached`; добавить `duration_from_line` и `eof_from_line` и колбэки в `watch`; тесты в tests/unit/test_player_ipc.py
- [X] T024 [US4] В src/mpv_launcher/backend.py подключать канал управления (`ipc_server`) для обоих режимов (встроенный и отдельное окно), если в `play` есть `watch`; проверить, что src/mpv_launcher/presets.py передаёт `--input-ipc-server` без `wid`, и поправить при необходимости; для каждого запуска хранить последнюю позицию, длительность и признак конца файла
- [X] T025 [US4] В src/mpv_launcher/backend.py принять параметр `watch` в `play` (проверка по контракту): после успешного старта — `watchlist.on_play_started`, событие `watchlist_changed`; после завершения mpv без сбоя и отмены, если позиция ≥ 95% длительности или конец файла — отметить серию (если есть `season`/`episode`), событие `watchlist_changed`, затем `watch_completed { key, title, final }`; тесты в tests/unit/test_backend.py: досмотр, прерывание на середине, сбой воспроизведения, `Просмотрено` не меняется при запуске
- [X] T026 [US4] В app/src/screens/Movie.svelte передавать `watch` в `play` (`final` = фильм или последняя серия последнего сезона) и обновлять `StatusPicker` и отметки по `watchlist_changed`
- [X] T027 [US4] В app/src/App.svelte по `watch_completed` с `final: true` показывать ненавязчивое предложение «Отметить как просмотренное?» с «Да» / «Нет»: «Да» → `watchlistSetStatus(title, "completed")`, «Нет» ничего не меняет; предложение видно на любом экране

## Phase 8: Polish

- [X] T028 Прогнать `python -m pytest`, `npm test`, `npm run check` в app/ и сверить с исходным результатом T001
- [ ] T029 (частично: интерфейс проверен в браузере с заглушкой backend, протокол — сквозным прогоном с настоящим IMDb; запуск mpv и досмотр — в собранном приложении у владельца) Пройти сценарии 1–11 из specs/010-watchlist-statuses/quickstart.md и отметить результат в нём
- [X] T030 [P] Описать «Мой список», статусы и файл `watchlist.json` в README.md

## Dependencies

- Phase 2 блокирует все истории.
- US1 (Phase 3) → US2 (Phase 4): экран списка использует типы и константы из T009.
- Phase 5 (IMDb) зависит от Phase 2 и T011; истории без неё работают на запасном ключе.
- US3 (Phase 6) зависит от US1 (страница со `StatusPicker`).
- US4 (Phase 7) зависит от US1; T025 использует `set_episode` из T020, если сериал.

## Parallel Example

- Phase 2: T006 пишется параллельно с T003–T005 по data-model.md.
- Phase 3: T008 параллельно с T009–T010.
- Phase 4: T013 параллельно с T012.
- Phase 5: T016 и T017 параллельно с US2 и US3 — отдельные файлы.

## Implementation Strategy

1. MVP: Phase 1–3 — статус на странице, сохранение в файле.
2. Phase 4 — «Мой список»; после неё список уже полезен.
3. Phase 5 — id IMDb, задел под синхронизацию между устройствами.
4. Phase 6–7 — серии и автоматика.
5. Phase 8 — общая проверка.

## Phase 9: Convergence

- [X] T034 Подключить канал управления mpv на macOS через Unix-сокет (путь во временном каталоге в src/mpv_launcher/backend.py, подключение `socket.AF_UNIX` в src/mpv_launcher/player_ipc.py вместо `open()` для путей не вида `\\.\pipe\…`), чтобы досмотр отмечал серию и предлагал «Просмотрено» и там; тесты в tests/unit/test_player_ipc.py и tests/unit/test_backend.py per FR-013, FR-014, plan: Target Platform (partial)
