"""Шейдеры: докачка недостающего и честный результат."""

import io
import zipfile
from types import SimpleNamespace
from unittest import mock

import pytest
import requests

from mpv_launcher import shaders


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(shaders, "_repo_dir", lambda: None)
    return tmp_path / "appdata" / "mpv" / "shaders"


def _zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in shaders.ANIME4K_REQUIRED:
            archive.writestr(f"pack/{name}", "shader")
    return buffer.getvalue()


def _ok(content=b"shader"):
    return SimpleNamespace(content=content, raise_for_status=lambda: None)


def _http_error():
    def fail():
        raise requests.HTTPError("404")

    return SimpleNamespace(content=b"", raise_for_status=fail)


def _fake_get(url, timeout):
    return _ok(_zip_bytes()) if url == shaders.ANIME4K_URL else _ok()


def test_installs_every_required_file(config):
    with mock.patch.object(shaders.requests, "get", side_effect=_fake_get):
        assert shaders.ensure_shaders_installed() is True
    assert all((config / name).is_file() for name in shaders._required_files())
    assert not list(config.glob("*.tmp"))


def test_partial_install_is_not_ready_and_only_missing_are_downloaded(config):
    config.mkdir(parents=True)
    (config / "FSRCNNX_x2_16-0-4-1.glsl").write_text("shader")
    assert shaders.are_shaders_installed() is False

    with mock.patch.object(shaders.requests, "get", side_effect=_fake_get) as get:
        assert shaders.ensure_shaders_installed() is True
    assert shaders.FSRCNNX_URLS["FSRCNNX_x2_16-0-4-1.glsl"] not in [c.args[0] for c in get.call_args_list]


def test_http_error_is_reported_as_failure(config):
    with mock.patch.object(shaders.requests, "get", return_value=_http_error()):
        assert shaders.ensure_shaders_installed() is False


def test_uses_home_config_when_appdata_is_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(shaders, "_repo_dir", lambda: None)
    with mock.patch.object(shaders.requests, "get", side_effect=_fake_get):
        assert shaders.ensure_shaders_installed() is True
    assert (tmp_path / ".config" / "mpv" / "shaders" / "KrigBilateral.glsl").is_file()
