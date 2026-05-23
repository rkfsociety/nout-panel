#!/usr/bin/env python3
"""Smoke-тест живучести nout-panel — сервис должен быть уже запущен."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

# Базовый URL: PANEL_URL или localhost и PANEL_PORT
_DEFAULT_PORT = os.environ.get("PANEL_PORT", "8765")
BASE_URL = os.environ.get("PANEL_URL", f"http://127.0.0.1:{_DEFAULT_PORT}").rstrip("/")
TIMEOUT_SEC = float(os.environ.get("PANEL_SMOKE_TIMEOUT", "5"))


def _get(path: str) -> tuple[int, dict[str, str], bytes]:
    """GET-запрос; возвращает код, заголовки и тело."""
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Accept": "*/*"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, headers, resp.read()


def _get_json(path: str) -> Any:
    """GET JSON с проверкой статуса 200."""
    status, _headers, body = _get(path)
    if status != 200:
        raise AssertionError(f"{path}: HTTP {status}")
    return json.loads(body.decode("utf-8"))


def _check_status() -> None:
    """API /api/status отвечает и ok=true."""
    data = _get_json("/api/status")
    assert data.get("ok") is True, "status: ok != true"
    assert data.get("hostname"), "status: нет hostname"
    print("  OK /api/status", data.get("hostname"))


def _check_metrics() -> None:
    """API /api/metrics — основные поля и мониторинг процесса панели."""
    data = _get_json("/api/metrics")
    assert data.get("ok") is True, "metrics: ok != true"
    assert "memory" in data, "metrics: нет memory"
    assert "history" in data, "metrics: нет history"
    panel = data.get("panel")
    if panel is None:
        print("  OK /api/metrics (поле panel нет — обновите панель)")
        return
    assert panel.get("available") is True, "metrics: panel недоступен"
    assert panel.get("pid"), "metrics: нет panel.pid"
    print("  OK /api/metrics", f"panel pid={panel.get('pid')} rss={panel.get('rss_mb')} МБ")


def _check_html(path: str) -> None:
    """Главная и статика отдаются с ожидаемым типом."""
    status, headers, body = _get(path)
    assert status == 200, f"{path}: HTTP {status}"
    ctype = headers.get("content-type", "")
    if path.endswith(".js"):
        assert "javascript" in ctype, f"{path}: неверный Content-Type"
    elif path.endswith(".css"):
        assert "css" in ctype, f"{path}: неверный Content-Type"
    else:
        assert "text/html" in ctype, f"{path}: неверный Content-Type"
        assert len(body) > 100, f"{path}: пустой ответ"
    cache = headers.get("cache-control", "")
    if path.endswith((".js", ".css")):
        assert "max-age" in cache, f"{path}: нет Cache-Control для статики"
    elif path in ("/", "/index.html"):
        assert "no-cache" in cache, f"{path}: HTML должен быть no-cache"
    print(f"  OK {path}")


def main() -> int:
    print(f"Smoke-тест: {BASE_URL}")
    tests = [
        ("status", _check_status),
        ("metrics", _check_metrics),
        ("index", lambda: _check_html("/")),
        ("nav.js", lambda: _check_html("/nav.js")),
        ("nav.css", lambda: _check_html("/nav.css")),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except (AssertionError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  FAIL {name}: {exc}", file=sys.stderr)
            failed += 1
    if failed:
        print(f"\nПровалено: {failed}/{len(tests)}", file=sys.stderr)
        return 1
    print(f"\nВсе проверки пройдены ({len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
