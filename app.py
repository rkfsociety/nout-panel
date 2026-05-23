#!/usr/bin/env python3
"""Веб-панель домашнего ноута — мониторинг CPU, RAM, дисков."""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from metrics_collector import get_metrics, start_collector
from panel_log import setup_logging

# Логи HTTP и старта — в файл, не в консоль
_log = setup_logging("nout-panel")

# Порт из окружения (install.sh → /etc/nout-panel/env)
HOST = "0.0.0.0"
PORT = int(os.environ.get("PANEL_PORT", "8765"))

STATIC_DIR = Path(__file__).resolve().parent / "static"


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
        # Узнать исходящий IP без привязки к конкретной подсети
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("1.1.1.1", 80))
                ips.append(s.getsockname()[0])
        except OSError:
            ips.append("127.0.0.1")
    return ips


def _status_payload() -> dict:
    """JSON: имя хоста и IP подставляются на клиенте с этой машины."""
    return {
        "ok": True,
        "hostname": socket.gethostname(),
        "ips": _local_ips(),
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "panel_version": "0.3.1",
    }


class PanelHandler(BaseHTTPRequestHandler):
    """HTTP: главная, /api/status, /api/metrics."""

    server_version = "NoutPanel/0.3.1"

    def log_message(self, fmt: str, *args) -> None:
        # Запросы в лог-файл
        _log.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), fmt % args)

    def _send_json(self, data: dict, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404, "Not Found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/status":
            self._send_json(_status_payload())
            return

        if path == "/api/metrics":
            self._send_json(get_metrics())
            return

        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path == "/chart.umd.min.js":
            self._send_file(STATIC_DIR / "chart.umd.min.js", "application/javascript; charset=utf-8")
            return

        self.send_error(404, "Not Found")


def main() -> None:
    start_collector()
    httpd = ThreadingHTTPServer((HOST, PORT), PanelHandler)
    _log.info("Nout panel started: http://%s:%s/", _local_ips()[0], PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log.info("Nout panel stopped (keyboard)")
    except Exception:
        _log.exception("Nout panel fatal error")
        raise


if __name__ == "__main__":
    main()
