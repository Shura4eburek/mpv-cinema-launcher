# Quickstart — GUI-приложение

Детали — в [contracts/gui-and-packaging.md](./contracts/gui-and-packaging.md) и
[data-model.md](./data-model.md).

## Prerequisites

- Python 3.10+ и установленный mpv (как в 001).
- Для сборки: `python -m pip install -e ".[build]"` (ставит PyInstaller).

## Проверка логики без сборки

```bash
pytest -q                              # все юниты, включая 002 (моканы)

# ручной прогон GUI-логики из исходников (окно откроется, если ссылка в буфере):
#   скопировать .m3u8 в буфер, затем:
python -m mpv_launcher.__gui__         # или entry `mpvplay-gui`, если задан
```

Ожидаемо:
- пустой буфер → нативный диалог «скопируйте ссылку», код 3;
- mpv не в PATH, но установлен в типичном месте → всё равно находится и играет.

## Сборка macOS (.app + .dmg)

```bash
python -m pip install -e ".[build]"
bash build/build_macos.sh
# → dist/mpvplay.app  и  dist/mpvplay.dmg
open dist/mpvplay.app                   # двойной клик-эквивалент
```

## Сборка Windows (.exe) — на Windows-машине

```powershell
python -m pip install -e ".[build]"
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
# → dist\mpvplay\mpvplay.exe
```

## Валидация по user stories

- **US1**: скопировать `.m3u8` → запустить `.app`/`.exe` двойным кликом → mpv играет.
- **US2**: запустить с пустым буфером → диалог; убрать mpv → диалог с подсказкой.
- **US3**: артефакты запускаются на машине без Python (SC-004); профили находятся
  внутри бандла (SC-005 — проверяется тем, что апскейл применяется и в `.app`).
