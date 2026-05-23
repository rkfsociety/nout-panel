#!/usr/bin/env python3
"""Логирование панели в файл (~/.nout-panel/log.txt по умолчанию)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Путь к логу (install.sh создаёт каталог; значение — в config.local.env)
_DEFAULT_LOG = Path.home() / ".nout-panel" / "log.txt"
LOG_PATH = os.environ.get("PANEL_LOG_FILE") or str(_DEFAULT_LOG)

# Ротация: размер файла 1–5 МБ и число резервных копий
def _log_max_bytes() -> int:
    try:
        mb = float(os.environ.get("PANEL_LOG_MAX_MB", "2"))
    except ValueError:
        mb = 2.0
    mb = max(1.0, min(mb, 5.0))
    return int(mb * 1_000_000)


def _log_backup_count() -> int:
    try:
        count = int(os.environ.get("PANEL_LOG_BACKUP_COUNT", "3"))
    except ValueError:
        count = 3
    return max(1, min(count, 10))


_CONFIGURED = False


def setup_logging(name: str = "nout-panel") -> logging.Logger:
    """Настроить ротацию логов в файл; без прав — в stderr (локальный запуск)."""
    global _CONFIGURED
    root = logging.getLogger("nout-panel")
    child = logging.getLogger(name if name.startswith("nout-panel") else f"nout-panel.{name}")

    if _CONFIGURED:
        return child

    root.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Основной вывод — файл с ротацией по размеру, не консоль
    log_file = Path(LOG_PATH).expanduser()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_file,
            maxBytes=_log_max_bytes(),
            backupCount=_log_backup_count(),
            encoding="utf-8",
        )
        handler.setFormatter(fmt)
        root.addHandler(handler)
    except OSError:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
        root.warning("Не удалось открыть %s — логи в stderr", log_file)

    root.propagate = False
    _CONFIGURED = True
    return child
