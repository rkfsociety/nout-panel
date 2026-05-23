#!/usr/bin/env python3
"""Управление питанием через loginctl (без пароля для сессии пользователя)."""

from __future__ import annotations

import subprocess
from typing import Any

try:
    from panel_log import setup_logging
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def setup_logging(name: str = "nout-panel") -> logging.Logger:
        return logging.getLogger(name)

_log = setup_logging("nout-panel.power")

# Подтверждение в теле запроса должно совпадать с action
_CONFIRM = {
    "suspend": "SUSPEND",
    "reboot": "REBOOT",
    "shutdown": "SHUTDOWN",
}

_CMD = {
    "suspend": ["loginctl", "suspend"],
    "reboot": ["loginctl", "reboot"],
    "shutdown": ["loginctl", "power-off"],
}


def run_power(action: str, confirm: str) -> dict[str, Any]:
    """Сон / перезагрузка / выключение с подтверждением."""
    action = action.strip().lower()
    if action not in _CMD:
        return {"ok": False, "error": "Неизвестное действие"}
    if confirm != _CONFIRM[action]:
        return {"ok": False, "error": "Нужно подтверждение: " + _CONFIRM[action]}
    cmd = _CMD[action]
    try:
        subprocess.Popen(cmd, start_new_session=True)
        _log.warning("power action: %s", action)
        return {"ok": True, "action": action}
    except FileNotFoundError:
        return {"ok": False, "error": "loginctl не найден"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
