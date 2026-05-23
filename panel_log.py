# panel_log.py — простое логирование для быстрого запуска
import logging

logging.basicConfig(level=logging.INFO)
info = logging.info
error = logging.error


def setup_logging(name: str = "nout-panel") -> logging.Logger:
    """Логгер для модулей панели (совместимость с import setup_logging)."""
    return logging.getLogger(name)
