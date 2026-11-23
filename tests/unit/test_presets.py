"""T017 [US2] / T022 [US3] / T026: сборка команды mpv."""

from mpv_launcher import presets
from mpv_launcher.cli import Options


def test_generic_uses_builtin_upscale():
    plan = presets.build_plan(Options(url="https://h/x"), "generic")
    assert plan.mpv_args[:2] == ["mpv", "--profile=gpu-hq"]
    assert plan.mpv_args[-1] == "https://h/x"
    assert plan.warnings == []


def test_player_interface_args_and_title():
    plan = presets.build_plan(Options(url="https://h/x", title="Довод"), "generic")
    base = presets.profiles_dir() / "player"
    assert "--force-media-title=Довод" in plan.mpv_args
    assert "--no-osc" in plan.mpv_args
    assert f"--script={base / 'uosc'}" in plan.mpv_args
    assert f"--script={base / 'cinema.lua'}" in plan.mpv_args
    assert f"--osd-fonts-dir={base / 'fonts'}" in plan.mpv_args
    assert "--script-opts-append=uosc-languages=ru" in plan.mpv_args
    controls = [a for a in plan.mpv_args if a.startswith("--script-opts-append=uosc-controls=")]
    assert len(controls) == 1 and "picture-menu" in controls[0] and "play-pause" in controls[0]
    assert "--cursor-autohide=3000" in plan.mpv_args
    assert "--script-opts-append=uosc-autohide=yes" in plan.mpv_args
    assert plan.mpv_args[-1] == "https://h/x"


def test_ready_file_is_passed_to_player_script():
    plan = presets.build_plan(Options(url="https://h/x", ready_file="C:/tmp/ready"), "generic")
    assert "--script-opts-append=cinema-ready_file=C:/tmp/ready" in plan.mpv_args
    plain = presets.build_plan(Options(url="https://h/x"), "generic")
    assert not any("ready_file" in a for a in plain.mpv_args)
    assert plan.mpv_args[-1] == "https://h/x"


def test_title_defaults_to_link_caption():
    plan = presets.build_plan(Options(url="https://h/x"), "generic")
    assert f"--force-media-title={presets.DEFAULT_TITLE}" in plan.mpv_args


def test_missing_player_dir_warns_and_skips_interface_args(tmp_path):
    plan = presets.build_plan(Options(url="https://h/x"), "generic", conf_dir=tmp_path)
    assert not any(a.startswith(("--script", "--no-osc", "--osd-fonts-dir")) for a in plan.mpv_args)
    assert plan.warnings and "интерфейс плеера" in plan.warnings[-1]
    assert plan.mpv_args[-1] == "https://h/x"


def test_hls_never_falls_back_to_playlist_demuxer():
    plan = presets.build_plan(Options(url="https://h/x"), "generic")
    assert "--demuxer=lavf" in plan.mpv_args
    assert "--network-timeout=10" in plan.mpv_args


def test_url_is_always_last():
    plan = presets.build_plan(Options(url="https://h/x", referer="https://r/"), "generic")
    assert plan.mpv_args[-1] == "https://h/x"


def test_profile_conf_included_when_present(tmp_path):
    conf = tmp_path / "desktop-4070ti.conf"
    conf.write_text("[film]\n[anime]\n")
    plan = presets.build_plan(
        Options(url="https://h/x", content="anime"), "desktop-4070ti", conf_dir=tmp_path
    )
    assert f"--include={conf}" in plan.mpv_args
    assert "--profile=anime" in plan.mpv_args
    assert plan.mpv_args[-1] == "https://h/x"
    assert not any("не найден" in w and "конфиг" in w for w in plan.warnings)


def test_film_vs_anime_profile_name(tmp_path):
    conf = tmp_path / "air-m1.conf"
    conf.write_text("[film]\n[anime]\n")
    film = presets.build_plan(Options(url="https://h/x", content="film"), "air-m1", conf_dir=tmp_path)
    anime = presets.build_plan(Options(url="https://h/x", content="anime"), "air-m1", conf_dir=tmp_path)
    assert "--profile=film" in film.mpv_args
    assert "--profile=anime" in anime.mpv_args


def test_missing_conf_degrades_with_warning(tmp_path):
    plan = presets.build_plan(
        Options(url="https://h/x"), "desktop-4070ti", conf_dir=tmp_path
    )
    assert "--profile=gpu-hq" in plan.mpv_args
    assert plan.warnings and "не найден" in plan.warnings[0]


def test_headers_assembled_in_order():
    opts = Options(
        url="https://h/x",
        referer="https://r/",
        user_agent="UA/1",
        headers=["X-Extra: 1"],
    )
    plan = presets.build_plan(opts, "generic")
    field = [a for a in plan.mpv_args if a.startswith("--http-header-fields=")]
    assert field == [
        "--http-header-fields=Referer: https://r/,User-Agent: UA/1,X-Extra: 1"
    ]


def test_no_headers_means_no_header_option():
    plan = presets.build_plan(Options(url="https://h/x"), "generic")
    assert not any(a.startswith("--http-header-fields=") for a in plan.mpv_args)


# --- profiles_dir (002: frozen-режим) ---

def test_profiles_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MPV_LAUNCHER_PROFILES_DIR", str(tmp_path))
    assert presets.profiles_dir() == tmp_path


def test_profiles_dir_frozen_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.delenv("MPV_LAUNCHER_PROFILES_DIR", raising=False)
    monkeypatch.setattr(presets.sys, "frozen", True, raising=False)
    monkeypatch.setattr(presets.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert presets.profiles_dir() == tmp_path / "mpv-profiles"


def test_profiles_dir_repo_default(monkeypatch):
    monkeypatch.delenv("MPV_LAUNCHER_PROFILES_DIR", raising=False)
    monkeypatch.setattr(presets.sys, "frozen", False, raising=False)
    assert presets.profiles_dir().name == "mpv-profiles"


def test_separate_window_has_no_embedded_arguments():
    args = presets.build_plan(Options(url="https://a/b.m3u8", profile="generic")).mpv_args
    assert not [a for a in args if a.startswith(("--wid", "--input-ipc-server", "--keep-open"))]
    assert not [a for a in args if "top_bar_controls" in a or "Закрыть плеер" in a]


def test_embedded_player_stays_in_page_area_after_the_end():
    options = Options(url="https://a/b.m3u8", profile="generic", wid=1234, ipc_server="pipe-name")
    args = presets.build_plan(options).mpv_args
    assert "--wid=1234" in args
    assert "--input-ipc-server=pipe-name" in args
    assert "--keep-open=yes" in args
    assert args[-1] == "https://a/b.m3u8"
    assert any("uosc-top_bar_controls=no" in a for a in args)
    assert any("Закрыть плеер" in a for a in args)


def test_embedded_player_turns_off_fullscreen_from_profile(tmp_path):
    conf = tmp_path / "desktop-4070ti.conf"
    conf.write_text("fs=yes\n[film]\n", encoding="utf-8")
    options = Options(url="https://a/b.m3u8", profile="high", wid=1)
    args = presets.build_plan(options, "high", conf_dir=tmp_path).mpv_args
    assert args.index("--fullscreen=no") > args.index(f"--include={conf}")
