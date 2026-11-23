"""Поиск исполняемого mpv, в т.ч. при урезанном PATH (запуск из Finder/ярлыка)."""

from __future__ import annotations

import os
import platform
import shutil


def _candidates() -> list[str]:
    """Типичные места установки mpv по ОС."""
    system = platform.system()
    if system == "Darwin":
        return [
            "/opt/homebrew/bin/mpv",
            "/usr/local/bin/mpv",
            "/Applications/mpv.app/Contents/MacOS/mpv",
        ]
    if system == "Windows":
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        paths = [
            os.path.join(program_files, "mpv", "mpv.exe"),
            os.path.join(program_files, "MPV Player", "mpv.exe"),
            os.path.join(program_files, "mpv.net", "mpvnet.exe"),
            os.path.join(program_files_x86, "mpv", "mpv.exe"),
            os.path.join(program_files_x86, "MPV Player", "mpv.exe"),
        ]
        if local:
            paths.append(os.path.join(local, "Programs", "mpv", "mpv.exe"))
            paths.append(os.path.join(local, "Programs", "MPV Player", "mpv.exe"))
            paths.append(os.path.join(local, "Microsoft", "WinGet", "Links", "mpv.exe"))

        # Проверка реестра Windows (Uninstall / App Paths)
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            sub_key_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, sub_key_name) as sub_key:
                                try:
                                    name, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                                    if "mpv" in str(name).lower():
                                        loc, _ = winreg.QueryValueEx(sub_key, "InstallLocation")
                                        if loc:
                                            paths.append(os.path.join(loc, "mpv.exe"))
                                except OSError:
                                    pass
                except OSError:
                    pass
        except Exception:
            pass

        return paths
    return []


def find_mpv() -> str | None:
    """Путь к mpv: сначала PATH, затем типичные места. None, если не найден."""
    for name in ("mpv", "mpvnet"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in _candidates():
        if os.path.isfile(candidate):
            return candidate
    return None
