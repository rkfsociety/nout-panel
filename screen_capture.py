#!/usr/bin/env python3
"""Скриншот экрана: перебор типичных утилит Linux."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from panel_log import setup_logging

_log = setup_logging("nout-panel.screen")


def capture_png() -> tuple[bytes, str] | None:
    """PNG-байты или None, если снимок недоступен."""
    tmp = Path(tempfile.mkdtemp(prefix="nout-panel-scr-"))
    out = tmp / "shot.png"
    try:
        cmds: list[list[str]] = []
        out_path = os.fspath(out)
        if os.environ.get("WAYLAND_DISPLAY"):
            cmds.append(["grim", out_path])
        if os.environ.get("DISPLAY"):
            cmds.extend(
                [
                    ["scrot", "-o", out_path],
                    ["gnome-screenshot", "-f", out_path],
                    ["import", "-window", "root", out_path],
                ]
            )
        cmds.append(["fbgrab", out_path])

        for cmd in cmds:
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                if r.returncode == 0 and out.is_file() and out.stat().st_size > 0:
                    data = out.read_bytes()
                    _log.info("screenshot via %s (%d bytes)", cmd[0], len(data))
                    return data, "image/png"
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        return None
    finally:
        _rmtree(tmp)


def _rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def _tools_present() -> list[str]:
    """Какие утилиты снимка найдены в PATH."""
    import shutil

    names = []
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("grim"):
        names.append("grim")
    if os.environ.get("DISPLAY"):
        for n in ("scrot", "gnome-screenshot", "import"):
            if shutil.which(n):
                names.append(n)
    if shutil.which("fbgrab"):
        names.append("fbgrab")
    return names


def capture_info() -> dict[str, Any]:
    """Статус доступности снимка экрана (без съёмки)."""
    tools = _tools_present()
    if tools:
        return {"ok": True, "available": True, "tools": tools}
    return {
        "ok": True,
        "available": False,
        "hint": "Установите grim (Wayland) или scrot (X11)",
    }
