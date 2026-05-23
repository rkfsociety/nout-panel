#!/usr/bin/env python3
"""Файловый менеджер: только разрешённые корни (~/ и /mnt/)."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from panel_log import setup_logging

_log = setup_logging("nout-panel.files")


def _roots() -> list[Path]:
    """Корни из PANEL_FILE_ROOTS или домашний каталог + /mnt."""
    raw = os.environ.get("PANEL_FILE_ROOTS", "").strip()
    if raw:
        out = []
        for part in raw.split(":"):
            p = part.strip()
            if p:
                out.append(Path(p).expanduser().resolve())
        return out
    roots = [Path.home().resolve()]
    mnt = Path("/mnt")
    if mnt.is_dir():
        roots.append(mnt.resolve())
    return roots


def _inside_root(path: Path) -> bool:
    resolved = path.resolve()
    for root in _roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def resolve_path(path_str: str | Path | None) -> Path | None:
    """Безопасный путь внутри разрешённых корней."""
    if path_str is None:
        return None
    text = str(path_str).strip()
    if text in ("", "/"):
        return None
    p = Path(text).expanduser()
    if not p.is_absolute():
        p = (_roots()[0] / p).resolve()
    else:
        try:
            p = p.resolve()
        except OSError:
            return None
    if not _inside_root(p):
        return None
    return p


def list_roots() -> list[dict[str, str]]:
    """Список корневых каталогов для UI."""
    items = []
    for root in _roots():
        label = "~" if root == Path.home().resolve() else str(root)
        items.append({"path": str(root), "label": label, "name": root.name or label})
    return items


def list_dir(path_str: str | None) -> dict[str, Any]:
    """Содержимое каталога или список корней."""
    if not path_str:
        return {"ok": True, "roots": list_roots(), "path": None, "entries": []}
    path = resolve_path(path_str)
    if path is None:
        return {"ok": False, "error": "Путь вне разрешённой области"}
    if not path.exists():
        return {"ok": False, "error": "Не найдено"}
    if not path.is_dir():
        return {"ok": False, "error": "Не каталог"}
    entries = []
    try:
        names = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    for child in names:
        try:
            st = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "dir": child.is_dir(),
                    "size": st.st_size if child.is_file() else None,
                    "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        except OSError:
            continue
    parent = str(path.parent) if _inside_root(path.parent) else None
    return {"ok": True, "path": str(path), "parent": parent, "entries": entries}


def read_file_bytes(path_str: str) -> tuple[bytes, str] | None:
    """Скачать файл."""
    path = resolve_path(path_str)
    if path is None or not path.is_file():
        return None
    try:
        return path.read_bytes(), path.name
    except OSError:
        return None


def save_upload(path_str: str, data: bytes, filename: str) -> dict[str, Any]:
    """Загрузить файл в каталог."""
    dest_dir = resolve_path(path_str) if path_str else _roots()[0]
    if dest_dir is None or not dest_dir.is_dir():
        return {"ok": False, "error": "Каталог недоступен"}
    safe_name = Path(filename).name
    if not safe_name or safe_name in (".", ".."):
        return {"ok": False, "error": "Недопустимое имя"}
    target = (dest_dir / safe_name).resolve()
    if not _inside_root(target):
        return {"ok": False, "error": "Путь вне разрешённой области"}
    try:
        target.write_bytes(data)
        _log.info("upload %s (%d bytes)", target, len(data))
        return {"ok": True, "path": str(target)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def delete_path(path_str: str) -> dict[str, Any]:
    """Удалить файл или пустой каталог."""
    path = resolve_path(path_str)
    if path is None:
        return {"ok": False, "error": "Путь вне разрешённой области"}
    if path in _roots():
        return {"ok": False, "error": "Нельзя удалить корень"}
    try:
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        _log.info("delete %s", path)
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
