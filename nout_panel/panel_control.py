#!/usr/bin/env python3
"""Управление сервисом панели (перезапуск через systemd)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

try:
    from nout_panel.panel_log import setup_logging
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def setup_logging(name: str = "nout-panel") -> logging.Logger:
        return logging.getLogger(name)

_log = setup_logging("nout-panel.control")

_CONFIRM = "RESTART_PANEL"
_UNIT = os.environ.get("PANEL_SYSTEMD_UNIT", "nout-panel.service")
_SUDO_HINT = "Нет прав sudo. На ноуте один раз: sudo ./install.sh"


def _systemctl_path() -> str:
    return shutil.which("systemctl") or "/usr/bin/systemctl"


def restart_panel(confirm: str) -> dict[str, Any]:
    """Перезапуск systemd-юнита панели (ответ HTTP успевает уйти до restart)."""
    if confirm != _CONFIRM:
        return {"ok": False, "error": f"Нужно подтверждение: {_CONFIRM}"}

    unit = _UNIT.replace("'", "")
    systemctl = _systemctl_path()
    # Задержка — чтобы JSON-ответ успел дойти до браузера
    script = f"sleep 0.8 && exec {systemctl} restart '{unit}'"

    try:
        proc = subprocess.Popen(
            ["sudo", "-n", "/bin/sh", "-c", script],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    # sudo -v не подходит: в sudoers только restart, не полный sudo
    try:
        _out, err = proc.communicate(timeout=1.5)
    except subprocess.TimeoutExpired:
        return {"ok": True, "message": "Панель перезапускается…"}

    hint = (err or b"").decode("utf-8", "replace").strip()[:240]
    if proc.returncode != 0:
        _log.warning("panel restart denied: %s", hint or proc.returncode)
        return {
            "ok": False,
            "error": f"{_SUDO_HINT}. {hint}" if hint else _SUDO_HINT,
        }

    _log.warning("panel restart scheduled (%s)", unit)
    return {"ok": True, "message": "Панель перезапускается…"}
