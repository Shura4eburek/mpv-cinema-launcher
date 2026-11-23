"""T009 [US1] / T021 [US3] / T027: разбор аргументов и главный поток."""

from unittest import mock

import pytest

from mpv_launcher import cli


# --- parse ---------------------------------------------------------------

def test_parse_positional_url_defaults():
    opts = cli.parse(["https://h/x"])
    assert opts.url == "https://h/x"
    assert opts.content == "film"
    assert opts.profile == "auto"
    assert opts.dry_run is False


def test_parse_anime():
    assert cli.parse(["--anime", "https://h/x"]).content == "anime"


def test_film_and_anime_mutually_exclusive():
    with pytest.raises(SystemExit) as exc:
        cli.parse(["--film", "--anime", "https://h/x"])
    assert exc.value.code == cli.EXIT_ARGS  # 2


def test_bad_profile_value_is_args_error():
    with pytest.raises(SystemExit) as exc:
        cli.parse(["--profile", "nonsense", "https://h/x"])
    assert exc.value.code == cli.EXIT_ARGS


# --- main flow -----------------------------------------------------------

def test_arg_url_beats_clipboard(capsys):
    with mock.patch("mpv_launcher.clipboard.read") as clip:
        code = cli.main(["https://arg/x.m3u8", "--dry-run", "--profile", "generic"])
    assert code == cli.EXIT_OK
    clip.assert_not_called()
    assert "https://arg/x.m3u8" in capsys.readouterr().out


def test_url_from_clipboard(capsys):
    with mock.patch("mpv_launcher.clipboard.read", return_value="https://clip/x.m3u8"):
        code = cli.main(["--dry-run", "--profile", "generic"])
    assert code == cli.EXIT_OK
    assert "https://clip/x.m3u8" in capsys.readouterr().out


def test_no_url_anywhere_returns_exit_no_url(capsys):
    with mock.patch("mpv_launcher.clipboard.read", return_value=None):
        code = cli.main(["--profile", "generic"])
    assert code == cli.EXIT_NO_URL
    assert "ссылка" in capsys.readouterr().err.lower()


def test_headers_end_to_end(capsys):
    code = cli.main([
        "https://h/x", "--dry-run", "--profile", "generic",
        "--referer", "https://r/", "--user-agent", "UA",
    ])
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "--http-header-fields=Referer: https://r/,User-Agent: UA" in out


def test_anime_profile_end_to_end(capsys):
    # Использует реальный mpv-profiles/air-m1.conf из репозитория.
    code = cli.main(["https://h/x", "--anime", "--profile", "air-m1", "--dry-run"])
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "--profile=anime" in out
    assert "air-m1.conf" in out
