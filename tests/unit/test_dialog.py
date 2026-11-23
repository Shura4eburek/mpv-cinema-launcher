"""T010 (002): нативный диалог по ОС (без реальных окон)."""

from unittest import mock

from mpv_launcher import dialog


def test_macos_uses_osascript():
    captured = {}

    def _run(cmd, **kwargs):
        captured["cmd"] = cmd

    with mock.patch.object(dialog.platform, "system", return_value="Darwin"), \
        mock.patch.object(dialog.subprocess, "run", side_effect=_run):
        dialog.show_error("бум")
    assert captured["cmd"][0] == "osascript"
    assert "бум" in captured["cmd"][-1]


def test_windows_uses_messagebox():
    fake_ctypes = mock.MagicMock()
    with mock.patch.object(dialog.platform, "system", return_value="Windows"), \
        mock.patch.object(dialog, "ctypes", fake_ctypes):
        dialog.show_error("бум")
    fake_ctypes.windll.user32.MessageBoxW.assert_called_once()
    args = fake_ctypes.windll.user32.MessageBoxW.call_args.args
    assert "бум" in args


def test_other_os_falls_back_to_stderr(capsys):
    with mock.patch.object(dialog.platform, "system", return_value="Linux"):
        dialog.show_error("бум")
    assert "бум" in capsys.readouterr().err


def test_mechanism_error_does_not_raise(capsys):
    with mock.patch.object(dialog.platform, "system", return_value="Darwin"), \
        mock.patch.object(dialog.subprocess, "run", side_effect=OSError("no osascript")):
        dialog.show_error("бум")  # не должно бросить
    assert "бум" in capsys.readouterr().err
