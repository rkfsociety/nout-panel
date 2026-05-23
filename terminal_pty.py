#!/usr/bin/env python3
"""Терминал в браузере: PTY + bash (опрос вывода по HTTP)."""

from __future__ import annotations

import fcntl
import os
import pty
import select
import struct
import termios
import threading
import time
import uuid
from typing import Any

from panel_log import setup_logging

_log = setup_logging("nout-panel.terminal")

# Лимит буфера вывода и числа сессий
_OUTPUT_MAX = 256_000
_MAX_SESSIONS = 5
_SESSION_TTL_SEC = 3600

_sessions: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


class _TerminalSession:
    """Интерактивная shell-сессия через pseudo-TTY."""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.output = bytearray()
        self.out_lock = threading.Lock()
        self._stop = False
        self.last_used = time.time()
        self.master_fd: int
        self.pid: int
        self.master_fd, slave_fd = pty.openpty()
        self.pid = os.fork()
        if self.pid == 0:
            # Дочерний процесс — login shell
            os.close(self.master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.chdir(os.path.expanduser("~"))
            os.environ["TERM"] = "xterm-256color"
            os.environ["HOME"] = os.path.expanduser("~")
            os.execvpe("/bin/bash", ["/bin/bash", "-l"], os.environ)
        os.close(slave_fd)
        self._reader = threading.Thread(target=self._read_loop, name=f"pty-{self.id}", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        """Читаем вывод shell в буфер."""
        while not self._stop:
            try:
                ready, _, _ = select.select([self.master_fd], [], [], 0.25)
                if not ready:
                    continue
                chunk = os.read(self.master_fd, 4096)
                if not chunk:
                    break
                with self.out_lock:
                    self.output.extend(chunk)
                    if len(self.output) > _OUTPUT_MAX:
                        del self.output[: len(self.output) - _OUTPUT_MAX // 2]
            except OSError:
                break

    def write(self, data: bytes) -> None:
        self.last_used = time.time()
        if data:
            os.write(self.master_fd, data)

    def resize(self, cols: int, rows: int) -> None:
        self.last_used = time.time()
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def read_from(self, offset: int) -> tuple[bytes, int]:
        with self.out_lock:
            if offset < 0:
                offset = 0
            if offset > len(self.output):
                offset = len(self.output)
            data = bytes(self.output[offset:])
            return data, len(self.output)

    def close(self) -> None:
        self._stop = True
        try:
            os.kill(self.pid, 15)
        except ProcessLookupError:
            pass
        try:
            os.close(self.master_fd)
        except OSError:
            pass


def _cleanup_sessions() -> None:
    """Удаляем старые и лишние сессии."""
    now = time.time()
    with _lock:
        expired = [sid for sid, s in _sessions.items() if now - s["obj"].last_used > _SESSION_TTL_SEC]
        for sid in expired:
            _sessions[sid]["obj"].close()
            del _sessions[sid]
        while len(_sessions) > _MAX_SESSIONS:
            oldest = min(_sessions.items(), key=lambda x: x[1]["obj"].last_used)[0]
            _sessions[oldest]["obj"].close()
            del _sessions[oldest]


def create_session() -> str:
    """Новая терминальная сессия."""
    _cleanup_sessions()
    sess = _TerminalSession()
    with _lock:
        _sessions[sess.id] = {"obj": sess}
    _log.info("terminal session %s", sess.id)
    return sess.id


def get_session(session_id: str) -> _TerminalSession | None:
    with _lock:
        row = _sessions.get(session_id)
        if not row:
            return None
        row["obj"].last_used = time.time()
        return row["obj"]


def close_session(session_id: str) -> bool:
    with _lock:
        row = _sessions.pop(session_id, None)
    if not row:
        return False
    row["obj"].close()
    _log.info("terminal closed %s", session_id)
    return True


def poll_output(session_id: str, offset: int) -> dict[str, Any] | None:
    sess = get_session(session_id)
    if not sess:
        return None
    chunk, new_offset = sess.read_from(offset)
    import base64

    return {"offset": new_offset, "data": base64.b64encode(chunk).decode("ascii")}


def write_input(session_id: str, data_b64: str) -> bool:
    sess = get_session(session_id)
    if not sess:
        return False
    import base64

    try:
        raw = base64.b64decode(data_b64)
    except Exception:
        return False
    sess.write(raw)
    return True
