"""Фоновые задачи backend: общий драйвер Selenium не потокобезопасен."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable


class Jobs:
    def __init__(self) -> None:
        self._selenium = ThreadPoolExecutor(max_workers=1, thread_name_prefix="selenium")
        self._io = ThreadPoolExecutor(max_workers=4, thread_name_prefix="io")
        self._play = ThreadPoolExecutor(max_workers=4, thread_name_prefix="play")

    def selenium(self, fn: Callable) -> Future:
        return self._selenium.submit(fn)

    def io(self, fn: Callable) -> Future:
        return self._io.submit(fn)

    def play(self, fn: Callable) -> Future:
        return self._play.submit(fn)

    def shutdown(self) -> None:
        for pool in (self._selenium, self._io, self._play):
            pool.shutdown(wait=False, cancel_futures=True)
