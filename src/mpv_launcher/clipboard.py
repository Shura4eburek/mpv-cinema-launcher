"""Чтение и запись системного буфера обмена без внешних зависимостей."""

from __future__ import annotations

import platform
import subprocess


def _commands() -> list[list[str]]:
    """Платформенные команды чтения буфера (в порядке приоритета)."""
    system = platform.system()
    if system == "Darwin":
        return [["pbpaste"]]
    if system == "Windows":
        return [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
    # Linux / прочее — best effort
    return [
        ["wl-paste"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "-b"],
    ]


def read() -> str | None:
    """Первая непустая строка из буфера обмена, либо None."""
    for cmd in _commands():
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        for line in (result.stdout or "").splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    return None


def write(text: str) -> bool:
    """Записать строку в системный буфер обмена."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["clip"], input=text, text=True, check=True)
            return True
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
            return True
        if system == "Linux":
            for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
                try:
                    subprocess.run(cmd, input=text, text=True, check=True)
                    return True
                except Exception:
                    continue
    except Exception:
        pass
    return False
