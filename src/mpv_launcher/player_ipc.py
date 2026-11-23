"""Канал управления встроенного mpv: приложение узнаёт, что зритель включил полный экран."""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
import time
from typing import Callable

_OPEN_TIMEOUT_SECONDS = 20
_OPEN_RETRY_SECONDS = 0.2
_OBSERVE = (
    b'{"command":["observe_property",1,"fullscreen"]}\n'
    b'{"command":["observe_property",2,"time-pos"]}\n'
    b'{"command":["observe_property",3,"duration"]}\n'
    b'{"command":["observe_property",4,"eof-reached"]}\n'
)


def _property(line: bytes, name: str):
    try:
        message = json.loads(line)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("event") != "property-change" or message.get("name") != name:
        return None
    return message.get("data")


def fullscreen_from_line(line: bytes) -> bool | None:
    """Значение из сообщения о смене полного экрана; ``None`` для остальных сообщений."""
    value = _property(line, "fullscreen")
    return value if isinstance(value, bool) else None


def position_from_line(line: bytes) -> float | None:
    """Позиция просмотра в секундах; ``None`` для остальных сообщений."""
    value = _property(line, "time-pos")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def duration_from_line(line: bytes) -> float | None:
    """Длительность в секундах; ``None`` для остальных сообщений."""
    value = _property(line, "duration")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def eof_from_line(line: bytes) -> bool:
    """Плеер дошёл до конца файла (при ``--keep-open`` он при этом не закрывается)."""
    return _property(line, "eof-reached") is True


_WINDOWS_PIPE = "\\\\.\\pipe\\"


def server_path(name: str) -> str:
    """Адрес канала для ``--input-ipc-server``: именованный канал Windows или Unix-сокет.

    Путь сокета короткий: у macOS предел около 104 символов, а временный каталог там длинный.
    """
    if platform.system() == "Windows":
        return f"{_WINDOWS_PIPE}mpv-cinema-{name}"
    return f"/tmp/mpv-cinema-{name[:16]}.sock"


def remove_server(path: str | None) -> None:
    """Сокет остаётся файлом после mpv; именованный канал Windows исчезает сам."""
    if path and not path.startswith(_WINDOWS_PIPE):
        try:
            os.unlink(path)
        except OSError:
            pass


class _Socket:
    """Unix-сокет с тем же чтением и записью, что у файла канала Windows."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self._sock.close()

    def write(self, data: bytes) -> None:
        self._sock.sendall(data)

    def read(self, size: int) -> bytes:
        return self._sock.recv(size)


def _connect(path: str):
    if path.startswith(_WINDOWS_PIPE):
        return open(path, "r+b", buffering=0)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        raise
    return _Socket(sock)


def _open(path: str, should_stop: Callable[[], bool]):
    deadline = time.monotonic() + _OPEN_TIMEOUT_SECONDS
    while time.monotonic() < deadline and not should_stop():
        try:
            return _connect(path)
        except OSError:
            time.sleep(_OPEN_RETRY_SECONDS)
    return None


def _read(
    pipe,
    on_fullscreen: Callable[[bool], None],
    on_position: Callable[[float], None],
    on_duration: Callable[[float], None],
    on_eof: Callable[[], None],
) -> None:
    with pipe:
        pipe.write(_OBSERVE)
        buffer = b""
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                return
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            for line in lines:
                fullscreen = fullscreen_from_line(line)
                if fullscreen is not None:
                    on_fullscreen(fullscreen)
                position = position_from_line(line)
                if position is not None:
                    on_position(position)
                duration = duration_from_line(line)
                if duration is not None:
                    on_duration(duration)
                if eof_from_line(line):
                    on_eof()


def watch(
    path: str,
    on_fullscreen: Callable[[bool], None],
    on_position: Callable[[float], None],
    should_stop: Callable[[], bool],
    on_duration: Callable[[float], None] = lambda _d: None,
    on_eof: Callable[[], None] = lambda: None,
) -> None:
    """Сообщать о полном экране, позиции, длительности и конце файла, пока идёт просмотр. Выполняется в своём потоке.

    После сбоя потока запасной адрес запускает новый mpv с тем же каналом, поэтому он открывается снова.
    """
    while not should_stop():
        pipe = _open(path, should_stop)
        if pipe is None:
            return
        try:
            _read(pipe, on_fullscreen, on_position, on_duration, on_eof)
        except OSError as exc:
            # Канал закрывается вместе с mpv: это обычное завершение просмотра.
            print(f"player_ipc: канал закрыт: {type(exc).__name__}", file=sys.stderr)
