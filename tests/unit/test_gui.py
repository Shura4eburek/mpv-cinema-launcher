"""T007/T011 (002): GUI-поток (двойной клик), ошибки в диалог."""

from unittest import mock

from mpv_launcher import gui
from mpv_launcher.cli import EXIT_NO_MPV, EXIT_NO_URL, EXIT_OK


def test_happy_path_runs_mpv():
    with mock.patch.object(gui.clipboard, "read", return_value="https://h/x.m3u8"), \
        mock.patch.object(gui.locate, "find_mpv", return_value="/opt/homebrew/bin/mpv"), \
        mock.patch.object(gui.runner, "run", return_value=0) as run_mock, \
        mock.patch.object(gui.dialog, "show_error") as dlg:
        code = gui.gui_main()
    assert code == EXIT_OK
    run_mock.assert_called_once()
    dlg.assert_not_called()
    # план собран с пресетом film
    plan = run_mock.call_args.args[0]
    assert "--profile=film" in plan.mpv_args or "--profile=gpu-hq" in plan.mpv_args
    assert plan.mpv_args[-1] == "https://h/x.m3u8"


def test_empty_clipboard_shows_dialog():
    with mock.patch.object(gui.clipboard, "read", return_value=None), \
        mock.patch.object(gui.runner, "run") as run_mock, \
        mock.patch.object(gui.dialog, "show_error") as dlg:
        code = gui.gui_main()
    assert code == EXIT_NO_URL
    run_mock.assert_not_called()
    dlg.assert_called_once()


def test_missing_mpv_shows_dialog():
    with mock.patch.object(gui.clipboard, "read", return_value="https://h/x.m3u8"), \
        mock.patch.object(gui.locate, "find_mpv", return_value=None), \
        mock.patch.object(gui.runner, "run") as run_mock, \
        mock.patch.object(gui.dialog, "show_error") as dlg:
        code = gui.gui_main()
    assert code == EXIT_NO_MPV
    run_mock.assert_not_called()
    dlg.assert_called_once()
