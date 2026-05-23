#!/usr/bin/env python3
"""Sudo с паролем из веб-настроек (хранится только в памяти процесса панели)."""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any

try:
    from nout_panel.panel_log import setup_logging
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def setup_logging(name: str = "nout-panel") -> logging.Logger:
        return logging.getLogger(name)

_log = setup_logging("nout-panel.sudo")

_lock = threading.Lock()
_password: str | None = None


def is_configured() -> bool:
    with _lock:
        return _password is not None


def status() -> dict[str, Any]:
    return {"ok": True, "configured": is_configured()}


def set_password(password: str) -> dict[str, Any]:
    """Сохранить или сбросить пароль sudo."""
    global _password
    pwd = (password or "").strip()
    if not pwd:
        with _lock:
            _password = None
        _log.info("sudo password cleared")
        return {"ok": True, "configured": False, "message": "Пароль sudo сброшен"}

    test = run(["true"], password=pwd, timeout=12)
    if test.returncode != 0:
        err = ((test.stderr or "") + (test.stdout or "")).strip()[:300]
        return {"ok": False, "error": err or "Неверный пароль или нет прав sudo"}

    with _lock:
        _password = pwd
    _log.info("sudo password stored in memory")
    return {"ok": True, "configured": True, "message": "Пароль сохранён (до перезапуска панели)"}


def _stored_password() -> str | None:
    with _lock:
        return _password


def run(
    cmd: list[str],
    *,
    password: str | None = None,
    timeout: float | None = 15,
) -> subprocess.CompletedProcess[str]:
    """sudo -n или sudo -S для списка аргументов (без слова sudo в cmd)."""
    pwd = password if password is not None else _stored_password()
    if pwd:
        return subprocess.run(
            ["sudo", "-S", "-p", ""] + cmd,
            input=pwd + "\n",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return subprocess.run(
        ["sudo", "-n"] + cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def popen_shell_script(script: str) -> dict[str, Any]:
    """Фоновый shell через sudo (перезапуск systemd и т.п.)."""
    pwd = _stored_password()
    try:
        if pwd:
            proc = subprocess.Popen(
                ["sudo", "-S", "/bin/sh", "-c", script],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            assert proc.stdin is not None
            proc.stdin.write(pwd + "\n")
            proc.stdin.flush()
            proc.stdin.close()
        else:
            proc = subprocess.Popen(
                ["sudo", "-n", "/bin/sh", "-c", script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    time.sleep(0.35)
    if proc.poll() is not None:
        err_b = proc.stderr.read() if proc.stderr else b""
        err = err_b.decode("utf-8", "replace").strip()[:300]
        return {
            "ok": False,
            "error": err or "sudo отклонил команду (укажите пароль в Настройках)",
        }
    return {"ok": True}
