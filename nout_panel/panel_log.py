#!/usr/bin/env python3
"""Заглушка логирования: только stdlib, работает без внешних зависимостей."""

from __future__ import annotations

import logging

_configured = False


def _ensure_config() -> None:
    """Один раз настроить basicConfig для всего процесса."""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _configured = True


def setup_logging(name: str = "nout-panel") -> logging.Logger:
    """Логгер для модулей панели."""
    _ensure_config()
    return logging.getLogger(name)


def info(msg: str, *args: object, **kwargs: object) -> None:
    _ensure_config()
    logging.info(msg, *args, **kwargs)


def error(msg: str, *args: object, **kwargs: object) -> None:
    _ensure_config()
    logging.error(msg, *args, **kwargs)
