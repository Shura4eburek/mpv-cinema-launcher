# Implementation Plan: mpv HLS Launcher

**Branch**: `001-mpv-hls-launcher` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-mpv-hls-launcher/spec.md`

## Summary

CLI-лаунчер, который берёт HLS-ссылку (аргумент или буфер обмена), собирает набор
аргументов mpv под класс текущей машины и выбранный пресет контента, и запускает
mpv. Логика выбора профиля/пресета и сборки команды отделена от собственно запуска
плеера и от mpv-конфигов апскейла — это делает ядро чисто юнит-тестируемым (mpv
мокается), а визуальные настройки живут в отдельных mpv-профилях.

## Technical Context

**Language/Version**: Python 3.10+ (stdlib-only; целевой рантайм — системный Python на macOS, Python из python.org / Store на Windows)

**Primary Dependencies**: только стандартная библиотека (`argparse`, `subprocess`, `shutil`, `platform`, `sys`, `os`, `pathlib`). Никаких pip-зависимостей.

**Storage**: N/A (состояние не хранится; читается внешний mpv-конфиг из стандартного каталога mpv)

**Testing**: `pytest` (dev-зависимость) + `unittest.mock` для подмены `subprocess`/clipboard/детекции железа

**Target Platform**: macOS (Apple Silicon) и Windows 10/11; Linux архитектурно не исключён, но вне явного scope

**Project Type**: single project — CLI-утилита

**Performance Goals**: холодный старт лаунчера до вызова mpv — ощутимо «мгновенный» (< ~300 мс); сам апскейл — забота mpv/GPU, не лаунчера

**Constraints**: без внешних runtime-зависимостей; не качать и не ставить шейдеры; не искать ссылки и не обходить блокировки; предсказуемое поведение при отсутствии mpv/шейдеров

**Scale/Scope**: один пользователь, разовые запуски; ~5–7 небольших модулей, покрытых юнит-тестами

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Проектная конституция (`.specify/memory/constitution.md`) — незаполненный шаблон, ратифицированных принципов нет, поэтому формальных гейтов нет. Тем не менее проект добровольно следует здравым принципам, совместимым с духом шаблона spec-kit:

- **CLI-интерфейс**: функциональность доступна через CLI; stdin/args → stdout, ошибки → stderr; осмысленные коды выхода. ✅
- **Test-First**: ядро (парсинг, валидация, выбор профиля/пресета, сборка команды) пишется по TDD, mpv мокается. ✅
- **Simplicity / YAGNI**: stdlib-only, один проект, без лишних абстракций. ✅

Нарушений нет → Complexity Tracking не заполняется.

## Project Structure

### Documentation (this feature)

```text
specs/001-mpv-hls-launcher/
├── plan.md              # Этот файл
├── research.md          # Phase 0 — решения и обоснования
├── data-model.md        # Phase 1 — сущности и правила
├── quickstart.md        # Phase 1 — как запустить и проверить
├── contracts/
│   └── cli.md           # Phase 1 — контракт CLI (флаги, коды выхода, поведение)
└── tasks.md             # Phase 2 — создаётся командой /speckit-tasks
```

### Source Code (repository root)

```text
src/
└── mpv_launcher/
    ├── __init__.py
    ├── __main__.py      # точка входа: python -m mpv_launcher
    ├── cli.py           # разбор аргументов (argparse) → Options
    ├── clipboard.py     # чтение буфера обмена под ОС (pbpaste / powershell Get-Clipboard)
    ├── url.py           # валидация ссылки (http(s), похоже на HLS/.m3u8)
    ├── machine.py       # детекция класса машины (desktop-nvidia / air-m1 / generic)
    ├── presets.py       # профиль машины + пресет контента → список аргументов mpv
    └── runner.py        # сборка итоговой команды mpv + запуск (subprocess)

mpv-profiles/            # mpv-конфиги апскейла (визуальные настройки, вне кода)
├── README.md            # как разложить по машинам + где взять шейдеры
├── desktop-4070ti.conf  # тяжёлый профиль (FSRCNNX x2_16, Anime4K HQ)
└── air-m1.conf          # облегчённый профиль (FSRCNNX x2_8 / ewa_lanczossharp)

tests/
└── unit/
    ├── test_cli.py
    ├── test_url.py
    ├── test_machine.py
    ├── test_presets.py
    └── test_runner.py

pyproject.toml           # метаданные пакета + dev-зависимость pytest + console-script `mpvplay`
```

**Structure Decision**: Single project. Код — маленький stdlib-пакет `mpv_launcher` с
чётким разделением на тестируемые юниты (парсинг/валидация/детекция/сборка команды) и
тонкий слой запуска (`runner.py`), который единственный реально трогает `subprocess` и
поэтому мокается в тестах. Визуальные настройки апскейла вынесены в `mpv-profiles/*.conf`
(данные, не код), что позволяет менять качество без правок логики. Шейдеры в репозиторий
не кладутся — профили ссылаются на стандартный каталог mpv, а `README.md` объясняет,
откуда их взять.

## Complexity Tracking

> Нарушений Constitution Check нет — раздел не заполняется.
