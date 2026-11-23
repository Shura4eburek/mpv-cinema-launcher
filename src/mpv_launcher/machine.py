"""Определение класса машины для выбора профиля апскейла."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from functools import lru_cache

VALID_PROFILES = ("auto", "desktop-4070ti", "air-m1", "generic")


def detect() -> str:
    """Эвристика класса машины.

    - macOS на Apple Silicon → `air-m1` (мобильный/облегчённый);
    - Windows с доступной dGPU NVIDIA (есть `nvidia-smi`) → `desktop-4070ti`;
    - иначе → `generic` (безопасный облегчённый вариант).
    """
    system = platform.system()
    arch = platform.machine().lower()
    if system == "Darwin" and arch in ("arm64", "aarch64"):
        return "air-m1"
    if system == "Windows" and shutil.which("nvidia-smi"):
        return "desktop-4070ti"
    return "generic"


def resolve(profile_flag: str) -> str:
    """Явный профиль (кроме `auto`) перекрывает автоопределение."""
    if profile_flag and profile_flag != "auto":
        return profile_flag
    return detect()


# --- Пресеты производительности ---

_VIRTUAL_ADAPTER = re.compile(r"virtual|remote display|basic display|basic render|parsec|vmware|virtualbox|citrix|displaylink|mirage", re.I)
_RANK = {"low": 0, "mid": 1, "high": 2}


def _nvidia_class(name: str) -> str | None:
    if "titan rtx" in name:
        return "high"
    rtx = re.search(r"\brtx\s*a?(\d{4})", name)
    if rtx:
        number = int(rtx[1])
        generation, tier = number // 1000, number % 1000
        if generation == 2:
            return "high" if tier >= 80 else "mid"
        if generation == 3:
            return "high" if tier >= 70 else "mid"
        return "high" if tier >= 60 else "mid"
    gtx = re.search(r"\bgtx\s*(\d{3,4})", name)
    if gtx:
        number = int(gtx[1])
        return "mid" if number >= 1060 or 970 <= number < 1000 else "low"
    return None


def _radeon_class(name: str) -> str | None:
    if re.search(r"\b(?:760|780|880|890)m\b", name):
        return "mid"
    rx = re.search(r"\brx\s*(\d{3,4})", name)
    if not rx:
        return None
    number = int(rx[1])
    if number < 1000:
        return "mid" if 470 <= number < 600 else "low"
    if number >= 9000:
        return "high" if number >= 9060 else "mid"
    if 5000 <= number < 6000:
        return "mid" if number >= 5500 else "low"
    tier = (number // 100) % 10
    if tier >= 7:
        return "high"
    return "mid" if tier >= 4 else "low"


def gpu_class(name: str) -> str:
    """Класс видеокарты по названию. Неизвестная модель никогда не получает High."""
    lowered = name.lower()
    if re.search(r"\bapple m\d", lowered) or re.search(r"\barc(?:\(tm\))?\s*[abm]?\d{3}", lowered):
        return "mid"
    return _nvidia_class(lowered) or _radeon_class(lowered) or "low"


def classify_gpus(names: list[str]) -> dict:
    """Лучшая из настоящих видеокарт: {"preset": ..., "gpu": название или None}."""
    real = [name.strip() for name in names if name.strip() and not _VIRTUAL_ADAPTER.search(name)]
    if not real:
        return {"preset": "low", "gpu": None}
    best = max(real, key=lambda name: _RANK[gpu_class(name)])
    return {"preset": gpu_class(best), "gpu": best}


def _windows_gpu_names() -> list[str]:
    """Установленные видеоадаптеры через SetupAPI.

    EnumDisplayDevices показывает адаптеры текущей сессии: в удалённом рабочем столе виден только
    виртуальный адаптер. WMI быстрее не вызвать: нужен отдельный процесс PowerShell.
    """
    import ctypes
    import uuid
    from ctypes import wintypes

    class DeviceInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("ClassGuid", ctypes.c_byte * 16),
            ("DevInst", wintypes.DWORD),
            ("Reserved", ctypes.c_size_t),
        ]

    digcf_present = 0x2
    spdrp_devicedesc = 0x0
    invalid_handle = ctypes.c_void_p(-1).value
    display_class = uuid.UUID("4d36e968-e325-11ce-bfc1-08002be10318").bytes_le

    api = ctypes.windll.setupapi
    api.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    api.SetupDiGetClassDevsW.argtypes = [ctypes.c_char_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    api.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DeviceInfo)]
    api.SetupDiGetDeviceRegistryPropertyW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(DeviceInfo),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

    devices = api.SetupDiGetClassDevsW(display_class, None, None, digcf_present)
    if devices in (None, invalid_handle):
        return []
    names = []
    try:
        info = DeviceInfo()
        info.cbSize = ctypes.sizeof(DeviceInfo)
        index = 0
        while api.SetupDiEnumDeviceInfo(devices, index, ctypes.byref(info)):
            buffer = ctypes.create_unicode_buffer(256)
            if api.SetupDiGetDeviceRegistryPropertyW(
                devices, ctypes.byref(info), spdrp_devicedesc, None, buffer, ctypes.sizeof(buffer), None
            ):
                names.append(buffer.value)
            index += 1
    finally:
        api.SetupDiDestroyDeviceInfoList(devices)
    return list(dict.fromkeys(names))


def gpu_names() -> list[str]:
    system = platform.system()
    if system == "Windows":
        return _windows_gpu_names()
    if system == "Darwin":
        result = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=1)
        return [result.stdout.strip()]
    result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=1)
    return [line.split(":", 2)[-1] for line in result.stdout.splitlines() if re.search(r"VGA|3D controller", line)]


@lru_cache(maxsize=1)
def detect_device() -> dict:
    try:
        return classify_gpus(gpu_names())
    except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
        return {"preset": "low", "gpu": None}


def preset_profile(preset: str) -> str:
    """Какой профиль применить: явный пресет или результат автоопределения."""
    return detect_device()["preset"] if preset == "auto" else preset


# --- RTX Video Super Resolution ---

# Минимальные драйверы по обзорам выхода функции: 531.18 для RTX 30/40, 545.84 для RTX 20.
_VSR_MIN_DRIVER = (531, 18)
_VSR_MIN_DRIVER_RTX20 = (545, 84)


def vsr_supported(name: str, driver: str) -> bool:
    """Поддерживает ли видеокарта с этим драйвером RTX VSR."""
    model = re.search(r"\bgeforce rtx\s*(\d)\d{3}", name.lower())
    version = re.fullmatch(r"(\d+)\.(\d+)", driver.strip())
    if not model or not version:
        return False
    minimum = _VSR_MIN_DRIVER_RTX20 if model[1] == "2" else _VSR_MIN_DRIVER
    return (int(version[1]), int(version[2])) >= minimum


def _hidden_output(command: list[str]) -> str:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout


def _has_other_real_gpu() -> bool:
    """На ноутбуке с двумя видеокартами mpv может работать на встроенной: VSR там не сработает."""
    return any(not _VIRTUAL_ADAPTER.search(name) and "nvidia" not in name.lower() for name in gpu_names())


@lru_cache(maxsize=1)
def _vsr_check() -> bool:
    if _has_other_real_gpu():
        return False
    output = _hidden_output(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    return any(vsr_supported(name, driver) for name, _, driver in (line.rpartition(",") for line in output.splitlines()))


def vsr_available() -> bool:
    """VSR работает только на Windows: у mpv он доступен через d3d11vpp. Сбой проверки не запоминается."""
    if platform.system() != "Windows":
        return False
    try:
        return _vsr_check()
    except (OSError, subprocess.SubprocessError):
        return False


@lru_cache(maxsize=2)
def _mpv_filter_help(mpv_path: str) -> str:
    return _hidden_output([mpv_path, "--vf=d3d11vpp=help"])


def mpv_supports_vsr(mpv_path: str) -> bool:
    """Старый mpv или mpv.net отвергли бы фильтр при запуске, и фильм не открылся бы."""
    try:
        return "scaling-mode" in _mpv_filter_help(mpv_path) and "nvidia" in _mpv_filter_help(mpv_path)
    except (OSError, subprocess.SubprocessError, AttributeError):
        return False
