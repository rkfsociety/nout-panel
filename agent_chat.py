#!/usr/bin/env python3
"""Чат с Cursor Agent из веб-панели (cursor agent CLI)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from panel_log import setup_logging
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def setup_logging(name: str = "nout-panel") -> logging.Logger:
        return logging.getLogger(name)

_log = setup_logging("nout-panel.chat")


def _env_path(key: str, default: Path) -> Path:
    """Путь из переменной окружения или значение по умолчанию."""
    raw = os.environ.get(key)
    if raw:
        return Path(raw).expanduser().resolve()
    return default.resolve()


_DATA_DIR = _env_path("PANEL_CHAT_DIR", Path.home() / ".local/share/nout-panel")
_SESSIONS_FILE = _DATA_DIR / "chat_sessions.json"
_WORKSPACE = _env_path("PANEL_AGENT_WORKSPACE", Path(__file__).resolve().parent.parent)

_jobs: dict[str, _Job] = {}
_jobs_lock = threading.Lock()
_MAX_JOB_OUTPUT = 512_000


@dataclass
class _Job:
    id: str
    session_id: str
    status: str = "running"
    output: str = ""
    error: str = ""
    started: float = field(default_factory=time.time)
    proc: subprocess.Popen[str] | None = None


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def agent_status() -> dict[str, Any]:
    """Проверка: залогинен ли cursor agent на ноуте."""
    if os.environ.get("CURSOR_API_KEY"):
        return {
            "ok": True,
            "available": True,
            "workspace": _WORKSPACE.as_posix(),
            "hint": None,
            "via": "CURSOR_API_KEY",
        }
    try:
        r = subprocess.run(
            ["cursor", "agent", "status"],
            capture_output=True,
            text=True,
            timeout=45,
        )
        text = (r.stdout or "") + (r.stderr or "")
        logged_in = "not logged in" not in text.lower() and (
            "logged in" in text.lower() or "authenticated" in text.lower()
        )
        return {
            "ok": True,
            "available": logged_in,
            "workspace": _WORKSPACE.as_posix(),
            "hint": None
            if logged_in
            else "На ноуте: cursor agent login (один раз, с браузером или SSH)",
            "status_text": text.strip()[:500],
        }
    except FileNotFoundError:
        return {"ok": True, "available": False, "hint": "Нет cursor agent в PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Таймаут cursor agent status"}


def _load_sessions() -> dict[str, Any]:
    _ensure_data_dir()
    if not _SESSIONS_FILE.is_file():
        return {"sessions": []}
    try:
        return json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sessions": []}


def _save_sessions(data: dict[str, Any]) -> None:
    _ensure_data_dir()
    _SESSIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_sessions() -> dict[str, Any]:
    return {"ok": True, "sessions": _load_sessions().get("sessions", [])}


def _parse_chat_id(raw: str) -> str | None:
    raw = raw.strip()
    m = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", raw, re.I)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-f0-9-]{8,}", raw, re.I):
        return raw
    return None


def create_session(title: str = "Чат с телефона") -> dict[str, Any]:
    st = agent_status()
    if not st.get("available"):
        return {"ok": False, "error": st.get("hint", "Агент недоступен")}
    try:
        r = subprocess.run(
            ["cursor", "agent", "create-chat"],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=os.fspath(_WORKSPACE),
        )
        chat_id = _parse_chat_id((r.stdout or "") + (r.stderr or ""))
        if not chat_id:
            return {"ok": False, "error": (r.stderr or r.stdout or "create-chat failed")[:300]}
        entry = {"id": chat_id, "title": title, "created": time.time()}
        data = _load_sessions()
        data.setdefault("sessions", []).insert(0, entry)
        _save_sessions(data)
        _log.info("chat session %s", chat_id)
        return {"ok": True, "session_id": chat_id, "session": entry}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Таймаут create-chat"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def _run_agent_thread(job: _Job, message: str) -> None:
    cmd = [
        "cursor",
        "agent",
        "--print",
        "--trust",
        "--output-format",
        "text",
        "--workspace",
        os.fspath(_WORKSPACE),
        "--resume",
        job.session_id,
        message,
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=os.fspath(_WORKSPACE),
            env=os.environ.copy(),
        )
        job.proc = proc
        assert proc.stdout is not None
        for line in proc.stdout:
            with _jobs_lock:
                job.output += line
                if len(job.output) > _MAX_JOB_OUTPUT:
                    job.output = job.output[-_MAX_JOB_OUTPUT // 2 :]
        code = proc.wait(timeout=3600)
        with _jobs_lock:
            job.status = "done" if code == 0 else "error"
            if code != 0 and not job.output.strip():
                job.error = f"код выхода {code}"
    except (OSError, subprocess.SubprocessError) as exc:
        with _jobs_lock:
            job.status = "error"
            job.error = str(exc)
        _log.exception("chat job %s", job.id)
    finally:
        with _jobs_lock:
            job.proc = None


def send_message(session_id: str, message: str) -> dict[str, Any]:
    message = message.strip()
    if not message:
        return {"ok": False, "error": "Пустое сообщение"}
    st = agent_status()
    if not st.get("available"):
        return {"ok": False, "error": st.get("hint", "Агент недоступен")}

    job = _Job(id=uuid.uuid4().hex[:12], session_id=session_id)
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=_run_agent_thread, args=(job, message), daemon=True).start()
    _log.info("chat job %s -> session %s", job.id, session_id)
    return {"ok": True, "job_id": job.id}


def poll_job(job_id: str, offset: int = 0) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        chunk = job.output[offset:]
        new_offset = len(job.output)
        done = job.status in ("done", "error")
        return {
            "ok": True,
            "status": job.status,
            "chunk": chunk,
            "offset": new_offset,
            "done": done,
            "error": job.error if done else "",
        }
