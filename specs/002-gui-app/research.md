# Research — GUI-приложение (Phase 0)

## R1. Поиск mpv при урезанном PATH

- **Decision**: `locate.find_mpv()` — сперва `shutil.which("mpv")` (и `mpvnet` на
  Windows), затем список кандидатов по ОС:
  - macOS: `/opt/homebrew/bin/mpv`, `/usr/local/bin/mpv`, `/Applications/mpv.app/Contents/MacOS/mpv`;
  - Windows: `%PROGRAMFILES%\mpv\mpv.exe`, `%PROGRAMFILES%\mpv.net\mpvnet.exe`, `%LOCALAPPDATA%\Programs\mpv\mpv.exe`;
  - возвращает первый существующий путь или `None`.
- **Rationale**: GUI-приложение из Finder/ярлыка получает минимальный PATH без
  `/opt/homebrew/bin` — как мы и наблюдали вживую. Явные кандидаты закрывают реальные
  места установки.
- **Alternatives considered**: читать логин-шелл пользователя для полного PATH
  (хрупко, медленно); требовать mpv строго в PATH (ломает запуск из Finder).

## R2. Нативный диалог без GUI-фреймворка

- **Decision**: `dialog.show_error(message)` по ОС:
  - macOS: `osascript -e 'display dialog "<msg>" with title "mpvplay" buttons {"OK"} with icon stop'`;
  - Windows: `ctypes.windll.user32.MessageBoxW(0, msg, "mpvplay", 0x10)` (MB_ICONERROR);
  - прочее / недоступно: печать в stderr.
- **Rationale**: ноль зависимостей, нативный вид, работает во frozen-бандле.
  `tkinter` тянет Tcl/Tk в бандл и ненадёжен на свежих macOS.
- **Alternatives considered**: tkinter.messagebox (вес + хрупкость), pyobjc/win32ui
  (тяжёлые зависимости).

## R3. Доступ к профилям во frozen-режиме

- **Decision**: `presets.profiles_dir()`:
  1. env `MPV_LAUNCHER_PROFILES_DIR` (override) — как в 001;
  2. если `getattr(sys, "frozen", False)` → `Path(sys._MEIPASS) / "mpv-profiles"`;
  3. иначе → `repo/mpv-profiles` (как в 001).
- **Rationale**: PyInstaller распаковывает `datas` в `sys._MEIPASS`; onedir/onefile
  оба поддерживаются. Профили кладём в бандл через `datas` в .spec.
- **Alternatives considered**: читать профили как package-data через importlib
  (сложнее передавать mpv как файл на диске — mpv `--include` нужен путь).

## R4. Точка входа GUI (без терминала)

- **Decision**: модуль `__gui__.py` с `sys.exit(gui.gui_main())`; PyInstaller
  собирает его в `--windowed` режиме (нет консольного окна). `gui_main()` не парсит
  argv — всегда берёт ссылку из буфера; профиль `auto`, пресет `film` (умолчания).
- **Rationale**: соответствует сценарию «двойной клик». CLI (`mpvplay`) из 001
  остаётся для флагов.
- **Alternatives considered**: один общий entry, определяющий режим по argv/TTY
  (лишняя сложность; CLI и GUI лучше держать раздельно).

## R5. Упаковка PyInstaller

- **Decision**: два .spec в `packaging/`:
  - macOS: `BUNDLE` → `.app`, `console=False`, `datas=[('mpv-profiles','mpv-profiles')]`,
    `bundle_identifier='dev.mamoru.mpvplay'`; затем `hdiutil create` → `.dmg`.
  - Windows: `EXE` (onedir по умолчанию ради скорости старта), `console=False`,
    те же `datas`.
  - build-скрипты `build/build_macos.sh` и `build/build_windows.ps1`.
- **Rationale**: .spec фиксирует datas/windowed/identifier воспроизводимо; onedir
  быстрее onefile и проще для datas.
- **Alternatives considered**: onefile .exe (медленный старт, распаковка во temp);
  py2app (только macOS, второй инструмент).
- **Note**: кросс-сборка невозможна — `.exe` собирает пользователь на Windows.

## R6. Переиспользование ядра 001

- **Decision**: `gui_main()` зовёт `clipboard.read` → `url.validate` →
  `machine.resolve("auto")` → `presets.build_plan(options, profile)` →
  `runner.run(plan)`. Options берётся из `cli.Options` с умолчаниями. Ошибки от
  `runner` (нет mpv) и пустой/битый буфер транслируются в `dialog.show_error`.
- **Rationale**: ни строки дублирования логики; GUI — только «обвязка» ввода/вывода.

## Resolved clarifications

Открытых `NEEDS CLARIFICATION` нет. Выбор «аниме» в GUI — сознательно вне MVP
(Assumptions спеки), поэтому пресет жёстко `film` в gui_main на этом этапе.
