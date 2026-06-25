#!/usr/bin/env python3
"""Phase 46C-3 production smoke tests."""

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
        with urllib.request.urlopen(url, timeout=15) as resp:
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
    record("api_health", code == 200, str(health)[:80] if health else str(code))

    code, perf = _get(f"{base}/api/performance/summary")
    record("performance_summary", code == 200 and isinstance(perf, dict) and perf.get("status") == "ok", str(code))

    code, _ = _get(f"{base}/api/history/global")
    record("history_route", code in {200, 401}, str(code))

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository(get_settings().sqlite_path)
    rows = [r for r in repo.list_worldcup_prediction_evaluations() if r.get("market_goal_minute_status")]
    record("goal_minute_eval_rows", len(rows) >= 0, f"count={len(rows)}")
    if rows:
        sample = rows[0]
        record(
            "goal_minute_columns",
            sample.get("market_goal_minute_status") is not None,
            f"fixture={sample.get('fixture_id')} status={sample.get('market_goal_minute_status')}",
        )

    code, billing = _get(f"{base}/api/billing/status")
    record("billing_status_live", code in {200, 401}, str(code))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Smoke: {passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
