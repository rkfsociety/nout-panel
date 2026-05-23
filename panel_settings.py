#!/usr/bin/env python3
"""Настройки панели через веб: конфиг, логи, статус сервиса."""

from __future__ import annotations

import os
import subprocess
from collections import deque
from pathlib import Path
from typing import Any

try:
    from panel_log import setup_logging
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def setup_logging(name: str = "nout-panel") -> logging.Logger:
        return logging.getLogger(name)

_log = setup_logging("nout-panel.settings")

_UNIT = os.environ.get("PANEL_SYSTEMD_UNIT", "nout-panel.service")
_INSTALL_DIR = Path(os.environ.get("INSTALL_DIR", Path(__file__).resolve().parent))
_CONFIG_LOCAL = _INSTALL_DIR / "config.local.env"
_CONFIG_SYSTEM = Path("/etc/nout-panel/env")

_READONLY_KEYS = ("PANEL_USER", "INSTALL_DIR")
_EDITABLE_KEYS = (
    "PANEL_PORT",
    "PANEL_METRICS_INTERVAL",
    "PANEL_LOG_FILE",
    "PANEL_LOG_MAX_MB",
    "PANEL_LOG_BACKUP_COUNT",
    "PANEL_FILE_ROOTS",
    "PANEL_AGENT_WORKSPACE",
    "PANEL_CHAT_DIR",
)


def _parse_env(path: Path) -> dict[str, str]:
    """Разбор KEY=VALUE из env-файла."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep:
            out[key.strip()] = val.strip()
    return out


def _write_env(path: Path, values: dict[str, str]) -> None:
    """Запись config.local.env (известные ключи + порядок)."""
    lines = ["# Локальная конфигурация nout-panel (не для Git)", ""]
    seen: set[str] = set()
    for key in (*_READONLY_KEYS, *_EDITABLE_KEYS):
        if key in values:
            lines.append(f"{key}={values[key]}")
            seen.add(key)
    for key in sorted(values):
        if key not in seen:
            lines.append(f"{key}={values[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _merge_env() -> dict[str, str]:
    """Текущие значения: локальный файл, иначе systemd env, иначе os.environ."""
    values = _parse_env(_CONFIG_SYSTEM)
    values.update(_parse_env(_CONFIG_LOCAL))
    for key in (*_READONLY_KEYS, *_EDITABLE_KEYS):
        if key not in values and key in os.environ:
            values[key] = os.environ[key]
    return values


def _validate_updates(updates: dict[str, str]) -> str | None:
    """Проверка полей перед сохранением."""
    if "PANEL_PORT" in updates:
        try:
            port = int(updates["PANEL_PORT"])
        except ValueError:
            return "PANEL_PORT должен быть числом"
        if port < 1024 or port > 65535:
            return "PANEL_PORT: диапазон 1024–65535"
    if "PANEL_METRICS_INTERVAL" in updates:
        try:
            interval = float(updates["PANEL_METRICS_INTERVAL"])
        except ValueError:
            return "PANEL_METRICS_INTERVAL должен быть числом"
        if interval < 0.1 or interval > 60:
            return "PANEL_METRICS_INTERVAL: 0.1–60"
    if "PANEL_LOG_MAX_MB" in updates:
        try:
            mb = float(updates["PANEL_LOG_MAX_MB"])
        except ValueError:
            return "PANEL_LOG_MAX_MB должен быть числом"
        if mb < 1 or mb > 5:
            return "PANEL_LOG_MAX_MB: 1–5"
    if "PANEL_LOG_BACKUP_COUNT" in updates:
        try:
            n = int(updates["PANEL_LOG_BACKUP_COUNT"])
        except ValueError:
            return "PANEL_LOG_BACKUP_COUNT должен быть целым"
        if n < 1 or n > 10:
            return "PANEL_LOG_BACKUP_COUNT: 1–10"
    if "PANEL_LOG_FILE" in updates and not updates["PANEL_LOG_FILE"].strip():
        return "PANEL_LOG_FILE не может быть пустым"
    return None


def get_config() -> dict[str, Any]:
    """Конфиг для формы в веб-UI."""
    values = _merge_env()
    return {
        "ok": True,
        "path": str(_CONFIG_LOCAL),
        "system_path": str(_CONFIG_SYSTEM),
        "editable_keys": list(_EDITABLE_KEYS),
        "readonly": {k: values.get(k, "") for k in _READONLY_KEYS},
        "values": {k: values.get(k, "") for k in _EDITABLE_KEYS},
    }


def save_config(updates: dict[str, str], apply: bool) -> dict[str, Any]:
    """Сохранить config.local.env и опционально применить в systemd."""
    clean = {k.strip(): str(v).strip() for k, v in updates.items() if k in _EDITABLE_KEYS}
    err = _validate_updates(clean)
    if err:
        return {"ok": False, "error": err}

    values = _merge_env()
    values.update(clean)
    try:
        _write_env(_CONFIG_LOCAL, values)
        _log.info("config saved %s", _CONFIG_LOCAL)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    if not apply:
        return {"ok": True, "message": "Сохранено в config.local.env", "applied": False}

    return apply_config()


def apply_config() -> dict[str, Any]:
    """Скопировать config.local.env → /etc/nout-panel/env (авто-перезапуск path-юнита)."""
    if not _CONFIG_LOCAL.is_file():
        return {"ok": False, "error": f"Нет файла {_CONFIG_LOCAL}"}
    try:
        proc = subprocess.run(
            ["sudo", "-n", "/usr/bin/cp", str(_CONFIG_LOCAL), str(_CONFIG_SYSTEM)],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        hint = (proc.stderr or proc.stdout or "").strip()[:300]
        return {
            "ok": False,
            "error": hint or "Нет прав на cp. Выполните: sudo ./install.sh",
        }
    _log.warning("config applied to %s", _CONFIG_SYSTEM)
    return {
        "ok": True,
        "message": "Конфиг применён, панель перезапустится автоматически",
        "applied": True,
    }


def tail_logs(lines: int = 200) -> dict[str, Any]:
    """Последние строки лог-файла панели."""
    n = max(10, min(int(lines), 2000))
    log_path = Path(os.environ.get("PANEL_LOG_FILE", Path.home() / ".nout-panel" / "log.txt"))
    if not log_path.is_file():
        return {"ok": True, "path": str(log_path), "text": "", "lines": 0}
    try:
        with log_path.open(encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=n)
        text = "".join(tail)
        return {"ok": True, "path": str(log_path), "text": text, "lines": len(tail)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def panel_info(version: str) -> dict[str, Any]:
    """Статус сервиса и путей для страницы настроек."""
    active = "unknown"
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", _UNIT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        active = (proc.stdout or "").strip() or "unknown"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    return {
        "ok": True,
        "version": version,
        "unit": _UNIT,
        "service_active": active == "active",
        "service_state": active,
        "config_local": str(_CONFIG_LOCAL),
        "config_system": str(_CONFIG_SYSTEM),
        "install_dir": str(_INSTALL_DIR),
    }
