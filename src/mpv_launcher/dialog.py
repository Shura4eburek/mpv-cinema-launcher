"""Нативный диалог с сообщением об ошибке (без GUI-фреймворков)."""

from __future__ import annotations

import ctypes
import platform
import subprocess
import sys

_TITLE = "mpvplay"


def _applescript_quote(text: str) -> str:
    """Экранировать строку для литерала AppleScript."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def show_error(message: str) -> None:
    """Показать модальное окно с ошибкой. Никогда не бросает исключений."""
    system = platform.system()
    try:
        if system == "Darwin":
            script = (
                f"display dialog {_applescript_quote(message)} "
                f'with title "{_TITLE}" buttons {{"OK"}} '
                f'default button "OK" with icon stop'
            )
            subprocess.run(["osascript", "-e", script], check=False)
            return
        if system == "Windows":
            # MB_OK | MB_ICONERROR = 0x10
            ctypes.windll.user32.MessageBoxW(0, message, _TITLE, 0x10)
            return
    except Exception:
        pass
    print(f"{_TITLE}: {message}", file=sys.stderr)
