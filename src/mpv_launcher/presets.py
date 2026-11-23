"""Сборка аргументов mpv из профиля машины и пресета контента."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Класс машины → имя файла mpv-профиля (None = базовый встроенный апскейл).
PROFILE_CONF: dict[str, str | None] = {
    "desktop-4070ti": "desktop-4070ti.conf",
    "air-m1": "air-m1.conf",
    "generic": None,
    # Пресеты приложения.
    "high": "desktop-4070ti.conf",
    "mid": "mid.conf",
    "low": "low.conf",
}

# Встроенный профиль mpv для деградации (без внешних шейдеров).
FALLBACK_PROFILE = "gpu-hq"

# Без --demuxer=lavf при сбое HLS-демуксера (например, 502 от CDN) mpv откатывается
# на playlist-демуксер и играет каждый .ts-сегмент (~6 с) как отдельный файл.
# seg_max_retry переживает разовые ошибки CDN на сегментах во время просмотра.
HLS_ARGS = ["--demuxer=lavf", "--demuxer-lavf-o=seg_max_retry=5", "--network-timeout=10"]

# Метка @vsr позволяет плееру выключать и включать апскейл без перезапуска.
VSR_ARGS = [
    "--hwdec=d3d11va",
    "--glsl-shaders=",
    "--vf=@vsr:d3d11vpp=scale=2:scaling-mode=nvidia",
]

# Явно, чтобы глобальный mpv.conf не вернул Vulkan: с ним при интерполяции были подфризы.
WINDOWS_RENDER_ARGS = ["--gpu-api=d3d11"]

DEFAULT_TITLE = "Видео по ссылке"
CURSOR_AUTOHIDE_MS = 3000
ANY_CURSOR_POSITION = 100000  # больше любого экрана: панель видна, где бы ни был курсор

# Кнопки панели uosc. Запятая здесь — часть значения, поэтому только --script-opts-append.
UOSC_CONTROLS = (
    "play-pause,gap,menu,subtitles,audio,space,"
    "command:high_quality:script-message-to cinema picture-menu?Качество картинки,"
    "gap,fullscreen"
)


# Плеер на странице: окном управляет приложение, а закрывается сам плеер.
EMBEDDED_UOSC_CONTROLS = f"{UOSC_CONTROLS},gap,command:close:quit?Закрыть плеер"


def _player_args(base: Path, embedded: bool = False) -> list[str] | None:
    """Аргументы интерфейса плеера; None, если каталога player/ нет."""
    player = base / "player"
    if not (player / "uosc" / "main.lua").is_file():
        return None
    return [
        "--no-osc",
        "--osd-bar=no",
        "--border=no",
        f"--cursor-autohide={CURSOR_AUTOHIDE_MS}",
        f"--script={player / 'uosc'}",
        f"--script={player / 'cinema.lua'}",
        f"--osd-fonts-dir={player / 'fonts'}",
        "--script-opts-append=uosc-languages=ru",
        f"--script-opts-append=uosc-controls={EMBEDDED_UOSC_CONTROLS if embedded else UOSC_CONTROLS}",
        # Панель появляется при любом движении мыши и скрывается вместе с курсором.
        "--script-opts-append=uosc-autohide=yes",
        f"--script-opts-append=uosc-proximity_in={ANY_CURSOR_POSITION}",
        f"--script-opts-append=uosc-proximity_out={ANY_CURSOR_POSITION + 1}",
    ]


@dataclass
class LaunchPlan:
    """Результат сборки — вход для runner."""

    mpv_args: list[str]
    warnings: list[str] = field(default_factory=list)


def profiles_dir() -> Path:
    """Каталог с mpv-профилями.

    Приоритет: env ``MPV_LAUNCHER_PROFILES_DIR`` → frozen-бандл (PyInstaller,
    ``sys._MEIPASS``) → каталог ``mpv-profiles`` в корне репозитория.
    """
    env = os.environ.get("MPV_LAUNCHER_PROFILES_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base) / "mpv-profiles"
    return Path(__file__).resolve().parents[2] / "mpv-profiles"


def _header_fields(options) -> list[str]:
    headers: list[str] = []
    if options.referer:
        headers.append(f"Referer: {options.referer}")
    if options.user_agent:
        headers.append(f"User-Agent: {options.user_agent}")
    headers.extend(options.headers or [])
    return headers


def build_plan(options, machine_profile: str | None = None, conf_dir=None) -> LaunchPlan:
    """Собрать argv для mpv. `url` всегда последний элемент.

    mpv запускается БЕЗ ``--no-config`` (иначе ломается резолв ``~~/`` к каталогу
    конфига, где лежат шейдеры). Дублирование с глобальным ``mpv.conf`` устранено
    на уровне профилей: секции ``[film]``/``[anime]`` в ``mpv-profiles/*.conf``
    задают список шейдеров replace-формой ``glsl-shaders=``, перекрывая всё, что
    добавил глобальный конфиг. Для класса ``generic`` — встроенный ``--profile=gpu-hq``.
    """
    args: list[str] = ["mpv"]
    warnings: list[str] = []

    base = Path(conf_dir) if conf_dir is not None else profiles_dir()
    conf_name = PROFILE_CONF.get(machine_profile) if machine_profile else None

    # Настройки качества апскейла
    upscale = getattr(options, "upscale_quality", "max")
    if upscale == "basic":
        args.append(f"--profile={FALLBACK_PROFILE}")
    else:
        use_conf = False
        if conf_name:
            conf_path = base / conf_name
            if conf_path.is_file():
                args.append(f"--include={conf_path}")
                args.append(f"--profile={options.content}")
                use_conf = True
                if platform.system() == "Windows":
                    args.extend(WINDOWS_RENDER_ARGS)
            else:
                warnings.append(
                    f"профиль {machine_profile}: конфиг {conf_path} не найден — "
                    f"базовый апскейл"
                )
        if not use_conf:
            args.append(f"--profile={FALLBACK_PROFILE}")

    if getattr(options, "vsr", False):
        args.extend(VSR_ARGS)

    # Генератор кадров / плавная интерполяция движений
    interp = getattr(options, "interpolation", None)
    if interp is True:
        args.append("--video-sync=display-resample")
        args.append("--interpolation=yes")
        args.append("--tscale=mitchell")
        args.append("--tscale-clamp=0")
        args.append("--blend-subtitles=yes")
    elif interp is False:
        args.append("--interpolation=no")

    headers = _header_fields(options)
    if headers:
        args.append("--http-header-fields=" + ",".join(headers))

    args.extend(HLS_ARGS)

    args.append(f"--force-media-title={getattr(options, 'title', None) or DEFAULT_TITLE}")
    wid = getattr(options, "wid", None)
    if wid is not None:
        # Профили задают fs=yes: встроенное окно разворачивает приложение. После конца фильма плеер остаётся.
        args.extend([f"--wid={wid}", "--fullscreen=no", "--keep-open=yes"])
        start = getattr(options, "start", None)
        if start:
            args.append(f"--start={start:.3f}")

    # Канал управления: полный экран встроенного плеера и позиция для «Моего списка».
    ipc_server = getattr(options, "ipc_server", None)
    if ipc_server:
        args.append(f"--input-ipc-server={ipc_server}")

    player_args = _player_args(base, embedded=wid is not None)
    if player_args is None:
        warnings.append(f"интерфейс плеера не найден в {base / 'player'} — стандартный интерфейс mpv")
    else:
        args.extend(player_args)
        if wid is not None:
            args.append("--script-opts-append=uosc-top_bar_controls=no")
        ready_file = getattr(options, "ready_file", None)
        if ready_file:
            args.append(f"--script-opts-append=cinema-ready_file={ready_file}")

    if options.url:
        args.append(options.url)
    return LaunchPlan(mpv_args=args, warnings=warnings)
