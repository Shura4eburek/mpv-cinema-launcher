"""T003: пакет импортируется и --help не падает (SystemExit 0)."""

import pytest

import mpv_launcher
from mpv_launcher import cli


def test_package_imports():
    assert mpv_launcher.__version__


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
