#!/usr/bin/env python3
"""Управление сервисом панели (перезапуск через systemd)."""

from __future__ import annotations

import os
import shutil
from typing import Any

from nout_panel import panel_sudo

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


def _systemctl_path() -> str:
    return shutil.which("systemctl") or "/usr/bin/systemctl"


def restart_panel(confirm: str) -> dict[str, Any]:
    """Перезапуск systemd-юнита панели (ответ HTTP успевает уйти до restart)."""
    if confirm != _CONFIRM:
        return {"ok": False, "error": f"Нужно подтверждение: {_CONFIRM}"}

    unit = _UNIT.replace("'", "")
    systemctl = _systemctl_path()
    script = f"sleep 0.8 && exec {systemctl} restart '{unit}'"

    got = panel_sudo.popen_shell_script(script)
    if not got.get("ok"):
        hint = got.get("error", "")
        extra = " Укажите пароль sudo в Настройках." if not panel_sudo.is_configured() else ""
        return {"ok": False, "error": (hint + extra).strip()}

    _log.warning("panel restart scheduled (%s)", unit)
    return {"ok": True, "message": "Панель перезапускается…"}
