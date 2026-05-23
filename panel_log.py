#!/usr/bin/env python3
"""Логирование панели в файл (по умолчанию /var/log/nout-panel.log)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

# Путь к логу (install.sh создаёт файл и задаёт в systemd)
LOG_PATH = os.environ.get("PANEL_LOG_FILE", "/var/log/nout-panel.log")

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

    # Основной вывод — файл, не консоль (один handler на всё дерево nout-panel.*)
    try:
        handler: logging.Handler = RotatingFileHandler(
            LOG_PATH,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(fmt)
        root.addHandler(handler)
    except OSError:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
        root.warning("Не удалось открыть %s — логи в stderr", LOG_PATH)

    root.propagate = False
    _CONFIGURED = True
    return child
