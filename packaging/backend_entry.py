"""Точка входа PyInstaller для backend (абсолютный импорт, не relative-as-main)."""

import sys

from mpv_launcher.backend import serve

if __name__ == "__main__":
    sys.exit(serve())
