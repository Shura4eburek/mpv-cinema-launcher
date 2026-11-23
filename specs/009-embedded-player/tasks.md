# Tasks: Плеер внутри окна приложения (проба на Windows)

**Input**: `specs/009-embedded-player/` (plan.md, spec.md, research.md, data-model.md, contracts/player-surface.md, quickstart.md)

**Tests**: для настройки, плана запуска и протокола, как в прежних функциях проекта; наложение, плавность и окна проверяются по quickstart.md, снимками экрана и замерами. Спецификация тесты отдельно не требует, но без них не подтвердить SC-005.

## Phase 1: Setup

- [X] T001 Создать git-ветку `009-embedded-player` от свежего `origin/main`, перенести в неё `specs/009-embedded-player/`, прогнать `python -m pytest`, `npm test`, `npm run check`, `cargo test --manifest-path app/src-tauri/Cargo.toml` и записать исходный результат в specs/009-embedded-player/research.md
- [X] T002 Добавить зависимость `windows-sys` только для Windows с нужными функциями окон в app/src-tauri/Cargo.toml

## Phase 2: Foundational

- [X] T003 Реализовать `player_surface_create`, `player_surface_show`, `player_surface_hide` и следование области за размером окна в app/src-tauri/src/player_surface.rs и зарегистрировать команды в app/src-tauri/src/main.rs; `wid` возвращается как целое положительное число, на другой системе ошибка `unsupported`
- [X] T004 Запустить mpv с `av://lavfi:testsrc2` и `--wid` в созданной области и снять снимок экрана; если видео не появляется в окне, остановиться и записать причину в specs/009-embedded-player/research.md

## Phase 3: User Story 1 - Узнать, можно ли показать интерфейс поверх видео (P1)

**Goal**: проверенный ответ на вопрос о наложении по каждому способу.

**Independent Test**: сценарии 1–5 quickstart.md на тестовом видео для способов А, Б и В.

**Отличие от задач**: проба включается переменной `MPV_CINEMA_SPIKE`, а не командой, а панель лежит в app/public/spike.html, а не в компоненте: так она не затрагивает интерфейс приложения и убирается одним шагом. Код в app/src-tauri/src/spike.rs.

- [X] T005 [US1] Добавить команду `spike_overlay` с режимом `"none"` и пробную панель с полупрозрачным фоном и кнопкой в app/src-tauri/src/player_surface.rs и app/src/components/SpikeOverlay.svelte; записать результат способа В
- [X] T006 [US1] Проверить способ Б: отдельное прозрачное окно верхнего уровня над областью, режим `"window"` в app/src-tauri/src/player_surface.rs, отдельная разрешённая страница в app/src-tauri/capabilities/main.json; следование за движением и размером окна, пропуск нажатий вне панели
- [X] T007 [US1] Проверить способ А: прозрачное главное окно, собранное отдельно через временную копию настроек `tauri.conf.json`, без изменения постоянной настройки app/src-tauri/tauri.conf.json; режим `"main"`, пропуск нажатий вне панели, сравнение обычного режима со снимком до изменения
- [X] T008 [US1] Заполнить таблицу по каждому способу со снимками экрана, выводом и рекомендацией в specs/009-embedded-player/research.md
- [X] T009 [US1] Показать итог владельцу проекта и получить решение, продолжать ли и каким способом. **Следующие фазы не начинать без этого решения** (решение: способ В, плеер на странице фильма)

## Phase 3а: Проба области на странице

**Goal**: узнать, заметно ли видео отстаёт от страницы при прокрутке, до остальной работы.

**Independent Test**: сценарии 5а и 5б quickstart.md на тестовом видео.

- [X] T030 Добавить параметры прямоугольника и `clip_top` в `player_surface_show` и новую команду `player_surface_move` в app/src-tauri/src/player_surface.rs с учётом масштаба окна; область больше не занимает всё окно
- [X] T031 Сделать пробную страницу с областью плеера и прокруткой в app/public/spike_page.html и app/public/spike_page.js: она наблюдает за элементом и вызывает `player_surface_move`; показать работу на тестовом видео и замерить отставание снимками в specs/009-embedded-player/research.md
- [X] T032 Показать прокрутку владельцу проекта и получить решение: область едет со страницей или закреплена вверху. **Следующие фазы не начинать без этого решения**

## Phase 4: User Story 5 - Отдельное окно остаётся по умолчанию (P1)

**Goal**: режим включается настройкой; без неё всё работает как раньше.

**Independent Test**: сценарий 6 quickstart.md.

- [X] T010 [US5] Добавить настройку `embedded_player`, по умолчанию `false`, в src/mpv_launcher/settings.py с тестом в tests/unit/test_settings.py; добавить поле в app/src/lib/api.ts
- [X] T011 [US5] Показать экспериментальный переключатель только на Windows в app/src/screens/Settings.svelte
- [X] T012 [US5] Добавить тест, что без `wid` аргументы плана запуска не меняются, в tests/unit/test_presets.py

## Phase 5: User Story 2 - Смотреть фильм внутри окна без потери качества (P1)

**Goal**: настоящий фильм идёт в окне с теми же улучшениями.

**Independent Test**: сценарии 7–9 quickstart.md.

- [X] T013 [US2] Добавить `wid` в `Options` и аргументы `--wid` и `--input-ipc-server` в src/mpv_launcher/presets.py и src/mpv_launcher/cli.py с тестами в tests/unit/test_presets.py
- [X] T014 [US2] Принимать `wid` в `play` и `play_clipboard` в src/mpv_launcher/backend.py: только целое положительное число, иначе `invalid_params`; на системе не Windows игнорировать; тесты в tests/unit/test_backend.py
- [X] T015 [US2] В app/src/screens/Movie.svelte при включённой настройке показывать область плеера на месте постера, создавать её, передавать `wid` в `play`, показывать по `playback_started`, скрывать по `playback_finished` и `playback_failed`, следить за положением элемента при прокрутке и изменении размера; ссылка из буфера остаётся в отдельном окне, так как у неё нет страницы (уточнено в spec.md); типы в app/src/lib/api.ts
- [X] T033 [US2] Скрывать кнопки окна uosc и заменить закрытие окна закрытием плеера на странице в src/mpv_launcher/presets.py при наличии `wid`, с тестом в tests/unit/test_presets.py
- [X] T016 [US2] Написать замер через канал управления (`vo-passes`, `frame-drop-count`, `vo-delayed-frame-count`, `estimated-vf-fps`), сравнить один фильм в обоих режимах и записать результат SC-002 в specs/009-embedded-player/research.md; замер не входит в приложение

## Phase 6: User Story 3 - Управлять плеером как обычно (P2)

**Goal**: клавиши, мышь, размер и полный экран работают как в отдельном окне.

**Independent Test**: сценарии 10–13 quickstart.md.

- [X] T017 [US3] Передавать фокус области при показе и после щелчка в app/src-tauri/src/player_surface.rs, чтобы клавиши и мышь попадали в mpv
- [X] T018 [US3] Добавить `player_surface_fullscreen` с возвратом к прежнему виду окна в app/src-tauri/src/player_surface.rs
- [X] T019 [US3] Читать свойство `fullscreen` через канал управления и отправлять событие `player_fullscreen` в src/mpv_launcher/backend.py с тестом разбора сообщений в tests/unit/test_backend.py; при его непригодности использовать запасной вариант из research.md §3 в mpv-profiles/player/cinema.lua
- [X] T020 [US3] Вызывать `player_surface_fullscreen` по событию `player_fullscreen` в app/src/App.svelte
- [ ] T021 [US3] Проверить масштаб Windows 150%, второй монитор и сворачивание, замерить SC-003 и записать результат в specs/009-embedded-player/research.md; поправить только найденные сбои в app/src-tauri/src/player_surface.rs

## Phase 7: User Story 4 - Вернуться к приложению и закрыть его (P2)

**Goal**: после просмотра виден прежний экран, процессов не остаётся.

**Independent Test**: сценарии 14–18 quickstart.md.

- [X] T022 [US4] Завершать встроенный процесс при закрытии в `Backend.close` и перед новым запуском, отдельный плеер продолжает переживать закрытие; в src/mpv_launcher/backend.py с тестами в tests/unit/test_backend.py
- [X] T023 [US4] Оставлять плеер после конца фильма через `--keep-open=yes` в src/mpv_launcher/presets.py при наличии `wid`, с тестом в tests/unit/test_presets.py; при закрытии плеера и `playback_failed` скрывать область и показывать постер и прежнее сообщение в app/src/screens/Movie.svelte
- [X] T034 [US4] Запускать другую серию или озвучку на том же месте при выборе во время просмотра, с завершением прежнего процесса, в app/src/screens/Movie.svelte и src/mpv_launcher/backend.py с тестом в tests/unit/test_backend.py
- [X] T035 [US4] Останавливать просмотр и убирать область при уходе со страницы и открытии настроек в app/src/screens/Movie.svelte и app/src/App.svelte
- [X] T036 [US4] Не допускать элементов под видео: открывать списки вне области плеера, скрывать видео на время трейлера и сообщений, в app/src/screens/Movie.svelte, app/src/components/Dropdown.svelte и app/src/App.svelte
- [X] T024 [US4] Проверить запасной адрес с тем же `--wid`, отмену запуска и повторные запуски; поправить только найденные сбои в src/mpv_launcher/backend.py

## Phase 8: Polish

- [X] T025 Удалить пробу: app/src-tauri/src/spike.rs, app/public/spike.html, app/public/spike.js и функцию `show_behind_page` в app/src-tauri/src/player_surface.rs
- [X] T026 [P] Описать режим, область и ограничения в AI_DEVELOPER_GUIDE.md
- [X] T027 [P] Добавить изменения протокола в specs/003-app-player-ui/contracts/backend-protocol.md
- [X] T028 Прогнать `python -m pytest`, `npm test`, `npm run check`, `cargo test --manifest-path app/src-tauri/Cargo.toml` и сравнить с результатом T001
- [ ] T029 Пройти оставшиеся сценарии specs/009-embedded-player/quickstart.md; плавность оценивает владелец проекта; записать итог и рекомендацию о дальнейшем в specs/009-embedded-player/research.md

## Dependencies

- Phase 2 блокирует всё; T004 подтверждает, что `--wid` вообще работает.
- US1 завершается решением T009, Phase 3а решением T032: от них зависят все следующие фазы и T025.
- US5 идёт раньше US2, чтобы настоящий просмотр сразу был закрыт настройкой.
- US3 и US4 зависят от US2.

## Parallel Example

```text
T026, T027 — разные документы
```

Остальные задачи идут последовательно: они правят одни файлы или требуют одного окна и одного плеера на экране.

## Implementation Strategy

- **MVP**: Phase 1–3, то есть ответ на вопрос о наложении. Это отдельный результат, даже если режим дальше не пойдёт.
- **Затем, после решения**: US5, US2, US3, US4.
- **В конце**: Polish.
