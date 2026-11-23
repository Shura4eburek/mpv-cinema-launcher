"""Шаги: состояния и отмена."""

import threading

import pytest

from mpv_launcher.progress import NO_PROGRESS, Cancelled, Progress


def _recorder():
    events = []
    return events, lambda step, state: events.append((step, state))


def test_step_reports_running_and_done():
    events, emit = _recorder()
    with Progress(emit).step("page"):
        pass
    assert events == [("page", "running"), ("page", "done")]


def test_step_reports_error_and_keeps_exception():
    events, emit = _recorder()
    with pytest.raises(ValueError):
        with Progress(emit).step("page"):
            raise ValueError()
    assert events == [("page", "running"), ("page", "error")]


def test_cancelled_is_not_an_error_step():
    flag = threading.Event()
    events, emit = _recorder()
    progress = Progress(emit, flag.is_set)
    with pytest.raises(Cancelled):
        with progress.step("stream"):
            flag.set()
            progress.check()
    assert events == [("stream", "running")]


def test_cancelled_step_does_not_start():
    events, emit = _recorder()
    with pytest.raises(Cancelled):
        with Progress(emit, lambda: True).step("page"):
            pytest.fail("шаг не должен начаться")
    assert events == []


def test_browser_flag_is_set_only_inside_browser_step():
    progress = Progress()
    assert progress.in_browser_step is False
    with progress.step("player", browser=True):
        assert progress.in_browser_step is True
    with progress.step("quality"):
        assert progress.in_browser_step is False
    assert progress.in_browser_step is False


def test_no_progress_is_silent():
    NO_PROGRESS.check()
    with NO_PROGRESS.step("page"):
        pass
