"""T016 [US2]: определение класса машины."""

from unittest import mock

from mpv_launcher import machine


def _patch(system, arch="x86_64", nvidia=False):
    which = (lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" and nvidia else None)
    return (
        mock.patch.object(machine.platform, "system", return_value=system),
        mock.patch.object(machine.platform, "machine", return_value=arch),
        mock.patch.object(machine.shutil, "which", side_effect=which),
    )


def test_apple_silicon_is_air_m1():
    p1, p2, p3 = _patch("Darwin", "arm64")
    with p1, p2, p3:
        assert machine.detect() == "air-m1"


def test_windows_with_nvidia_is_desktop():
    p1, p2, p3 = _patch("Windows", "AMD64", nvidia=True)
    with p1, p2, p3:
        assert machine.detect() == "desktop-4070ti"


def test_windows_without_nvidia_is_generic():
    p1, p2, p3 = _patch("Windows", "AMD64", nvidia=False)
    with p1, p2, p3:
        assert machine.detect() == "generic"


def test_linux_is_generic():
    p1, p2, p3 = _patch("Linux", "x86_64")
    with p1, p2, p3:
        assert machine.detect() == "generic"


def test_explicit_profile_overrides_auto():
    assert machine.resolve("air-m1") == "air-m1"
    assert machine.resolve("desktop-4070ti") == "desktop-4070ti"


def test_auto_delegates_to_detect():
    with mock.patch.object(machine, "detect", return_value="generic"):
        assert machine.resolve("auto") == "generic"
