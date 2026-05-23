#!/usr/bin/env python3
"""Управление сервисом панели (перезапуск через systemd)."""

from __future__ import annotations

import os
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


def restart_panel(confirm: str) -> dict[str, Any]:
    """Перезапуск systemd-юнита панели (ответ HTTP успевает уйти до restart)."""
    if confirm != _CONFIRM:
        return {"ok": False, "error": f"Нужно подтверждение: {_CONFIRM}"}

    # Проверка sudo без пароля (настраивается в install.sh)
    try:
        check = subprocess.run(
            ["sudo", "-n", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}
    if check.returncode != 0:
        return {
            "ok": False,
            "error": "Нет прав на systemctl. Один раз на ноуте: sudo ./install.sh (вкладка Настройки)",
        }

    unit = _UNIT.replace("'", "")
    # Небольшая задержка — чтобы JSON-ответ успел дойти до браузера
    script = f"sleep 0.8 && exec /usr/bin/systemctl restart '{unit}'"
    try:
        subprocess.Popen(
            ["sudo", "-n", "/bin/sh", "-c", script],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log.warning("panel restart scheduled (%s)", unit)
        return {"ok": True, "message": "Панель перезапускается…"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
