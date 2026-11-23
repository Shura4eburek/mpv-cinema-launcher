"""Запуск без терминала: ссылка из буфера обмена открывается в mpv, ошибки — в диалоге.

Основной интерфейс приложения находится в каталоге ``app/`` (Tauri).
"""

from __future__ import annotations

import sys

from . import clipboard, dialog, locate, machine, presets, runner
from . import url as url_mod
from .cli import EXIT_NO_MPV, EXIT_NO_URL, Options

_NO_URL_MSG = (
    "В буфере обмена нет пригодной ссылки на поток (.m3u8).\n"
    "Скопируйте ссылку и запустите приложение снова."
)
_NO_MPV_MSG = (
    "Не найден плеер mpv.\n"
    "Установите mpv: macOS — «brew install mpv», Windows — «winget install mpv»."
)


def gui_main() -> int:
    """Буфер обмена → mpv."""
    raw = clipboard.read()
    if not url_mod.validate(raw):
        dialog.show_error(_NO_URL_MSG)
        return EXIT_NO_URL

    if locate.find_mpv() is None:
        dialog.show_error(_NO_MPV_MSG)
        return EXIT_NO_MPV

    options = Options(url=raw.strip(), profile="auto", content="film")
    plan = presets.build_plan(options, machine.resolve(options.profile))
    return runner.run(plan)


if __name__ == "__main__":
    sys.exit(gui_main())
