"""Автоматическая проверка и загрузка шейдеров апскейла (FSRCNNX, Anime4K)."""

from __future__ import annotations

import io
import os
import sys
import zipfile

import requests

FSRCNNX_URLS = {
    "FSRCNNX_x2_16-0-4-1.glsl": "https://github.com/igv/FSRCNN-TensorFlow/releases/download/1.1/FSRCNNX_x2_16-0-4-1.glsl",
    "FSRCNNX_x2_8-0-4-1.glsl": "https://github.com/igv/FSRCNN-TensorFlow/releases/download/1.1/FSRCNNX_x2_8-0-4-1.glsl",
    "KrigBilateral.glsl": "https://gist.githubusercontent.com/igv/a015fc885d5c22e6891820ad89555637/raw/d7f39734d6aff4c0989f32a4530b1b010e64bda3/KrigBilateral.glsl",
}
ANIME4K_URL = "https://github.com/bloc97/Anime4K/releases/download/v4.0.1/Anime4K_v4.0.zip"

# Файлы Anime4K, на которые ссылаются профили в mpv-profiles/*.conf.
ANIME4K_REQUIRED = (
    "Anime4K_Clamp_Highlights.glsl",
    "Anime4K_Restore_CNN_VL.glsl",
    "Anime4K_Restore_CNN_M.glsl",
    "Anime4K_Upscale_CNN_x2_VL.glsl",
    "Anime4K_Upscale_CNN_x2_M.glsl",
    "Anime4K_AutoDownscalePre_x2.glsl",
)


def _config_dir() -> str:
    """Каталог шейдеров mpv (~~/shaders/) на этой системе."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "mpv", "shaders")
    return os.path.join(os.path.expanduser("~"), ".config", "mpv", "shaders")


def _repo_dir() -> str | None:
    # В собранном приложении каталога репозитория нет, а папка установки может быть только для чтения.
    if getattr(sys, "frozen", False):
        return None
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "mpv-profiles", "shaders"))


def get_shaders_dirs() -> list[str]:
    return [d for d in (_config_dir(), _repo_dir()) if d]


def _required_files() -> list[str]:
    return [*FSRCNNX_URLS, *ANIME4K_REQUIRED]


def are_shaders_installed() -> bool:
    """Все ли файлы, на которые ссылаются профили, есть в каталоге конфигурации mpv."""
    target = _config_dir()
    return all(os.path.isfile(os.path.join(target, name)) for name in _required_files())


def _write(directories: list[str], name: str, content: bytes) -> None:
    for directory in directories:
        path = os.path.join(directory, name)
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as handle:
            handle.write(content)
        os.replace(tmp, path)  # прерванная загрузка не оставит обрезанный шейдер


def _download_fsrcnnx(directories: list[str]) -> bool:
    success = True
    for name, url in FSRCNNX_URLS.items():
        if os.path.isfile(os.path.join(directories[0], name)):
            continue
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            _write(directories, name, response.content)
        except (requests.RequestException, OSError):
            success = False
    return success


def _download_anime4k(directories: list[str]) -> bool:
    if all(os.path.isfile(os.path.join(directories[0], name)) for name in ANIME4K_REQUIRED):
        return True
    try:
        response = requests.get(ANIME4K_URL, timeout=25)
        response.raise_for_status()
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        for member in archive.namelist():
            if member.endswith(".glsl"):
                _write(directories, os.path.basename(member), archive.read(member))
    except (requests.RequestException, OSError, zipfile.BadZipFile):
        return False
    return True


def ensure_shaders_installed() -> bool:
    """Докачать недостающие шейдеры. True, только если в итоге есть все нужные файлы."""
    if are_shaders_installed():
        return True

    directories = get_shaders_dirs()
    try:
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    except OSError:
        return False

    _download_fsrcnnx(directories)
    _download_anime4k(directories)
    return are_shaders_installed()
