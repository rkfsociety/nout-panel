#!/usr/bin/env python3
"""Сбор метрик CPU, RAM, дисков — кэш для быстрого API."""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from panel_log import setup_logging
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def setup_logging(name: str = "nout-panel") -> logging.Logger:
        return logging.getLogger(name)

_log = setup_logging("nout-panel.metrics")


def _metrics_interval() -> float:
    """Интервал обновления кэша из config.local.env (PANEL_METRICS_INTERVAL)."""
    raw = os.environ.get("PANEL_METRICS_INTERVAL", "0.5")
    try:
        val = float(raw)
    except ValueError:
        val = 0.5
    return max(0.1, min(val, 60.0))


# Интервал обновления кэша (сек) — задаётся в config.local.env
COLLECT_INTERVAL = _metrics_interval()

# Точек истории (~10 мин при интервале 0.5 с)
HISTORY_MAXLEN = 1200

# Типы ФС, которые не показываем в панели
_SKIP_FSTYPES = frozenset(
    {
        "tmpfs",
        "devtmpfs",
        "squashfs",
        "overlay",
        "proc",
        "sysfs",
        "devpts",
        "cgroup",
        "cgroup2",
        "securityfs",
        "pstore",
        "bpf",
        "tracefs",
        "debugfs",
        "fusectl",
        "mqueue",
        "hugetlbfs",
        "configfs",
        "efivarfs",
        "autofs",
        "binfmt_misc",
        "fuse.gvfsd-fuse",
        "fuse.portal",
    }
)

# Префиксы путей, не показываем в панели
_SKIP_MOUNT_PREFIXES = ("/proc", "/sys", "/dev", "/run", "/snap")

# Пути /proc и /sys — через pathlib
_PROC_STAT = Path("/proc/stat")
_PROC_MEMINFO = Path("/proc/meminfo")
_PROC_LOADAVG = Path("/proc/loadavg")
_PROC_MOUNTS = Path("/proc/mounts")
_SYS_THERMAL = Path("/sys/class/thermal")
_SYS_POWER = Path("/sys/class/power_supply")

# Ошибки сбора метрик — ловим явно, без except Exception
_COLLECTOR_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    ZeroDivisionError,
)

_cache: dict[str, Any] = {"ok": False}
_history: deque[dict[str, Any]] = deque(maxlen=HISTORY_MAXLEN)
_lock = threading.Lock()
_prev_cpu: tuple[int, int] | None = None
_thread_started = False


def _proc_exists(path: Path) -> bool:
    """Проверка, что файл /proc или /sys доступен для чтения."""
    return os.path.exists(os.fspath(path))


def _read_proc_text(path: Path) -> str | None:
    """Прочитать файл /proc; при отсутствии — None, без падения."""
    if not _proc_exists(path):
        _log.debug("Файл недоступен: %s", path)
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.warning("Не удалось прочитать %s: %s", path, exc)
        return None


def _parse_int(raw: str, default: int | None = 0) -> int | None:
    """Безопасный int; при ошибке — default."""
    try:
        return int(str(raw).strip().split()[0])
    except (ValueError, TypeError, IndexError, AttributeError):
        return default


def _parse_float(raw: str, default: float | None = 0.0) -> float | None:
    """Безопасный float; при ошибке — default."""
    try:
        return float(str(raw).strip().split()[0])
    except (ValueError, TypeError, IndexError, AttributeError):
        return default


def _safe(label: str, fn: Callable[[], Any], default: Any) -> Any:
    """Вызов сборщика: при ошибке — default и запись в лог, без падения."""
    try:
        return fn()
    except _COLLECTOR_ERRORS as exc:
        _log.warning("%s: %s", label, exc)
        return default


def _memory_na() -> dict[str, Any]:
    """ОЗУ недоступно — N/A в UI."""
    return {
        "available": False,
        "ram_total_gb": None,
        "ram_used_gb": None,
        "ram_percent": None,
        "swap_total_gb": None,
        "swap_used_gb": None,
        "swap_percent": None,
    }


def _temperatures_na() -> dict[str, Any]:
    """Температуры недоступны — N/A в UI."""
    return {"available": False, "sensors": []}


def _battery_na() -> dict[str, Any]:
    """Батарея отсутствует или недоступна — N/A в UI."""
    return {"available": False, "percent": None, "status": "na", "status_label": "N/A"}


def _read_cpu_jiffies() -> tuple[int, int] | None:
    """Сумма jiffies CPU и idle из /proc/stat."""
    text = _read_proc_text(_PROC_STAT)
    if not text:
        return None
    lines = text.splitlines()
    if not lines:
        return None
    parts = lines[0].split()
    if len(parts) < 5:
        return None
    # cpu user nice system idle iowait irq softirq ...
    nums: list[int] = []
    for token in parts[1:]:
        val = _parse_int(token, None)
        if val is not None:
            nums.append(val)
    if len(nums) < 4:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return sum(nums), idle


def _cpu_percent() -> float | None:
    """Загрузка CPU (%), нужны два замера."""
    global _prev_cpu
    cur = _read_cpu_jiffies()
    if cur is None:
        return None
    if _prev_cpu is None:
        _prev_cpu = cur
        return None
    total_d = cur[0] - _prev_cpu[0]
    idle_d = cur[1] - _prev_cpu[1]
    _prev_cpu = cur
    if total_d <= 0:
        return 0.0
    return round(100.0 * (1.0 - idle_d / total_d), 1)


def _memory() -> dict[str, Any]:
    """ОЗУ и swap из /proc/meminfo (кБ)."""
    text = _read_proc_text(_PROC_MEMINFO)
    if not text:
        raise OSError("meminfo недоступен")
    info: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        kb = _parse_int(rest, None)
        if kb is not None:
            info[key] = kb

    total_kb = info.get("MemTotal", 0)
    avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
    used_kb = max(0, total_kb - avail_kb)

    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    swap_used = max(0, swap_total - swap_free)

    def pct(used: int, total: int) -> float:
        return round(100.0 * used / total, 1) if total > 0 else 0.0

    return {
        "available": True,
        "ram_total_gb": round(total_kb / 1024 / 1024, 2),
        "ram_used_gb": round(used_kb / 1024 / 1024, 2),
        "ram_percent": pct(used_kb, total_kb),
        "swap_total_gb": round(swap_total / 1024 / 1024, 2),
        "swap_used_gb": round(swap_used / 1024 / 1024, 2),
        "swap_percent": pct(swap_used, swap_total),
    }


def _load() -> dict[str, Any]:
    """Средняя загрузка и число ядер."""
    text = _read_proc_text(_PROC_LOADAVG)
    if not text:
        raise OSError("loadavg недоступен")
    parts = text.split()
    if len(parts) < 3:
        raise ValueError("короткая строка loadavg")
    load1 = _parse_float(parts[0], None)
    load5 = _parse_float(parts[1], None)
    load15 = _parse_float(parts[2], None)
    if load1 is None:
        raise ValueError("не удалось разобрать loadavg")
    cores = os.cpu_count() or 1
    return {
        "load_1": load1,
        "load_5": load5 if load5 is not None else 0.0,
        "load_15": load15 if load15 is not None else 0.0,
        "cpu_cores": cores,
        "load_percent": round(100.0 * load1 / cores, 1),
    }


def _temperatures() -> dict[str, Any]:
    """Температуры из thermal_zone; сбой датчика — пропуск, нет датчиков — N/A."""
    by_label: dict[str, float] = {}
    if not _proc_exists(_SYS_THERMAL) or not _SYS_THERMAL.is_dir():
        return _temperatures_na()
    for zone in sorted(_SYS_THERMAL.iterdir(), key=lambda p: p.name):
        if not zone.name.startswith("thermal_zone"):
            continue
        temp_path = zone / "temp"
        type_path = zone / "type"
        try:
            if not temp_path.is_file():
                continue
            raw = temp_path.read_text(encoding="utf-8").strip()
            if not raw or raw in ("0", "00"):
                continue
            milli = _parse_int(raw, None)
            if milli is None:
                continue
            celsius = round(milli / 1000.0, 1)
            if celsius <= 0:
                continue
            label = type_path.read_text(encoding="utf-8").strip() if type_path.is_file() else zone.name
            by_label[label] = max(by_label.get(label, 0.0), celsius)
        except (OSError, ValueError, TypeError):
            # Отдельная зона недоступна — не прерываем сбор остальных
            continue
    if not by_label:
        return _temperatures_na()
    sensors = [{"name": k, "celsius": v, "status": "ok"} for k, v in sorted(by_label.items())]
    return {"available": True, "sensors": sensors}


def _battery() -> dict[str, Any]:
    """Заряд батареи из power_supply (ноутбук); на ПК без BAT — N/A."""
    if not _proc_exists(_SYS_POWER) or not _SYS_POWER.is_dir():
        return _battery_na()
    status_labels = {
        "charging": "зарядка",
        "discharging": "разряд",
        "full": "полная",
        "not charging": "не заряжается",
        "unknown": "неизвестно",
    }
    for root in sorted(_SYS_POWER.iterdir(), key=lambda p: p.name):
        if not root.name.upper().startswith("BAT"):
            continue
        cap_path = root / "capacity"
        status_path = root / "status"
        try:
            if not cap_path.is_file():
                continue
            percent = _parse_int(cap_path.read_text(encoding="utf-8"), None)
            if percent is None or percent < 0 or percent > 100:
                continue
            status_raw = "unknown"
            if status_path.is_file():
                status_raw = status_path.read_text(encoding="utf-8").strip().lower()
            return {
                "available": True,
                "percent": percent,
                "status": status_raw,
                "status_label": status_labels.get(status_raw, status_raw),
            }
        except (OSError, ValueError, TypeError):
            continue
    return _battery_na()


def _disks() -> list[dict[str, Any]]:
    """Занятость смонтированных разделов."""
    seen: set[str] = set()
    mounts: list[tuple[str, str, str]] = []
    mounts_text = _read_proc_text(_PROC_MOUNTS)
    if not mounts_text:
        return []
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        dev, mnt, fstype = parts[0], parts[1], parts[2]
        if fstype in _SKIP_FSTYPES:
            continue
        if any(mnt.startswith(p) for p in _SKIP_MOUNT_PREFIXES):
            continue
        mnt_path = Path(mnt)
        if mnt in seen or not mnt_path.is_dir():
            continue
        try:
            shutil.disk_usage(mnt_path)
        except OSError:
            continue
        seen.add(mnt)
        mounts.append((dev, mnt, fstype))

    # Сортируем: / первым, потом /home, остальное по пути
    def sort_key(item: tuple[str, str, str]) -> tuple[int, str]:
        mnt = item[1]
        if mnt == "/":
            return (0, mnt)
        if mnt == "/home":
            return (1, mnt)
        return (2, mnt)

    mounts.sort(key=sort_key)

    disks: list[dict[str, Any]] = []
    for dev, mnt, fstype in mounts:
        usage = shutil.disk_usage(Path(mnt))
        total = usage.total
        if total < 100 * 1024 * 1024:  # меньше 100 МБ — не показываем
            continue
        used = usage.used
        pct = round(100.0 * used / total, 1) if total > 0 else 0.0
        disks.append(
            {
                "device": dev,
                "mount": mnt,
                "fstype": fstype,
                "total_gb": round(total / 1024**3, 2),
                "used_gb": round(used / 1024**3, 2),
                "free_gb": round(usage.free / 1024**3, 2),
                "percent": pct,
            }
        )
    return disks


def _append_history(data: dict[str, Any]) -> None:
    """Добавить точку в кольцевой буфер для графиков."""
    if not data.get("cpu_ready"):
        return
    temps_block = data.get("temperatures") or {}
    sensors = temps_block.get("sensors") if isinstance(temps_block, dict) else temps_block or []
    temp_max = max(
        (t["celsius"] for t in sensors if t.get("celsius") is not None),
        default=None,
    )
    point: dict[str, Any] = {
        "ts": data["time_utc"],
        "cpu": data["cpu_percent"],
        "ram": data["memory"]["ram_percent"],
        "load": data["load"]["load_percent"],
    }
    if temp_max is not None:
        point["temp_max"] = temp_max
    _history.append(point)


def _collect_once() -> dict[str, Any]:
    """Один проход сбора всех метрик; сбой подсистемы — N/A, не исключение."""
    cpu = _cpu_percent()
    memory = _safe("memory", _memory, _memory_na())
    load = _safe("load", _load, {"load_1": None, "load_5": None, "load_15": None, "cpu_cores": None, "load_percent": None})
    temperatures = _safe("temperatures", _temperatures, _temperatures_na())
    battery = _safe("battery", _battery, _battery_na())
    disks = _safe("disks", _disks, [])
    return {
        "ok": True,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": cpu if cpu is not None else 0.0,
        "cpu_ready": cpu is not None,
        "memory": memory,
        "load": load,
        "temperatures": temperatures,
        "battery": battery,
        "disks": disks,
    }


def _collector_loop() -> None:
    """Фоновый цикл обновления кэша."""
    global _prev_cpu
    # Первый замер CPU (если /proc/stat недоступен — пропускаем)
    _prev_cpu = _read_cpu_jiffies()
    time.sleep(COLLECT_INTERVAL)
    while True:
        try:
            data = _collect_once()
            with _lock:
                _cache.clear()
                _cache.update(data)
                _append_history(data)
        except _COLLECTOR_ERRORS as exc:
            _log.exception("collector_loop: %s", exc)
            with _lock:
                _cache.update({"ok": False, "error": str(exc)})
        time.sleep(COLLECT_INTERVAL)


def start_collector() -> None:
    """Запуск фонового сборщика (один раз)."""
    global _thread_started
    if _thread_started:
        return
    _thread_started = True
    t = threading.Thread(target=_collector_loop, name="metrics-collector", daemon=True)
    t.start()


def get_metrics() -> dict[str, Any]:
    """Текущий снимок метрик и история для графиков."""
    with _lock:
        out = dict(_cache)
        out["history"] = list(_history)
        out["history_interval_sec"] = COLLECT_INTERVAL
        return out
