# Tasks: mpv HLS Launcher

**Feature**: `001-mpv-hls-launcher` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]** — можно делать параллельно (разные файлы, нет зависимостей от незавершённых задач).
- **[US#]** — задача относится к user story из спеки (только в фазах user stories).
- Тесты включены: пользователь запросил **TDD** — в каждой story тесты идут перед реализацией.

## Path Conventions

Single project: код в `src/mpv_launcher/`, тесты в `tests/unit/`, mpv-конфиги в `mpv-profiles/`.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Создать структуру проекта: каталоги `src/mpv_launcher/`, `tests/unit/`, `mpv-profiles/`; файлы `src/mpv_launcher/__init__.py` и `src/mpv_launcher/__main__.py` (пустой stub, импортирующий `cli.main`)
- [X] T002 Создать `pyproject.toml`: пакет `mpv_launcher` (requires-python >=3.10, stdlib-only), console-script `mpvplay = mpv_launcher.cli:main`, optional-dependencies `dev = ["pytest"]`
- [X] T003 [P] Настроить pytest в `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) и добавить smoke-тест `tests/unit/test_smoke.py`, проверяющий, что пакет импортируется и `--help` не падает

## Phase 2: Foundational (Blocking Prerequisites)

**Блокирует все user stories.**

- [X] T004 Определить константы кодов выхода (`EXIT_OK=0, EXIT_ARGS=2, EXIT_NO_URL=3, EXIT_NO_MPV=4`) и dataclass `Options` в `src/mpv_launcher/cli.py` согласно data-model.md: поля `url: str|None`, `profile: str="auto"`, `content: str="film"`, `referer: str|None`, `user_agent: str|None`, `headers: list[str]`, `dry_run: bool=False` (только структуры, без логики разбора)
- [X] T005 Определить dataclass `LaunchPlan` (`mpv_args: list[str]`, `warnings: list[str]`) в `src/mpv_launcher/presets.py` как контракт между сборкой команды и `runner` (без логики)

---

## Phase 3: User Story 1 — Просмотр одной командой (Priority: P1) 🎯 MVP

**Goal**: ссылка (аргумент или буфер) → mpv играет поток. Профиль пока базовый (`generic`).

**Independent Test**: `mpvplay "<url>"` запускает mpv; `mpvplay` без аргумента берёт ссылку из буфера; пустой ввод → код 3.

### Tests for User Story 1 ⚠️ (пишутся первыми, должны падать)

- [X] T006 [P] [US1] `tests/unit/test_url.py`: валидация ссылки — http/https с непустым host проходит; пустая строка и не-URL → невалидна; `looks_like_hls` истинно при наличии `.m3u8`/`hls` в URL
- [X] T007 [P] [US1] `tests/unit/test_clipboard.py`: чтение буфера с моком `subprocess` — берётся первая непустая строка; пустой вывод → `None`; выбор команды по `platform.system()` (Darwin→pbpaste, Windows→powershell Get-Clipboard)
- [X] T008 [P] [US1] `tests/unit/test_runner.py`: при отсутствии mpv (мок `shutil.which`→None) код выхода 4 и mpv не вызывается; при `dry_run=True` argv печатается в stdout и `subprocess` не запускается; `url` — последний элемент argv
- [X] T009 [P] [US1] `tests/unit/test_cli.py`: `url` из аргумента приоритетнее буфера; при пустом аргументе читается буфер (мок); пустой ввод отовсюду → код 3; stderr/stdout разделены

### Implementation for User Story 1

- [X] T010 [US1] Реализовать `validate(url)` и `looks_like_hls(url)` в `src/mpv_launcher/url.py` (через `urllib.parse`)
- [X] T011 [US1] Реализовать `read()` в `src/mpv_launcher/clipboard.py` (платформенные команды через `subprocess`, best-effort для Linux: wl-paste→xclip→xsel)
- [X] T012 [US1] Реализовать минимальную сборку команды в `src/mpv_launcher/presets.py`: `build_plan(options, machine_profile=None)` → `LaunchPlan` с argv `["mpv", "--profile=gpu-hq", url]` (базовый апскейл для MVP)
- [X] T013 [US1] Реализовать `run(plan, dry_run)` в `src/mpv_launcher/runner.py`: проверка `shutil.which("mpv")` (нет → код 4 + подсказка на stderr); `dry_run` → печать argv; иначе `subprocess.run` и проксирование кода выхода
- [X] T014 [US1] Реализовать `parse(argv)` и `main(argv=None)` в `src/mpv_launcher/cli.py`: позиционный `url`, `--dry-run`; fallback на `clipboard.read()`; `url.validate()` (нет → код 3); вызвать `presets.build_plan` → `runner.run`
- [X] T015 [US1] Связать `src/mpv_launcher/__main__.py` с `cli.main` и убедиться, что `python -m mpv_launcher` и `mpvplay` работают

**Checkpoint US1**: поток играется одной командой с базовым апскейлом.

---

## Phase 4: User Story 2 — Автопрофиль под железо (Priority: P2)

**Goal**: на M1 Air — облегчённый профиль, на Windows+NVIDIA — тяжёлый; флаг `--profile` переопределяет.

**Independent Test**: `--dry-run` на разных машинах даёт разный `--include=<conf>`; `--profile air-m1` форсирует выбор.

### Tests for User Story 2 ⚠️

- [X] T016 [P] [US2] `tests/unit/test_machine.py`: детекция класса (моки `platform.system`/`platform.machine`/`shutil.which`): Darwin+arm64→`air-m1`; Windows+есть nvidia-smi→`desktop-4070ti`; иначе→`generic`; явный `--profile` перекрывает авто
- [X] T017 [P] [US2] Дополнить `tests/unit/test_presets.py`: для профиля с существующим `.conf` в argv появляется `--include=<path>`; для отсутствующего `.conf` — `warnings` непуст и argv деградирует к `--profile=gpu-hq`

### Implementation for User Story 2

- [X] T018 [US2] Реализовать `detect()` и `resolve(profile_flag)` в `src/mpv_launcher/machine.py` (эвристика R3 + override; при неуверенности → `generic`)
- [X] T019 [US2] Расширить `presets.build_plan` в `src/mpv_launcher/presets.py`: по `MachineProfile.conf_file` добавлять `--include=<mpv-profiles/<name>.conf>`; если файла нет — `warnings` + базовый апскейл
- [X] T020 [US2] Добавить флаг `--profile {auto,desktop-4070ti,air-m1,generic}` (default `auto`) в `cli.parse` и прокинуть `machine.resolve` в основной поток `cli.main`

**Checkpoint US2**: корректный профиль выбирается автоматически и переопределяется флагом.

---

## Phase 5: User Story 3 — Пресеты контента (Priority: P3)

**Goal**: `--film` (default) и `--anime` дают разный апскейл; взаимоисключающи.

**Independent Test**: `--anime --dry-run` → `--profile=anime`; `--film --anime` → код 2.

### Tests for User Story 3 ⚠️

- [X] T021 [P] [US3] Дополнить `tests/unit/test_cli.py`: `--film` и `--anime` взаимоисключающи → код 2; без флага `content=="film"`; `--anime` → `content=="anime"`
- [X] T022 [P] [US3] Дополнить `tests/unit/test_presets.py`: `build_plan` добавляет `--profile=film` или `--profile=anime` согласно `Options.content`

### Implementation for User Story 3

- [X] T023 [US3] Добавить взаимоисключающую группу `--film`/`--anime` в `cli.parse` (→ `Options.content`, default `film`)
- [X] T024 [US3] Расширить `presets.build_plan`: подставлять `--profile=<content>` (имя mpv-профиля внутри `.conf`)
- [X] T025 [P] [US3] Создать `mpv-profiles/desktop-4070ti.conf` и `mpv-profiles/air-m1.conf` с секциями `[film]` и `[anime]` (FSRCNNX/Anime4K согласно классу машины) и `mpv-profiles/README.md` — куда класть файлы на каждой ОС и откуда взять шейдеры (FSRCNNX, Anime4K)

**Checkpoint US3**: кино и аниме дают разный собранный апскейл.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T026 [P] Реализовать HTTP-заголовки: флаги `--referer`, `--user-agent`, повторяемый `--header "Name: Value"` в `cli.parse`; сборка в `--http-header-fields="..."` в `presets.build_plan` (порядок: referer, user-agent, затем `--header`); опция отсутствует в argv, если заголовков нет. Тесты в `tests/unit/test_presets.py`
- [X] T027 [P] Добавить end-to-end `--dry-run` сценарии из quickstart.md в `tests/unit/test_cli.py` (US1/US2/US3/заголовки) как регрессионный набор
- [X] T028 [P] Заполнить раздел «Использование» в `README.md` (примеры из contracts/cli.md) и проверить соответствие quickstart.md
- [X] T029 Финальная сверка кодов выхода и stderr/stdout по `contracts/cli.md`; прогнать весь `pytest -q` зелёным

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Ph1)** → блокирует всё.
- **Foundational (Ph2)** → блокирует все user stories (структуры данных и коды выхода).
- **US1 (Ph3)** → MVP; не зависит от US2/US3.
- **US2 (Ph4)** и **US3 (Ph5)** → строятся поверх US1 (расширяют `presets.build_plan` и `cli.parse`), поэтому идут после US1; между собой US2 и US3 почти независимы, но обе трогают `presets.py`/`cli.py` → не параллелить их реализацию между собой.
- **Polish (Ph6)** → после профильных фаз.

### User Story Dependencies

- US1 — независима (MVP).
- US2 — логически после US1 (нужен рабочий поток «ссылка→mpv»).
- US3 — после US1; к US2 не привязана.

### Within Each User Story

Тесты (TDD) → реализация → checkpoint. Тесты в разных файлах помечены `[P]`.

### Parallel Opportunities

- Setup: T003 параллельно с T002 после T001.
- US1 тесты T006–T009 — все `[P]` (разные файлы), пишутся параллельно до реализации.
- US1 реализация: T010 и T011 `[P]` (разные модули); T012→T013→T014 последовательны (связаны потоком), T015 в конце.
- Между историями реализацию `presets.py`/`cli.py` не параллелить (общие файлы).

## Parallel Example: User Story 1

```text
# Тесты US1 (TDD) — запускаются вместе, должны падать:
T006 test_url.py   |  T007 test_clipboard.py  |  T008 test_runner.py  |  T009 test_cli.py

# Затем реализация, часть параллельно:
T010 url.py  ||  T011 clipboard.py   →   T012 presets.py → T013 runner.py → T014 cli.py → T015 __main__.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

Сделать Ph1 → Ph2 → Ph3. На выходе — рабочий `mpvplay "<url>"` с базовым апскейлом.
Это самостоятельный, демонстрируемый результат.

### Incremental Delivery

US1 (MVP) → US2 (профиль под железо) → US3 (пресеты кино/аниме) → Polish (заголовки, README, регрессия).
Каждая фаза оставляет проект в рабочем, тестируемом состоянии.

### Parallel Team Strategy

В рамках соло-разработки параллелятся в основном тесты и независимые модули (см. `[P]`).
Реализацию `presets.py`/`cli.py` держать последовательной — это общие точки сборки.

## Notes

- Тесты **мокают** `subprocess`, буфер обмена и детекцию железа — реальный mpv в CI не запускается.
- Файлы шейдеров в репозиторий не коммитятся; `mpv-profiles/README.md` объясняет, где их взять и куда положить.

## Task Summary

- **Всего задач**: 29 (T001–T029)
- **Setup**: 3 · **Foundational**: 2 · **US1**: 10 · **US2**: 5 · **US3**: 5 · **Polish**: 4
- **MVP scope**: T001–T015 (Setup + Foundational + US1)
