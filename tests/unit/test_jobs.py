"""Очередь Selenium выполняется последовательно, остальные задачи её не ждут."""

import threading
import time

from mpv_launcher.jobs import Jobs


def test_selenium_jobs_run_strictly_in_order():
    jobs = Jobs()
    active = []
    overlaps = []
    order = []

    def work(n):
        active.append(n)
        overlaps.append(len(active))
        time.sleep(0.01)
        order.append(n)
        active.remove(n)

    futures = [jobs.selenium(lambda n=n: work(n)) for n in range(5)]
    for f in futures:
        f.result(timeout=5)
    jobs.shutdown()
    assert order == list(range(5))
    assert max(overlaps) == 1


def test_io_and_play_do_not_wait_for_selenium():
    jobs = Jobs()
    release = threading.Event()
    blocker = jobs.selenium(release.wait)
    try:
        assert jobs.io(lambda: "poster").result(timeout=2) == "poster"
        assert jobs.play(lambda: "mpv").result(timeout=2) == "mpv"
    finally:
        release.set()
    blocker.result(timeout=2)
    jobs.shutdown()


def test_long_playback_does_not_block_next_playback():
    jobs = Jobs()
    release = threading.Event()
    jobs.play(release.wait)
    try:
        assert jobs.play(lambda: 1).result(timeout=2) == 1
    finally:
        release.set()
    jobs.shutdown()
