#!/usr/bin/env python3
"""HTTPS E2E for worker + broad listing hotfix."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("GPT_ACTIONS_BASE_URL", "https://footballpredictor.it.com/api/gpt-actions/v1")
KEY = os.environ.get("GPT_ACTIONS_API_KEY", "")


def req(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    r = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(r, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if not KEY:
        print("GPT_ACTIONS_API_KEY missing", file=sys.stderr)
        return 1
    out: dict = {}
    out["list"] = req("GET", "/matches/list?date=2026-07-10&timezone=Europe/Vienna&listing_filter=all")
    out["discover_owner"] = req("GET", "/matches/discover?date=2026-07-10&timezone=Europe/Vienna&scope=owner")
    out["discover_production"] = req("GET", "/matches/discover?date=2026-07-10&timezone=Europe/Vienna&scope=production")
    job = req(
        "POST",
        "/prediction-jobs",
        {
            "date": "2026-07-10",
            "timezone": "Europe/Vienna",
            "fixture_ids": [1581821],
            "prediction_scope": "production",
            "include_all_predictions": True,
            "select_best": 1,
        },
    )
    out["job_create"] = {"job_id": job.get("job_id"), "status": job.get("status")}
    jid = job["job_id"]
    final = None
    for i in range(30):
        time.sleep(2)
        poll = req("GET", f"/prediction-jobs/{jid}")
        out["last_poll"] = {"n": i + 1, "status": poll.get("status"), "error": poll.get("error")}
        if poll.get("status") in ("completed", "partial", "failed"):
            final = poll
            break
    out["job_final_status"] = final.get("status") if final else "timeout"
    out["job_error"] = final.get("error") if final else "timeout"
    preds = (final.get("result") or {}).get("predictions") or [] if final else []
    if preds:
        wde = preds[0].get("wde") or {}
        ecse = preds[0].get("ecse") or {}
        tops = [(ecse.get(f"top{i}") or {}).get("score") for i in range(1, 6)]
        out["spain_belgium"] = {
            "wde_decision": wde.get("decision_pick"),
            "ft_marginal": wde.get("probability_argmax"),
            "hda": [wde.get("home_probability"), wde.get("draw_probability"), wde.get("away_probability")],
            "ecse_top5": tops,
            "wde_confidence": wde.get("confidence"),
        }
    broad_count = out["list"].get("count")
    discover_count = out["discover_owner"].get("count")
    out["pass"] = {
        "broad_gt_discover": broad_count > discover_count if broad_count and discover_count is not None else False,
        "job_completed": out["job_final_status"] in ("completed", "partial"),
        "no_tier_unbound": out["job_error"] != "cannot access local variable 'tier' where it is not associated with a value",
    }
    print(json.dumps(out, indent=2, default=str))
    ok = out["pass"]["job_completed"] and out["pass"]["no_tier_unbound"]
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        raise SystemExit(1)
