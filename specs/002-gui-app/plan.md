# Implementation Plan: GUI-приложение (двойной клик)

**Branch**: `002-gui-app` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-gui-app/spec.md`

## Summary

GUI-обёртка поверх пакета `mpv_launcher` (001): точка входа без аргументов берёт
ссылку из буфера, прогоняет её через ту же цепочку (валидация → профиль → пресет →
mpv) и показывает ошибки нативным диалогом ОС. Приложение упаковывается PyInstaller
в самодостаточный бандл (`.app`/`.dmg` на macOS, `.exe` на Windows), несёт внутри
mpv-профили и умеет находить mpv при урезанном PATH (запуск из Finder/ярлыка).

## Technical Context

**Language/Version**: Python 3.10+ (stdlib + PyInstaller для сборки)

**Primary Dependencies**: runtime — только stdlib (`ctypes`, `subprocess`, `platform`, `sys`); build-time — PyInstaller

**Storage**: N/A

**Testing**: pytest + `unittest.mock` (диалоги/поиск mpv/буфер — моканы; реальные окна и сборка не запускаются в тестах)

**Target Platform**: macOS (.app/.dmg) и Windows (.exe)

**Project Type**: single project — расширение CLI-утилиты до GUI-приложения

**Performance Goals**: от клика до старта mpv — несколько секунд (SC-001)

**Constraints**: без тяжёлых GUI-тулкитов; mpv не бандлится; работа при урезанном PATH; профили доступны во frozen-режиме

**Scale/Scope**: один пользователь; +4 небольших модуля, 2 PyInstaller-спека, 2 build-скрипта

## Constitution Check

Конституция — незаполненный шаблон, формальных гейтов нет. Добровольные принципы
соблюдены: переиспользование ядра 001 (no-dup), TDD для новой логики (mpv/диалоги/gui
моканы), stdlib-only в рантайме. Нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/002-gui-app/
├── plan.md · research.md · data-model.md · quickstart.md
└── contracts/
    └── gui-and-packaging.md
```

### Source Code (repository root)

```text
src/mpv_launcher/
├── locate.py        # find_mpv(): PATH + типичные места установки по ОС
├── dialog.py        # show_error(msg): osascript (macOS) / MessageBoxW (Windows) / stderr
├── gui.py           # gui_main(): буфер → валидация → профиль → run; ошибки в диалог
├── __gui__.py       # точка входа бандла: sys.exit(gui.gui_main())
├── presets.py       # [изменить] profiles_dir(): поддержка frozen (sys._MEIPASS)
└── runner.py        # [изменить] использовать locate.find_mpv() вместо shutil.which

packaging/
├── mpvplay-macos.spec      # PyInstaller: windowed .app, datas=mpv-profiles
└── mpvplay-windows.spec    # PyInstaller: windowed .exe, datas=mpv-profiles

build/
├── build_macos.sh          # pyinstaller + hdiutil → .dmg
└── build_windows.ps1       # pyinstaller → .exe (запускает пользователь)

tests/unit/
├── test_locate.py · test_dialog.py · test_gui.py
└── test_presets.py  # [дополнить] frozen-режим profiles_dir
```

**Structure Decision**: расширяем существующий пакет `mpv_launcher`, не создавая
второй. GUI — тонкий слой (`gui.py`) над уже протестированным ядром 001. Единственные
правки в коде 001 — точечные: `runner` теперь ищет mpv через `locate.find_mpv()`, а
`presets.profiles_dir()` понимает frozen-режим. Упаковка и build-скрипты изолированы
в `packaging/` и `build/`.

## Complexity Tracking

Нарушений Constitution Check нет — раздел не заполняется.
