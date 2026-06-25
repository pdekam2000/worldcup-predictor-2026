#!/usr/bin/env python3
"""Phase 48A production smoke tests."""

from __future__ import annotations

import json
import runpy
import sys
import urllib.error
import urllib.request
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _get(url: str) -> tuple[int, dict | str]:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def main() -> int:
    base = "http://127.0.0.1:8000"
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))

    code, health = _get(f"{base}/api/health")
    record("api_health", code == 200, str(health)[:40] if health else str(code))

    code, perf = _get(f"{base}/api/performance/summary")
    record("performance_summary", code == 200 and isinstance(perf, dict) and perf.get("version") == "v2", str(code))

    code, mon = _get(f"{base}/api/performance/monitoring")
    record(
        "performance_monitoring",
        code == 200 and isinstance(mon, dict) and "rule_a_monitoring" in mon,
        str(code),
    )

    code, _ = _get(f"{base}/api/history/global")
    record("history_route", code in {200, 401}, str(code))

    code, _ = _get(f"{base}/api/billing/status")
    record("billing_route", code in {200, 401}, str(code))

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"Smoke: {passed}/{len(checks)} PASS")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
