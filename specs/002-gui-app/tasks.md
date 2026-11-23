# Tasks: GUI-приложение (двойной клик)

**Feature**: `002-gui-app` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]** — параллельно (разные файлы, нет зависимостей от незавершённого).
- **[US#]** — задача user story. TDD: тесты перед реализацией.

## Path Conventions

Расширяем пакет `src/mpv_launcher/`; упаковка в `packaging/` и `build/`; тесты в `tests/unit/`.

---

## Phase 1: Setup

- [X] T001 Добавить optional-dependencies `build = ["pyinstaller>=6"]` в `pyproject.toml` и каталоги `packaging/`, `build/`

## Phase 2: Foundational (Blocking Prerequisites)

**Блокирует user stories: правки ядра 001, от которых зависят GUI и бандл.**

- [X] T002 [P] `tests/unit/test_locate.py`: find_mpv — мок `shutil.which` (найдено в PATH → этот путь), мок отсутствия в PATH + существующий кандидат по ОС → путь кандидата, ничего нет → None (моки `platform.system`, `os.path.isfile`)
- [X] T003 [P] Дополнить `tests/unit/test_presets.py`: profiles_dir — env override; `sys.frozen=True`+`sys._MEIPASS` → `<_MEIPASS>/mpv-profiles`; иначе repo (monkeypatch)
- [X] T004 Реализовать `src/mpv_launcher/locate.py` → `find_mpv()` (PATH + кандидаты по ОС, см. data-model)
- [X] T005 Изменить `src/mpv_launcher/presets.py` → `profiles_dir()`: env → frozen(`sys._MEIPASS`) → repo
- [X] T006 Изменить `src/mpv_launcher/runner.py`: использовать `locate.find_mpv()`; подставлять найденный путь как argv[0] вместо `"mpv"`; при None → `EXIT_NO_MPV`. Обновить `tests/unit/test_runner.py` (мокать `runner.locate.find_mpv`)

## Phase 3: User Story 1 — Запуск двойным кликом из буфера (Priority: P1) 🎯 MVP

**Goal**: без аргументов берёт ссылку из буфера и запускает mpv (профиль auto, пресет film).

**Independent Test**: `python -m mpv_launcher.__gui__` при валидной ссылке в буфере → mpv играет.

### Tests for User Story 1 ⚠️

- [X] T007 [P] [US1] `tests/unit/test_gui.py`: happy path — мок `clipboard.read`→валидный URL, мок `runner.run`→0, мок `machine.resolve`; `gui_main()` зовёт `runner.run` с планом (Options content=="film", profile разрешён) и возвращает 0

### Implementation for User Story 1

- [X] T008 [US1] Реализовать `src/mpv_launcher/gui.py` → `gui_main()`: clipboard.read → url.validate → machine.resolve("auto") → presets.build_plan(Options(url, content="film")) → runner.run; возвращает код
- [X] T009 [US1] Реализовать `src/mpv_launcher/__gui__.py`: `sys.exit(gui.gui_main())`; проверить запуск `python -m mpv_launcher.__gui__`

**Checkpoint US1**: двойной клик (эмуляция запуском модуля) играет поток.

---

## Phase 4: User Story 2 — Нативные диалоги ошибок (Priority: P2)

**Goal**: пустой буфер / нет mpv → нативное окно, не stderr.

**Independent Test**: пустой буфер → диалог, код 3; mpv не найден → диалог, код 4.

### Tests for User Story 2 ⚠️

- [X] T010 [P] [US2] `tests/unit/test_dialog.py`: show_error — мок `platform.system`+`subprocess.run` (Darwin → вызван osascript с текстом); Windows-ветка через мок `ctypes`; прочее → stderr; исключение механизма не пробрасывается
- [X] T011 [P] [US2] Дополнить `tests/unit/test_gui.py`: пустой буфер (`clipboard.read`→None) → вызван `dialog.show_error`, `runner.run` не вызван, код 3; mpv не найден (`runner.run`→4) → вызван `dialog.show_error`, код 4

### Implementation for User Story 2

- [X] T012 [US2] Реализовать `src/mpv_launcher/dialog.py` → `show_error(message)` (osascript / MessageBoxW / stderr; без исключений наружу)
- [X] T013 [US2] Встроить диалоги в `gui.py`: при невалидной ссылке и при коде `EXIT_NO_MPV` от runner звать `dialog.show_error` с понятным текстом (в GUI подавить дублирующий stderr runner'а)

**Checkpoint US2**: ошибки видны нативным окном.

---

## Phase 5: User Story 3 — Распространяемые артефакты (Priority: P3)

**Goal**: `.app`/`.dmg` на macOS; `.exe` на Windows через готовый скрипт; профили внутри бандла.

**Independent Test**: сборка на macOS даёт запускаемый `.app`/`.dmg`; скрипт на Windows даёт `.exe`.

### Implementation for User Story 3

- [X] T014 [P] [US3] `packaging/mpvplay-macos.spec`: entry `__gui__`, `console=False`, `datas=[('mpv-profiles','mpv-profiles')]`, `BUNDLE` с `bundle_identifier='dev.mamoru.mpvplay'`
- [X] T015 [P] [US3] `packaging/mpvplay-windows.spec`: entry `__gui__`, `console=False`, onedir, те же `datas`
- [X] T016 [P] [US3] `build/build_macos.sh`: `pyinstaller packaging/mpvplay-macos.spec` + `hdiutil create` → `dist/mpvplay.dmg`
- [X] T017 [P] [US3] `build/build_windows.ps1`: `pyinstaller packaging/mpvplay-windows.spec` (для пользователя)
- [X] T018 [US3] Собрать на этом маке: прогнать `build/build_macos.sh`, проверить `dist/mpvplay.app` и `dist/mpvplay.dmg`, что профили внутри бандла и приложение стартует (находит mpv, играет/или даёт корректный диалог)

**Checkpoint US3**: есть .app/.dmg; .exe собирается скриптом на Windows.

---

## Phase 6: Polish & Cross-Cutting

- [X] T019 [P] Дополнить `README.md`: раздел «Приложение (двойной клик)» — где взять .app/.dmg, как собрать .exe, что mpv нужен отдельно
- [X] T020 Финальный прогон `pytest -q` зелёным; сверка с contracts/gui-and-packaging.md

---

## Dependencies & Execution Order

- **Setup (T001)** → далее.
- **Foundational (T002–T006)** → блокирует всё: locate/profiles/runner нужны и GUI, и бандлу.
- **US1 (T007–T009)** → MVP, поверх foundational.
- **US2 (T010–T013)** → поверх US1 (трогает gui.py).
- **US3 (T014–T018)** → поверх рабочего GUI (бандлит его); T018 — реальная сборка после US1/US2.
- **Polish (T019–T020)** → в конце.

### Parallel Opportunities

- Foundational: тесты T002,T003 [P]; затем T004,T005 [P], потом T006.
- US3: спеки и скрипты T014–T017 все [P] (разные файлы); T018 — после них и после GUI.

## Implementation Strategy

MVP = Setup + Foundational + US1 (двойной клик играет из буфера). Затем US2 (диалоги),
US3 (сборка .app/.dmg + скрипт .exe), Polish.

## Notes

- mpv и сборка (`.app`) реально запускаются только в T018; юниты их мокают.
- Windows `.exe` в этой сессии не собирается — только скрипт/спек.

## Task Summary

- **Всего**: 20 (T001–T020)
- Setup 1 · Foundational 5 · US1 3 · US2 4 · US3 5 · Polish 2
- **MVP**: T001–T009
