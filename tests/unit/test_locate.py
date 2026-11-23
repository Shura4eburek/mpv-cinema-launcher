"""T002 (002): поиск mpv в PATH и типичных местах."""

from unittest import mock

from mpv_launcher import locate


def test_found_in_path_wins():
    with mock.patch.object(locate.shutil, "which",
                           side_effect=lambda n: "/usr/bin/mpv" if n == "mpv" else None):
        assert locate.find_mpv() == "/usr/bin/mpv"


def test_falls_back_to_candidate_when_not_in_path():
    with mock.patch.object(locate.shutil, "which", return_value=None), \
        mock.patch.object(locate.platform, "system", return_value="Darwin"), \
        mock.patch.object(locate.os.path, "isfile",
                          side_effect=lambda p: p == "/opt/homebrew/bin/mpv"):
        assert locate.find_mpv() == "/opt/homebrew/bin/mpv"


def test_returns_none_when_nothing_found():
    with mock.patch.object(locate.shutil, "which", return_value=None), \
        mock.patch.object(locate.platform, "system", return_value="Darwin"), \
        mock.patch.object(locate.os.path, "isfile", return_value=False):
        assert locate.find_mpv() is None


def test_mpvnet_in_path_is_accepted():
    with mock.patch.object(locate.shutil, "which",
                           side_effect=lambda n: r"C:\mpv.net\mpvnet.exe" if n == "mpvnet" else None):
        assert locate.find_mpv() == r"C:\mpv.net\mpvnet.exe"
