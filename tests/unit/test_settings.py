"""Настройки: значения по умолчанию, проверка полей, повреждённый файл, атомарная запись."""

import json

import pytest

from mpv_launcher import settings


def test_defaults_when_file_missing(tmp_path):
    assert settings.load(tmp_path / "settings.json") == settings.DEFAULTS


def test_lampac_is_off_by_default_and_validated(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.load(path)["lampac_enabled"] is False
    assert settings.update({"lampac_enabled": True}, path)["lampac_enabled"] is True
    with pytest.raises(ValueError):
        settings.update({"lampac_enabled": "да"}, path)


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    settings.update({"content": "anime", "interpolation": False}, path)
    loaded = settings.load(path)
    assert loaded["content"] == "anime"
    assert loaded["interpolation"] is False
    assert loaded["preset"] == "auto"


@pytest.mark.parametrize(
    ("old", "preset"),
    [
        ({"upscale_quality": "basic", "profile": "desktop-4070ti"}, "low"),
        ({"upscale_quality": "max", "profile": "desktop-4070ti"}, "high"),
        ({"upscale_quality": "balanced", "profile": "air-m1"}, "mid"),
        ({"profile": "generic"}, "low"),
        ({"upscale_quality": "max", "profile": "auto"}, "auto"),
        ({}, "auto"),
    ],
)
def test_previous_settings_move_to_nearest_preset(tmp_path, old, preset):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    loaded = settings.load(path)
    assert loaded["preset"] == preset
    assert "upscale_quality" not in loaded and "profile" not in loaded


def test_saved_preset_wins_over_previous_fields(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"preset": "mid", "upscale_quality": "basic"}), encoding="utf-8")
    assert settings.load(path)["preset"] == "mid"


def test_invalid_preset_becomes_auto(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"preset": "ultra"}), encoding="utf-8")
    assert settings.load(path)["preset"] == "auto"


def test_each_field_is_validated_separately(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"content": "anime", "interpolation": "yes", "preset": "x", "last_quality": 5}),
        encoding="utf-8",
    )
    loaded = settings.load(path)
    assert loaded["content"] == "anime"
    assert loaded["interpolation"] is True
    assert loaded["preset"] == "auto"
    assert loaded["last_quality"] is None


@pytest.mark.parametrize("raw", ["{broken", "[]", "null", ""])
def test_corrupted_file_gives_defaults_and_is_not_overwritten(tmp_path, raw):
    path = tmp_path / "settings.json"
    path.write_text(raw, encoding="utf-8")
    assert settings.load(path) == settings.DEFAULTS
    assert path.read_text(encoding="utf-8") == raw


def test_kinogo_url_accepts_only_http_addresses(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.update({"kinogo_url": "https://kinogo.example"}, path)["kinogo_url"] == "https://kinogo.example"
    for bad in ("file:///x", "kinogo.example", "", None):
        with pytest.raises(ValueError):
            settings.update({"kinogo_url": bad}, path)
    path.write_text(json.dumps({"kinogo_url": "javascript:alert(1)"}), encoding="utf-8")
    assert settings.load(path)["kinogo_url"] == settings.DEFAULTS["kinogo_url"]


def test_update_rejects_invalid_value_and_unknown_field(tmp_path):
    path = tmp_path / "settings.json"
    with pytest.raises(ValueError):
        settings.update({"preset": "ultra"}, path)
    with pytest.raises(ValueError):
        settings.update({"unknown": 1}, path)
    assert not path.exists()


def test_write_is_atomic_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    settings.update({"content": "anime"}, path)

    def fail(*_):
        raise OSError("disk")

    monkeypatch.setattr(settings.os, "replace", fail)
    with pytest.raises(OSError):
        settings.update({"content": "film"}, path)
    assert settings.load(path)["content"] == "anime"
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_embedded_player_is_off_by_default_and_must_be_boolean(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.load(path)["embedded_player"] is False
    assert settings.update({"embedded_player": True}, path)["embedded_player"] is True
    with pytest.raises(ValueError):
        settings.update({"embedded_player": "да"}, path)
