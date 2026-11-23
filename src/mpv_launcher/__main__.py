"""Точка входа `python -m mpv_launcher`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
