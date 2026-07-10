#!/usr/bin/env python3
"""Production HTTPS GPT Actions end-to-end retest (read-only)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("GPT_ACTIONS_BASE_URL", "https://footballpredictor.it.com/api/gpt-actions/v1")
KEY = os.environ.get("GPT_ACTIONS_API_KEY", "")


def _req(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if not KEY:
        print("GPT_ACTIONS_API_KEY not set", file=sys.stderr)
        return 1

    print("=== 1 getSystemStatus ===")
    status = _req("GET", "/system/status")
    print("service", status.get("service"), "health", (status.get("health") or {}).get("status"))

    print("=== 2 discoverTodayMatches ===")
    disc = _req("GET", "/matches/discover?date=2026-07-10&timezone=Europe/Vienna")
    sb = [m for m in disc.get("matches") or [] if int(m.get("fixture_id") or 0) == 1581821]
    print("spain_belgium_found", bool(sb))

    print("=== 4 startPredictionJob ===")
    job = _req(
        "POST",
        "/prediction-jobs",
        {
            "date": "2026-07-10",
            "timezone": "Europe/Vienna",
            "fixture_ids": [1581821],
            "include_all_predictions": True,
            "select_best": 3,
        },
    )
    job_id = job["job_id"]
    print("job_id", job_id, "status", job.get("status"))

    print("=== 5 getPredictionJob (same job_id) ===")
    final = None
    for i in range(15):
        time.sleep(2)
        poll = _req("GET", f"/prediction-jobs/{job_id}")
        st = poll.get("status")
        print(f"poll {i+1} status={st}")
        if st in ("completed", "partial", "failed"):
            final = poll
            break
    if not final:
        print("FAIL: job did not complete")
        return 1

    preds = (final.get("result") or {}).get("predictions") or []
    wde = preds[0].get("wde") or {} if preds else {}
    ecse = preds[0].get("ecse") or {} if preds else {}
    print("WDE decision", wde.get("decision_pick"), wde.get("prediction"))
    print("FT marginal", wde.get("probability_argmax"))
    print("H/D/A", wde.get("home_probability"), wde.get("draw_probability"), wde.get("away_probability"))
    print("confidence", wde.get("confidence"))
    print("provenance", wde.get("wde_execution_status"), wde.get("wde_result_source"), wde.get("wde_warning"))
    tops = [(ecse.get(f"top{i}") or {}).get("score") for i in range(1, 6)]
    print("ECSE tops", tops)

    ok_wde = wde.get("decision_pick") == "draw" and wde.get("probability_argmax") == "home_win"
    ok_ecse = tops[:5] == ["2-0", "1-0", "3-0", "2-1", "1-1"]

    print("=== 6 getLatestPredictionReport ===")
    latest = _req("GET", "/reports/latest")
    print("found", latest.get("found"), "name", latest.get("report_name"), "type", latest.get("report_type"))
    ok_latest = latest.get("found") and "CONNECTION_GUIDE" not in (latest.get("report_name") or "")

    print("=== 7 getPredictionReportByDate ===")
    by_date = _req("GET", "/reports/2026-07-10")
    print("found", by_date.get("found"), "name", by_date.get("report_name"), "type", by_date.get("report_type"))
    ok_date = by_date.get("found") is True

    if ok_wde and ok_ecse and ok_latest and ok_date:
        print("\nHTTPS E2E RETEST: PASSED")
        print("STATUS = GPT_ACTIONS_END_TO_END_PARITY_RESTORED")
        return 0

    print("\nHTTPS E2E RETEST: FAILED", {"wde": ok_wde, "ecse": ok_ecse, "latest": ok_latest, "date": ok_date})
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        raise SystemExit(1)
