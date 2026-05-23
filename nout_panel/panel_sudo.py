#!/usr/bin/env python3
"""Sudo с паролем из веб-настроек (локальный файл ~/.nout-panel/sudo.secret)."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
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
_loaded = False


def _secret_path() -> Path:
    """Путь к локальному файлу пароля (не в Git)."""
    explicit = os.environ.get("PANEL_SUDO_FILE", "").strip()
    if explicit:
        return Path(explicit)
    log_file = os.environ.get("PANEL_LOG_FILE", "").strip()
    if log_file:
        return Path(log_file).parent / "sudo.secret"
    return Path.home() / ".nout-panel" / "sudo.secret"


def load_from_disk() -> None:
    """Загрузить пароль с диска при старте панели."""
    global _password, _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
    path = _secret_path()
    if not path.is_file():
        return
    try:
        pwd = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        _log.warning("не удалось прочитать %s: %s", path, exc)
        return
    if not pwd:
        return
    with _lock:
        _password = pwd
    _log.info("sudo password loaded from %s", path)


def _write_secret(pwd: str) -> None:
    path = _secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pwd + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _delete_secret() -> None:
    try:
        _secret_path().unlink(missing_ok=True)
    except OSError as exc:
        _log.warning("не удалось удалить %s: %s", _secret_path(), exc)


def is_configured() -> bool:
    load_from_disk()
    with _lock:
        return _password is not None


def status() -> dict[str, Any]:
    load_from_disk()
    path = _secret_path()
    return {
        "ok": True,
        "configured": is_configured(),
        "path": str(path) if path.is_file() else None,
    }


def set_password(password: str) -> dict[str, Any]:
    """Сохранить или сбросить пароль sudo."""
    global _password
    pwd = (password or "").strip()
    if not pwd:
        with _lock:
            _password = None
        _delete_secret()
        _log.info("sudo password cleared")
        return {"ok": True, "configured": False, "message": "Пароль sudo удалён"}

    test = run(["true"], password=pwd, timeout=12)
    if test.returncode != 0:
        err = ((test.stderr or "") + (test.stdout or "")).strip()[:300]
        return {"ok": False, "error": err or "Неверный пароль или нет прав sudo"}

    try:
        _write_secret(pwd)
    except OSError as exc:
        return {"ok": False, "error": f"Не удалось сохранить: {exc}"}

    with _lock:
        _password = pwd
    _log.info("sudo password saved to %s", _secret_path())
    return {
        "ok": True,
        "configured": True,
        "message": f"Пароль сохранён локально ({_secret_path()})",
    }


def _stored_password() -> str | None:
    load_from_disk()
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
            # stdin в бинарном режиме — только bytes
            proc.stdin.write((pwd + "\n").encode("utf-8"))
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


# Загрузка при импорте модуля
load_from_disk()
