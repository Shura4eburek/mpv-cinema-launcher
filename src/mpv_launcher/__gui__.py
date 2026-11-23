"""Запуск GUI как модуля: python -m mpv_launcher.__gui__."""

import sys

from .gui import gui_main

if __name__ == "__main__":
    sys.exit(gui_main())
