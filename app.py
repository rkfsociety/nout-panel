#!/usr/bin/env python3
"""Веб-панель домашнего ноута — мониторинг и удалённое управление в LAN."""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import agent_chat
import file_manager
import panel_control
import panel_settings
import power_control
import screen_capture
import terminal_pty
from metrics_collector import get_metrics, start_collector
try:
    from panel_log import setup_logging
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def setup_logging(name: str = "nout-panel") -> logging.Logger:
        return logging.getLogger(name)

_log = setup_logging("nout-panel")

HOST = "0.0.0.0"
PORT = int(os.environ.get("PANEL_PORT", "8765"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
PANEL_VERSION = "0.5.0"

# Кэш в браузере: HTML всегда свежий, статика .js/.css — на неделю
_CACHE_HTML = "no-cache"
_CACHE_STATIC = "public, max-age=604800"


def _local_ips() -> list[str]:
    """Список IPv4-адресов машины (кроме loopback)."""
    ips: list[str] = []
    try:
        for line in subprocess.check_output(["hostname", "-I"], text=True).split():
            if "." in line:
                ips.append(line.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if not ips:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("1.1.1.1", 80))
                ips.append(s.getsockname()[0])
        except OSError:
            ips.append("127.0.0.1")
    return ips


def _status_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "hostname": socket.gethostname(),
        "ips": _local_ips(),
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "panel_version": PANEL_VERSION,
        "remote": True,
        "chat": True,
    }


def _parse_multipart_file(body: bytes, content_type: str) -> tuple[str, bytes] | None:
    """Извлечь поле file из multipart/form-data."""
    m = re.search(r"boundary=([^;\s]+)", content_type)
    if not m:
        return None
    boundary = m.group(1).strip('"').encode()
    for part in body.split(b"--" + boundary):
        if b"\r\n\r\n" not in part or b'name="file"' not in part:
            continue
        header, data = part.split(b"\r\n\r\n", 1)
        data = data.rstrip(b"\r\n")
        if data.endswith(b"--"):
            data = data[:-2].rstrip(b"\r\n")
        filename = "upload.bin"
        if b'filename="' in header:
            filename = header.split(b'filename="', 1)[1].split(b'"', 1)[0].decode("utf-8", "replace")
        return filename, data
    return None


class PanelHandler(BaseHTTPRequestHandler):
    """HTTP: мониторинг, терминал, файлы, питание, экран."""

    server_version = f"NoutPanel/{PANEL_VERSION}"

    def log_message(self, fmt: str, *args) -> None:
        _log.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), fmt % args)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _read_json(self) -> dict[str, Any]:
        raw = self._read_body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _query(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.path).query)

    def _path(self) -> str:
        return urlparse(self.path).path.rstrip("/") or "/"

    def _send_json(self, data: dict[str, Any], code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str, download_name: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def _static_cache_control(self, path: Path, content_type: str) -> str:
        """Заголовок Cache-Control для HTML и статики."""
        name = path.name.lower()
        if content_type.startswith("text/html") or name.endswith(".html"):
            return _CACHE_HTML
        if name.endswith((".js", ".css")):
            return _CACHE_STATIC
        return _CACHE_HTML

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404, "Not Found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", self._static_cache_control(path, content_type))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _q1(self, key: str) -> str | None:
        vals = self._query().get(key)
        return vals[0] if vals else None

    # --- GET ---

    def do_GET(self) -> None:
        path = self._path()

        if path == "/api/status":
            self._send_json(_status_payload())
            return
        if path == "/api/metrics":
            self._send_json(get_metrics())
            return

        if path == "/api/files/list":
            self._send_json(file_manager.list_dir(self._q1("path")))
            return
        if path == "/api/files/download":
            fp = self._q1("path")
            if not fp:
                self._send_json({"ok": False, "error": "path required"}, 400)
                return
            got = file_manager.read_file_bytes(fp)
            if not got:
                self.send_error(404, "Not Found")
                return
            data, name = got
            self._send_bytes(data, "application/octet-stream", name)
            return

        if path == "/api/terminal/poll":
            sid = self._q1("session")
            offset = int(self._q1("offset") or "0")
            if not sid:
                self._send_json({"ok": False, "error": "session required"}, 400)
                return
            out = terminal_pty.poll_output(sid, offset)
            if out is None:
                self._send_json({"ok": False, "error": "session not found"}, 404)
                return
            self._send_json({"ok": True, **out})
            return

        if path == "/api/screen/info":
            self._send_json(screen_capture.capture_info())
            return
        if path == "/api/chat/status":
            self._send_json(agent_chat.agent_status())
            return
        if path == "/api/chat/sessions":
            self._send_json(agent_chat.list_sessions())
            return
        if path == "/api/panel/config":
            self._send_json(panel_settings.get_config())
            return
        if path == "/api/panel/info":
            self._send_json(panel_settings.panel_info(PANEL_VERSION))
            return
        if path == "/api/panel/logs":
            lines = int(self._q1("lines") or "200")
            self._send_json(panel_settings.tail_logs(lines))
            return

        if path == "/api/chat/poll":
            jid = self._q1("job")
            offset = int(self._q1("offset") or "0")
            if not jid:
                self._send_json({"ok": False, "error": "job required"}, 400)
                return
            out = agent_chat.poll_job(jid, offset)
            if out is None:
                self._send_json({"ok": False, "error": "job not found"}, 404)
                return
            self._send_json(out)
            return

        if path == "/api/screen/capture":
            got = screen_capture.capture_png()
            if not got:
                self._send_json({"ok": False, "error": "Скриншот недоступен"}, 503)
                return
            data, ctype = got
            self._send_bytes(data, ctype)
            return

        static_map = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/remote": ("remote.html", "text/html; charset=utf-8"),
            "/remote.html": ("remote.html", "text/html; charset=utf-8"),
            "/chat": ("chat.html", "text/html; charset=utf-8"),
            "/chat.html": ("chat.html", "text/html; charset=utf-8"),
            "/settings": ("settings.html", "text/html; charset=utf-8"),
            "/settings.html": ("settings.html", "text/html; charset=utf-8"),
            "/chart.umd.min.js": ("chart.umd.min.js", "application/javascript; charset=utf-8"),
            "/xterm.min.js": ("xterm.min.js", "application/javascript; charset=utf-8"),
            "/xterm.min.css": ("xterm.min.css", "text/css; charset=utf-8"),
            "/nav.css": ("nav.css", "text/css; charset=utf-8"),
            "/nav.js": ("nav.js", "application/javascript; charset=utf-8"),
        }
        if path in static_map:
            name, ctype = static_map[path]
            self._send_file(STATIC_DIR / name, ctype)
            return

        self.send_error(404, "Not Found")

    # --- POST ---

    def do_POST(self) -> None:
        path = self._path()
        ctype = self.headers.get("Content-Type", "")

        try:
            if path == "/api/terminal/session":
                sid = terminal_pty.create_session()
                self._send_json({"ok": True, "session": sid})
                return

            if path == "/api/terminal/write":
                body = self._read_json()
                ok = terminal_pty.write_input(body.get("session", ""), body.get("data", ""))
                self._send_json({"ok": ok})
                return

            if path == "/api/terminal/resize":
                body = self._read_json()
                sess = terminal_pty.get_session(body.get("session", ""))
                if not sess:
                    self._send_json({"ok": False, "error": "session not found"}, 404)
                    return
                sess.resize(int(body.get("cols", 80)), int(body.get("rows", 24)))
                self._send_json({"ok": True})
                return

            if path == "/api/terminal/close":
                body = self._read_json()
                ok = terminal_pty.close_session(body.get("session", ""))
                self._send_json({"ok": ok})
                return

            if path == "/api/files/upload":
                dir_path = self._q1("path")
                if "multipart/form-data" in ctype:
                    raw = self._read_body()
                    parsed = _parse_multipart_file(raw, ctype)
                    if not parsed:
                        self._send_json({"ok": False, "error": "Нет файла"}, 400)
                        return
                    filename, data = parsed
                    self._send_json(file_manager.save_upload(dir_path or "", data, filename))
                    return
                body = self._read_json()
                import base64

                data = base64.b64decode(body.get("data", ""))
                self._send_json(
                    file_manager.save_upload(
                        dir_path or body.get("path", ""),
                        data,
                        body.get("filename", "upload.bin"),
                    )
                )
                return

            if path == "/api/files/delete":
                body = self._read_json()
                self._send_json(file_manager.delete_path(body.get("path", "")))
                return

            if path == "/api/chat/session":
                body = self._read_json()
                self._send_json(agent_chat.create_session(body.get("title", "Чат с телефона")))
                return

            if path == "/api/chat/send":
                body = self._read_json()
                sid = body.get("session_id", "")
                if not sid:
                    created = agent_chat.create_session()
                    if not created.get("ok"):
                        self._send_json(created, 400)
                        return
                    sid = created["session_id"]
                sent = agent_chat.send_message(sid, body.get("message", ""))
                if sent.get("ok"):
                    sent["session_id"] = sid
                self._send_json(sent)
                return

            if path == "/api/power":
                body = self._read_json()
                self._send_json(
                    power_control.run_power(body.get("action", ""), body.get("confirm", ""))
                )
                return

            if path == "/api/panel/restart":
                body = self._read_json()
                self._send_json(panel_control.restart_panel(body.get("confirm", "")))
                return

            if path == "/api/panel/config":
                body = self._read_json()
                updates = body.get("values") or body.get("updates") or {}
                apply = bool(body.get("apply", True))
                self._send_json(panel_settings.save_config(updates, apply))
                return

            if path == "/api/panel/apply":
                self._send_json(panel_settings.apply_config())
                return

            self.send_error(404, "Not Found")
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON"}, 400)
        except (ValueError, TypeError, OSError, KeyError) as exc:
            _log.exception("POST %s: %s", path, exc)
            self._send_json({"ok": False, "error": str(exc)}, 500)


def main() -> None:
    start_collector()
    httpd = ThreadingHTTPServer((HOST, PORT), PanelHandler)
    _log.info(
        "Nout panel %s: http://%s:%s/ (remote: /remote, chat: /chat)",
        PANEL_VERSION,
        _local_ips()[0],
        PORT,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log.info("Nout panel stopped (keyboard)")


if __name__ == "__main__":
    main()
