"""T007 [US1]: чтение буфера обмена с моками."""

from types import SimpleNamespace
from unittest import mock

from mpv_launcher import clipboard


def _fake_run(stdout, returncode=0):
    def _run(cmd, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    return _run


def test_reads_first_nonempty_line():
    with mock.patch.object(clipboard.platform, "system", return_value="Darwin"), \
        mock.patch.object(clipboard.subprocess, "run",
                          side_effect=_fake_run("\n  https://host/x  \nsecond\n")):
        assert clipboard.read() == "https://host/x"


def test_empty_clipboard_returns_none():
    with mock.patch.object(clipboard.platform, "system", return_value="Darwin"), \
        mock.patch.object(clipboard.subprocess, "run", side_effect=_fake_run("   \n\n")):
        assert clipboard.read() is None


def test_windows_uses_powershell():
    captured = {}

    def _run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="https://host/x")

    with mock.patch.object(clipboard.platform, "system", return_value="Windows"), \
        mock.patch.object(clipboard.subprocess, "run", side_effect=_run):
        clipboard.read()
    assert captured["cmd"][0] == "powershell"
    assert "Get-Clipboard" in captured["cmd"]


def test_macos_uses_pbpaste():
    captured = {}

    def _run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="https://host/x")

    with mock.patch.object(clipboard.platform, "system", return_value="Darwin"), \
        mock.patch.object(clipboard.subprocess, "run", side_effect=_run):
        clipboard.read()
    assert captured["cmd"] == ["pbpaste"]
