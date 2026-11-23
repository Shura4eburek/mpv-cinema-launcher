# Data Model — GUI-приложение (Phase 1)

Новых персистентных сущностей нет. Описаны внутренние понятия и изменения в
существующих функциях.

## find_mpv() → str | None

Разрешение пути к mpv.

| Шаг | Источник | Результат |
|-----|----------|-----------|
| 1 | `shutil.which("mpv")` / `shutil.which("mpvnet")` | путь, если есть в PATH |
| 2 | список кандидатов по ОС (см. research R1) | первый существующий файл |
| 3 | ничего не найдено | `None` |

## show_error(message: str) -> None

Выбор механизма по `platform.system()`:

| ОС | Механизм |
|----|----------|
| Darwin | `osascript -e 'display dialog ...'` |
| Windows | `ctypes ... MessageBoxW(..., MB_ICONERROR)` |
| прочее | печать в stderr |

Не бросает исключений наружу: если механизм недоступен — тихий фолбэк в stderr.

## profiles_dir() — изменение (из 001)

| Приоритет | Условие | Каталог |
|-----------|---------|---------|
| 1 | env `MPV_LAUNCHER_PROFILES_DIR` задан | значение env |
| 2 | `sys.frozen` истинно | `Path(sys._MEIPASS)/"mpv-profiles"` |
| 3 | иначе | `repo/mpv-profiles` (как в 001) |

## runner.run() — изменение (из 001)

Проверка наличия mpv теперь через `locate.find_mpv()` (не голый `shutil.which`).
Если `None` → код `EXIT_NO_MPV` (4) + сообщение (CLI: stderr; GUI транслирует в диалог).
Найденный путь подставляется первым элементом argv вместо литерала `"mpv"`.

## Поток данных GUI (happy path)

```text
двойной клик ─▶ __gui__.main ─▶ gui.gui_main()
     clipboard.read() ─▶ url.validate()  ──(невалидно)──▶ dialog.show_error → exit 3
            │(валидно)
            ▼
   machine.resolve("auto") ─▶ presets.build_plan(Options(content="film"), profile)
            ▼
   runner.run(plan)  ──(mpv не найден)──▶ (код 4) ─▶ dialog.show_error → exit 4
            │(ок)
            ▼
         mpv играет
```
