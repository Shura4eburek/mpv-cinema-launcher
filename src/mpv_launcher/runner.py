"""Запуск mpv по собранному плану."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from . import locate
from .cli import EXIT_NO_MPV, EXIT_OK

# Код выхода mpv: ни один файл не удалось загрузить (пользовательский выход — 0).
MPV_EXIT_LOAD_FAILED = 2

_MPV_HINT = (
    "mpv не найден. Установите mpv: "
    "macOS — `brew install mpv`, Windows — `winget install mpv`."
)


def _player_binary(path: str) -> str:
    """mpv.com лишь запускает mpv.exe: закрыть такой запуск при отмене было бы нельзя."""
    candidate = Path(path)
    if candidate.suffix.lower() == ".com" and candidate.with_suffix(".exe").is_file():
        return str(candidate.with_suffix(".exe"))
    return path


def run_with_fallback(
    plan,
    fallback_urls=(),
    dry_run: bool = False,
    on_fallback=None,
    on_process=None,
    should_stop=None,
) -> int:
    """Запустить mpv, а если поток не загрузился — следующие зеркала по очереди."""
    code = run(plan, dry_run=dry_run, on_process=on_process)
    for url in fallback_urls:
        if code != MPV_EXIT_LOAD_FAILED or (should_stop is not None and should_stop()):
            break
        # В адресе потока есть токен, поэтому в журнал попадает только хост.
        print(f"Поток не загрузился, пробую зеркало: {urlparse(url).netloc}", file=sys.stderr)
        if on_fallback is not None:
            on_fallback(url)
        plan = replace(plan, mpv_args=[*plan.mpv_args[:-1], url], warnings=[])
        code = run(plan, dry_run=dry_run, on_process=on_process)
    return code


def run(plan, dry_run: bool = False, on_process=None) -> int:
    """Запустить mpv. При dry_run — напечатать команду и выйти.

    ``on_process`` получает запущенный процесс, чтобы запуск можно было отменить.
    """
    if dry_run:
        print(" ".join(plan.mpv_args))
        for warning in plan.warnings:
            print(warning, file=sys.stderr)
        return EXIT_OK

    mpv_path = locate.find_mpv()
    if mpv_path is None:
        print(_MPV_HINT, file=sys.stderr)
        return EXIT_NO_MPV

    for warning in plan.warnings:
        print(warning, file=sys.stderr)

    # plan.mpv_args[0] — литерал "mpv"; подставляем разрешённый путь.
    argv = [_player_binary(mpv_path), *plan.mpv_args[1:]]
    if on_process is not None:
        process = subprocess.Popen(argv)
        on_process(process)
        return process.wait()
    completed = subprocess.run(argv)
    return completed.returncode
