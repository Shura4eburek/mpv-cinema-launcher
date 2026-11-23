"""Настройки пользователя: JSON в каталоге приложения, запись атомарна."""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path

from . import url as url_mod

APP_NAME = "mpv-cinema-launcher"

DEFAULTS: dict = {
    "version": 1,
    "preset": "auto",
    "content": "film",
    "interpolation": True,
    "last_translator": None,
    "last_quality": None,
    "kinogo_url": "https://uakinogo.io",
    "lampac_enabled": False,
    "embedded_player": False,
}

_CHOICES = {
    "preset": ("auto", "high", "mid", "low"),
    "content": ("film", "anime"),
}
_OPTIONAL_TEXT = ("last_translator", "last_quality")


def _is_valid(key: str, value) -> bool:
    if key in _CHOICES:
        return value in _CHOICES[key]
    if key in ("interpolation", "lampac_enabled", "embedded_player"):
        return isinstance(value, bool)
    if key in _OPTIONAL_TEXT:
        return value is None or isinstance(value, str)
    if key == "kinogo_url":
        return isinstance(value, str) and url_mod.validate(value)
    return False


def _migrated_preset(raw: dict) -> str:
    """Ближайший пресет для настроек прежней версии."""
    if raw.get("upscale_quality") == "basic":
        return "low"
    return {"desktop-4070ti": "high", "air-m1": "mid", "generic": "low"}.get(raw.get("profile"), "auto")


def data_dir() -> Path:
    """Каталог настроек пользователя."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME


def cache_dir() -> Path:
    """Каталог кэша (постеры)."""
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    return data_dir()


def default_path() -> Path:
    return data_dir() / "settings.json"


def account_path() -> Path:
    """Профиль Google-аккаунта для показа без сети (без секретов)."""
    return data_dir() / "account.json"


def avatar_path() -> Path:
    return cache_dir() / "avatar.jpg"


def load(path: Path | None = None) -> dict:
    """Прочитать настройки. Ошибки чтения и неверные поля заменяются значениями по умолчанию."""
    result = dict(DEFAULTS)
    try:
        raw = json.loads(Path(path or default_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        if key != "version" and _is_valid(key, value):
            result[key] = value
    if "preset" not in raw:
        result["preset"] = _migrated_preset(raw)
    return result


def update(changes: dict, path: Path | None = None) -> dict:
    """Проверить изменения и атомарно сохранить. ValueError при неверных данных."""
    for key, value in changes.items():
        if not _is_valid(key, value):
            raise ValueError(f"Недопустимая настройка: {key}")

    target = Path(path or default_path())
    result = {**load(target), **changes}
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return result
