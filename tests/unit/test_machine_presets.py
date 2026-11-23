"""Автоопределение пресета по видеокарте и применение пресетов."""

from unittest import mock

import pytest

from mpv_launcher import machine, presets
from mpv_launcher.cli import Options


@pytest.mark.parametrize(
    ("name", "preset"),
    [
        ("NVIDIA GeForce RTX 4070 Ti", "high"),
        ("NVIDIA GeForce RTX 3080", "high"),
        ("NVIDIA GeForce RTX 5090", "high"),
        ("NVIDIA GeForce RTX 2080 SUPER", "high"),
        ("AMD Radeon RX 6800 XT", "high"),
        ("AMD Radeon RX 7900 XTX", "high"),
        ("NVIDIA GeForce RTX 3060", "mid"),
        ("NVIDIA GeForce RTX 4050 Laptop GPU", "mid"),
        ("NVIDIA GeForce GTX 1660 SUPER", "mid"),
        ("NVIDIA GeForce GTX 1060 6GB", "mid"),
        ("AMD Radeon RX 580 Series", "mid"),
        ("AMD Radeon RX 5700 XT", "mid"),
        ("AMD Radeon 780M Graphics", "mid"),
        ("Intel(R) Arc(TM) A750 Graphics", "mid"),
        ("Apple M1", "mid"),
        ("Apple M3 Max", "mid"),
        ("Intel(R) UHD Graphics 630", "low"),
        ("Intel(R) Iris(R) Xe Graphics", "low"),
        ("AMD Radeon(TM) Vega 8 Graphics", "low"),
        ("NVIDIA GeForce MX150", "low"),
        ("NVIDIA GeForce GT 730", "low"),
        ("Совершенно неизвестная карта 9000", "low"),
    ],
)
def test_model_classes(name, preset):
    assert machine.classify_gpus([name]) == {"preset": preset, "gpu": name}


def test_virtual_adapters_are_ignored_and_best_wins():
    names = [
        "Virtual Desktop Monitor",
        "Intel(R) UHD Graphics 770",
        "NVIDIA GeForce RTX 4070 Ti",
        "Microsoft Remote Display Adapter",
    ]
    assert machine.classify_gpus(names) == {"preset": "high", "gpu": "NVIDIA GeForce RTX 4070 Ti"}


@pytest.mark.parametrize("names", [[], ["Microsoft Basic Display Adapter"], ["Parsec Virtual Display Adapter"]])
def test_nothing_detected_is_low_without_name(names):
    assert machine.classify_gpus(names) == {"preset": "low", "gpu": None}


def test_detection_failure_is_low():
    machine.detect_device.cache_clear()
    with mock.patch.object(machine, "gpu_names", side_effect=OSError()):
        assert machine.detect_device() == {"preset": "low", "gpu": None}
    machine.detect_device.cache_clear()


def test_manual_preset_skips_detection():
    with mock.patch.object(machine, "detect_device") as detect:
        assert machine.preset_profile("mid") == "mid"
    detect.assert_not_called()


def test_auto_preset_uses_detection():
    with mock.patch.object(machine, "detect_device", return_value={"preset": "high", "gpu": "X"}):
        assert machine.preset_profile("auto") == "high"


@pytest.mark.parametrize(
    ("name", "driver", "supported"),
    [
        ("NVIDIA GeForce RTX 4070 Ti", "610.88", True),
        ("NVIDIA GeForce RTX 4070 Ti", "531.18", True),
        ("NVIDIA GeForce RTX 4070 Ti", "531.17", False),
        ("NVIDIA GeForce RTX 3060", "531.18", True),
        ("NVIDIA GeForce RTX 5080", "600.00", True),
        ("NVIDIA GeForce RTX 2080 SUPER", "545.84", True),
        ("NVIDIA GeForce RTX 2060", "545.83", False),
        ("NVIDIA GeForce RTX 2060", "531.18", False),
        ("NVIDIA GeForce GTX 1660 SUPER", "610.88", False),
        ("NVIDIA RTX A4000", "610.88", False),
        ("AMD Radeon RX 7900 XTX", "610.88", False),
        ("NVIDIA GeForce RTX 4070 Ti", "неизвестно", False),
    ],
)
def test_vsr_requires_rtx_and_driver(name, driver, supported):
    assert machine.vsr_supported(name, driver) is supported


def _nvidia_smi(stdout):
    return mock.Mock(stdout=stdout)


def _windows(gpus=("NVIDIA GeForce RTX 4070 Ti",)):
    return (
        mock.patch.object(machine.platform, "system", return_value="Windows"),
        mock.patch.object(machine.subprocess, "CREATE_NO_WINDOW", 0, create=True),
        mock.patch.object(machine, "gpu_names", return_value=list(gpus)),
    )


def test_vsr_available_reads_driver_from_nvidia_smi():
    machine._vsr_check.cache_clear()
    system, flags, gpus = _windows(("NVIDIA GeForce RTX 4070 Ti", "Microsoft Remote Display Adapter", "Virtual Desktop Monitor"))
    with system, flags, gpus, \
        mock.patch.object(machine.subprocess, "run", return_value=_nvidia_smi("NVIDIA GeForce RTX 4070 Ti, 610.88\n")):
        assert machine.vsr_available() is True
    machine._vsr_check.cache_clear()


def test_vsr_is_off_when_integrated_gpu_is_also_present():
    machine._vsr_check.cache_clear()
    system, flags, gpus = _windows(("NVIDIA GeForce RTX 4060 Laptop GPU", "Intel(R) UHD Graphics 770"))
    with system, flags, gpus, mock.patch.object(machine.subprocess, "run") as run:
        assert machine.vsr_available() is False
    run.assert_not_called()
    machine._vsr_check.cache_clear()


def test_vsr_check_failure_is_not_remembered():
    machine._vsr_check.cache_clear()
    system, flags, gpus = _windows()
    with system, flags, gpus, mock.patch.object(
        machine.subprocess,
        "run",
        side_effect=[machine.subprocess.TimeoutExpired("nvidia-smi", 3), _nvidia_smi("NVIDIA GeForce RTX 4070 Ti, 610.88\n")],
    ):
        assert machine.vsr_available() is False
        assert machine.vsr_available() is True
    machine._vsr_check.cache_clear()


@pytest.mark.parametrize(
    ("stdout", "supported"),
    [(" scaling-mode Choices: standard intel nvidia", True), (" scale Float", False), ("", False)],
)
def test_mpv_filter_support_is_checked(stdout, supported):
    machine._mpv_filter_help.cache_clear()
    with mock.patch.object(machine.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
        mock.patch.object(machine.subprocess, "run", return_value=_nvidia_smi(stdout)):
        assert machine.mpv_supports_vsr("mpv") is supported
    machine._mpv_filter_help.cache_clear()


def test_windows_pins_render_api_for_profiles():
    with mock.patch.object(presets.platform, "system", return_value="Windows"):
        plan = presets.build_plan(Options(url="https://h/x", content="film"), "high")
    assert "--gpu-api=d3d11" in plan.mpv_args
    with mock.patch.object(presets.platform, "system", return_value="Darwin"):
        plan = presets.build_plan(Options(url="https://h/x", content="film"), "high")
    assert "--gpu-api=d3d11" not in plan.mpv_args


def test_vsr_unavailable_without_nvidia_smi_or_on_other_systems():
    machine._vsr_check.cache_clear()
    system, flags, gpus = _windows()
    with system, flags, gpus, mock.patch.object(machine.subprocess, "run", side_effect=OSError()):
        assert machine.vsr_available() is False
    machine._vsr_check.cache_clear()
    with mock.patch.object(machine.platform, "system", return_value="Darwin"):
        assert machine.vsr_available() is False


def test_plan_replaces_shaders_with_vsr_after_profile():
    plan = presets.build_plan(Options(url="https://h/x", content="film", vsr=True), "high")
    args = plan.mpv_args
    assert args.index("--glsl-shaders=") > args.index("--profile=film")
    assert "--vf=@vsr:d3d11vpp=scale=2:scaling-mode=nvidia" in args
    assert "--hwdec=d3d11va" in args
    assert args[-1] == "https://h/x"


def test_plan_without_vsr_has_no_filter():
    plan = presets.build_plan(Options(url="https://h/x", content="film"), "high")
    assert not any(a.startswith("--vf=") for a in plan.mpv_args)


@pytest.mark.parametrize(
    ("preset", "conf"),
    [("high", "desktop-4070ti.conf"), ("mid", "mid.conf"), ("low", "low.conf")],
)
def test_presets_include_their_profile(preset, conf):
    plan = presets.build_plan(Options(url="https://h/x", content="film"), preset)
    assert f"--include={presets.profiles_dir() / conf}" in plan.mpv_args
    assert "--profile=film" in plan.mpv_args
    assert plan.warnings == []
