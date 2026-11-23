"""Канал управления встроенного mpv."""

import io

from mpv_launcher import player_ipc


def test_fullscreen_change_is_read_from_message():
    assert player_ipc.fullscreen_from_line(b'{"event":"property-change","id":1,"name":"fullscreen","data":true}') is True
    assert player_ipc.fullscreen_from_line(b'{"event":"property-change","id":1,"name":"fullscreen","data":false}') is False


def test_other_messages_are_ignored():
    assert player_ipc.fullscreen_from_line(b'{"event":"property-change","name":"pause","data":true}') is None
    assert player_ipc.fullscreen_from_line(b'{"event":"property-change","name":"fullscreen"}') is None
    assert player_ipc.fullscreen_from_line(b'{"request_id":0,"error":"success"}') is None
    assert player_ipc.fullscreen_from_line(b"not json") is None
    assert player_ipc.fullscreen_from_line(b"[]") is None


def test_missing_pipe_ends_watch_when_asked_to_stop():
    calls = []
    player_ipc.watch(r"\\.\pipe\mpv-cinema-absent", calls.append, calls.append, lambda: True)
    assert calls == []


def test_position_is_read_from_message():
    assert player_ipc.position_from_line(b'{"event":"property-change","id":2,"name":"time-pos","data":12.5}') == 12.5
    assert player_ipc.position_from_line(b'{"event":"property-change","id":2,"name":"time-pos"}') is None
    assert player_ipc.position_from_line(b'{"event":"property-change","id":1,"name":"fullscreen","data":true}') is None


class _Pipe(io.BytesIO):
    written = b""

    def write(self, data):
        _Pipe.written += data
        return len(data)


def test_watch_reopens_channel_for_next_mirror(monkeypatch):
    first = b'{"event":"property-change","name":"fullscreen","data":true}\n'
    second = b'{"event":"property-change","name":"time-pos","data":7}\n'
    pipes = iter([_Pipe(first), _Pipe(second)])
    stops = iter([False, False, True])
    monkeypatch.setattr(player_ipc, "_open", lambda _path, _stop: next(pipes))
    fullscreen, positions = [], []
    player_ipc.watch("pipe", fullscreen.append, positions.append, lambda: next(stops))
    assert fullscreen == [True]
    assert positions == [7.0]


def test_duration_and_eof_are_read_from_message():
    assert player_ipc.duration_from_line(b'{"event":"property-change","id":3,"name":"duration","data":5400.5}') == 5400.5
    assert player_ipc.duration_from_line(b'{"event":"property-change","id":3,"name":"duration","data":0}') is None
    assert player_ipc.eof_from_line(b'{"event":"property-change","id":4,"name":"eof-reached","data":true}') is True
    assert player_ipc.eof_from_line(b'{"event":"property-change","id":4,"name":"eof-reached","data":false}') is False


def test_watch_reports_duration_and_eof(monkeypatch):
    lines = (b'{"event":"property-change","name":"duration","data":100}\n'
             b'{"event":"property-change","name":"eof-reached","data":true}\n')
    pipes = iter([_Pipe(lines)])
    stops = iter([False, True])
    monkeypatch.setattr(player_ipc, "_open", lambda _path, _stop: next(pipes))
    durations, eofs = [], []
    player_ipc.watch("pipe", lambda _on: None, lambda _p: None, lambda: next(stops),
                     on_duration=durations.append, on_eof=lambda: eofs.append(True))
    assert durations == [100.0] and eofs == [True]
    assert b"eof-reached" in _Pipe.written


def test_server_path_per_platform(monkeypatch):
    monkeypatch.setattr(player_ipc.platform, "system", lambda: "Windows")
    assert player_ipc.server_path("abc") == r"\\.\pipe\mpv-cinema-abc"
    monkeypatch.setattr(player_ipc.platform, "system", lambda: "Darwin")
    path = player_ipc.server_path("0123456789abcdef0123")
    assert path == "/tmp/mpv-cinema-0123456789abcdef.sock" and len(path) < 104


def test_unix_socket_is_used_outside_windows(monkeypatch):
    class FakeSocket:
        sent = b""

        def __init__(self, *_args):
            self.closed = False

        def connect(self, path):
            self.path = path

        def sendall(self, data):
            FakeSocket.sent += data

        def recv(self, _size):
            return b""

        def close(self):
            self.closed = True

    monkeypatch.setattr(player_ipc.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(player_ipc.socket, "socket", FakeSocket)
    channel = player_ipc._connect("/tmp/mpv-cinema-x.sock")
    with channel:
        player_ipc._read(channel, None, None, None, None)
    assert b"eof-reached" in FakeSocket.sent
    assert channel._sock.closed and channel._sock.path == "/tmp/mpv-cinema-x.sock"


def test_remove_server_deletes_only_sockets(tmp_path):
    sock = tmp_path / "mpv.sock"
    sock.write_text("")
    player_ipc.remove_server(str(sock))
    assert not sock.exists()
    player_ipc.remove_server(r"\\.\pipe\mpv-cinema-x")
    player_ipc.remove_server(None)
