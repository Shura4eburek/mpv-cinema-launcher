"""Реальные шаги долгих операций и их отмена. Без получателя событий ничего не делает."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator


class Cancelled(Exception):
    """Пользователь отменил загрузку."""


class Progress:
    def __init__(
        self,
        emit: Callable[[str, str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self._emit = emit
        self._is_cancelled = is_cancelled
        self.in_browser_step = False

    def check(self) -> None:
        if self._is_cancelled is not None and self._is_cancelled():
            raise Cancelled()

    def _send(self, name: str, state: str) -> None:
        if self._emit is not None:
            self._emit(name, state)

    @contextmanager
    def step(self, name: str, browser: bool = False, retried: bool = False) -> Iterator[None]:
        """Шаг операции. ``browser`` отмечает работу в Chrome: её можно прервать, только закрыв его.

        ``retried``: при сбое шаг будет повторён другим способом, поэтому ошибка не показывается.
        """
        self.check()
        self._send(name, "running")
        self.in_browser_step = browser
        try:
            yield
        except Cancelled:
            raise
        except Exception:
            if not retried:
                self._send(name, "error")
            raise
        finally:
            self.in_browser_step = False
        self._send(name, "done")


NO_PROGRESS = Progress()
