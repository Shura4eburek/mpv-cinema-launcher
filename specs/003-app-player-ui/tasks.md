---

description: "Task list for the new application and player interface"
---

# Tasks: Новый интерфейс приложения и плеера

**Input**: Design documents from `specs/003-app-player-ui/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: логика покрывается pytest, `cargo test` и Vitest, как указано в plan.md; экраны и плеер проверяются вручную по quickstart.md.

**Organization**: задачи сгруппированы по пользовательским историям.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно выполнять параллельно (разные файлы, нет зависимостей)
- **[Story]**: история из spec.md

---

## Phase 1: Setup

**Purpose**: зафиксировать текущие исправления и снять главный риск до начала работы

- [x] T001 Закоммитить исправления зеркал и `fs=yes` (`src/mpv_launcher/`, `tests/unit/`, `mpv-profiles/desktop-4070ti.conf`) в `003-hdrezka-search`, запушить и создать от этой ветки `003-app-player-ui`
- [x] T002 Пользователь запускает проверку uosc; по `panel.png`, `menu.png` и `result.txt` подтвердить панель, значки, русский язык и работу без `bin/` либо вернуться к plan.md
- [x] T003 Включить uosc 5.13.0 без `bin/`, шрифты и текст лицензии в `mpv-profiles/player/` (`uosc/`, `fonts/`, `LICENSE-uosc.txt`)
- [x] T004 Создать каркас Tauri 2.12, Svelte 5 и TypeScript в `app/` (`package.json`, `vite.config.ts`, `index.html`, `src-tauri/tauri.conf.json`), добавить `node_modules` и `target` в `.gitignore`
- [x] T005 [P] Настроить Vitest в `app/package.json` и `app/vite.config.ts`

---

## Phase 2: Foundational

**Purpose**: сквозной срез «окно → Rust → Python → окно»; блокирует все истории

- [x] T006 [P] Написать тесты очереди Selenium и потоков в `tests/unit/test_jobs.py`: операции Selenium идут строго последовательно, постер и запуск не ждут очередь
- [x] T007 Реализовать очередь и потоки в `src/mpv_launcher/jobs.py`
- [x] T008 [P] Написать тесты протокола в `tests/unit/test_backend.py`: разбор строк, неизвестный метод, плохой JSON не завершают процесс, коды ошибок, проверка `url` (только `http` и `https`), конец stdin завершает драйвер
- [x] T009 Реализовать сервер в `src/mpv_launcher/backend.py` по `contracts/backend-protocol.md` с методами `status`, `search`, `movie`, `translator_streams`; при старте забрать настоящий stdout и перенаправить fd 1 в stderr
- [x] T010 [P] Написать тесты разбора и маршрутизации сообщений в `app/src-tauri/src/backend.rs`
- [x] T011 Реализовать в `app/src-tauri/src/backend.rs` запуск Python без окна консоли, сопоставление `id`, запись stderr в журнал, однократный перезапуск, событие `backend_down` и остановку: закрыть stdin и снять процесс через 3 секунды
- [x] T012 Реализовать команды Tauri в `app/src-tauri/src/main.rs` и минимальные права в `app/src-tauri/capabilities/main.json`, без плагинов shell и fs; задать CSP `default-src 'self'` в `tauri.conf.json`
- [x] T013 Реализовать типизированный клиент в `app/src/lib/api.ts`
- [x] T014 Сделать минимальный поиск с текстовым выводом в `app/src/App.svelte` и пройти раздел «Сквозной срез» из `quickstart.md`

**Checkpoint**: поиск работает через всю цепочку, после закрытия окна не остаётся процессов.

---

## Phase 3: User Story 1 - Удобное управление в плеере (Priority: P1) 🎯 MVP

**Goal**: панель поверх видео с названием, перемоткой, громкостью, дорожками и субтитрами.

**Independent Test**: запустить поток, в том числе из буфера, и выполнить основные действия только мышью.

- [x] T015 [P] [US1] Обновить и дополнить `tests/unit/test_presets.py`: аргументы скина, название, «Видео по ссылке», URL последний, при отсутствии `player/` есть предупреждение и нет аргументов скина
- [x] T016 [US1] Добавить `title` в `Options` в `src/mpv_launcher/cli.py`
- [x] T017 [US1] Добавить аргументы скина и `--force-media-title` в `src/mpv_launcher/presets.py` по `contracts/ui-and-player.md`
- [x] T018 [P] [US1] Написать тесты `play` и `play_clipboard` в `tests/unit/test_backend.py`: непустой `urls`, каждый адрес проходит `url.validate`, события `playback_finished` и `playback_failed`
- [x] T019 [US1] Реализовать `play`, `play_clipboard` и `copy_text` в `src/mpv_launcher/backend.py` через `runner.run_with_fallback`
- [x] T020 [US1] Добавить временную кнопку запуска первого результата в `app/src/App.svelte` и пройти раздел «Плеер (US1)» из `quickstart.md`

**Checkpoint**: фильм запускается из нового окна и управляется мышью.

---

## Phase 4: User Story 2 - Каталог вместо списка результатов (Priority: P2)

**Goal**: сетка постеров и страница фильма с понятными состояниями.

**Independent Test**: найти фильм, открыть и запустить, не заходя в настройки.

- [x] T021 [P] [US2] Написать тесты `app/src/lib/logic.test.ts`: год и качество, обрезка названий, текст и действие для каждого кода ошибки
- [x] T022 [US2] Реализовать `app/src/lib/logic.ts`
- [x] T023 [P] [US2] Написать тесты `poster` в `tests/unit/test_backend.py`: только `http` и `https`, повторный запрос берётся из кэша, ошибка загрузки возвращает код
- [x] T024 [US2] Реализовать `poster` в `src/mpv_launcher/backend.py` и разрешить протокол `asset` только для каталога кэша в `app/src-tauri/tauri.conf.json`
- [x] T025 [P] [US2] Создать единое тёмное оформление в `app/src/styles/theme.css`
- [x] T026 [P] [US2] Создать карточку с заглушкой и подсказкой полного названия в `app/src/components/MovieCard.svelte` и адаптивную сетку в `app/src/components/PosterGrid.svelte`
- [x] T027 [P] [US2] Создать сообщение с действием в `app/src/components/StatusMessage.svelte`
- [x] T028 [US2] Реализовать `app/src/screens/Home.svelte` и `app/src/screens/Results.svelte`
- [x] T029 [US2] Реализовать `app/src/screens/Movie.svelte`: постер, название, год, рейтинг, описание, озвучка, качество, «Смотреть», копирование ссылки; без `{@html}`
- [x] T030 [US2] Реализовать навигацию и `ViewState` в `app/src/App.svelte`: сохранение запроса и прокрутки, отбрасывание устаревших ответов, запуск из буфера, замена временной кнопки из T020
- [x] T031 [US2] Пройти раздел «Приложение (US2)» из `quickstart.md` и проверку названия с HTML-разметкой

**Checkpoint**: путь от запроса до просмотра занимает не более 4 действий.

---

## Phase 5: User Story 3 - Понятные настройки качества картинки (Priority: P3)

**Goal**: настройки сохраняются, а в плеере видно реальное разрешение и состояние апскейла.

**Independent Test**: изменить настройки, перезапустить приложение; проверить индикатор в окне и на весь экран.

- [x] T032 [P] [US3] Написать `tests/unit/test_settings.py`: значения по умолчанию, `upscale_quality` только `max` или `basic`, `balanced` заменяется значением по умолчанию, каждое поле проверяется отдельно, повреждённый файл не мешает запуску, запись атомарна
- [x] T033 [US3] Реализовать `src/mpv_launcher/settings.py` по `data-model.md`
- [x] T034 [US3] Добавить `get_settings` и `set_settings` с проверкой значений в `src/mpv_launcher/backend.py`, тесты в `tests/unit/test_backend.py`
- [x] T035 [US3] Убрать `balanced` из `src/mpv_launcher/cli.py` и `src/mpv_launcher/presets.py`, сохранив совместимость CLI: старое значение работает как `max`
- [x] T036 [US3] Реализовать `app/src/screens/Settings.svelte` с понятными вариантами и применять `last_translator` и `last_quality` на `app/src/screens/Movie.svelte`, только если они есть у фильма
- [x] T037 [US3] Реализовать `mpv-profiles/player/cinema.lua`: состояния `active`, `not_needed`, `disabled`, `unavailable`, меню «Качество картинки» с реальным разрешением, переключение без перезапуска, признак проходов для FSRCNNX и Anime4K
- [x] T038 [US3] Добавить кнопку `picture-menu` в `uosc-controls` в `src/mpv_launcher/presets.py` и пройти раздел «Настройки и апскейл (US3)» из `quickstart.md`, разрешение сверить с `ffprobe`

**Checkpoint**: все три истории работают из исходников.

---

## Phase 6: Polish & Cross-Cutting

- [x] T039 Удалить `CinemaApp` из `src/mpv_launcher/gui.py`, оставив запуск из буфера; обновить `tests/unit/test_gui.py`, убрать `customtkinter` и `pillow` из `pyproject.toml`
- [x] T040 [P] Создать `packaging/backend.spec` и `packaging/backend_entry.py` (onedir, профили, Selenium Manager) и обновить `build/build_windows.ps1`: сборка backend, затем Tauri с `bundle.resources`; определение пути backend в `app/src-tauri/src/backend.rs`
- [x] T041 [P] Обновить `build/build_macos.sh`, удалить `packaging/mpvplay-*.spec` и `packaging/app.py`; отметить в документации, что macOS не проверена
- [x] T042 Собрать установщик и пройти раздел «Установщик» и «Регрессия» из `quickstart.md`
- [x] T043 [P] Обновить `README.md` и `AI_DEVELOPER_GUIDE.md`: новая архитектура, запуск и сборка; указать лицензию uosc
- [x] T044 Прогнать `pytest`, `npm test`, `cargo test` и проверить SC-001…SC-006 из `spec.md`

---

## Dependencies & Execution Order

- **Setup (T001–T005)**: T002 блокирует всё остальное. Если uosc не заработал, сначала правится plan.md.
- **Foundational (T006–T014)**: блокирует все истории.
- **US1 → US2 → US3**: US2 заменяет временную кнопку из US1; US3 использует панель из US1 и экран фильма из US2.
- **Polish**: после всех историй. T039 выполняется только после проверки нового окна.

### Parallel Opportunities

```text
Phase 2: T006, T008, T010
US2:     T021, T023, T025, T026, T027
Polish:  T040, T041, T043
```

Задачи выполняются последовательно в основном потоке; `[P]` лишь отмечает отсутствие зависимостей.

## Implementation Strategy

1. **MVP**: Setup, Foundational и US1. На этом этапе уже можно смотреть фильмы через новое окно и новую панель плеера.
2. Затем US2 даёт основной внешний вид приложения.
3. Затем US3 и замена старого GUI со сборкой установщика.
