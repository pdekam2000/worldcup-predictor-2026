#!/usr/bin/env python3
"""Controlled MCP production smoke tests (owner)."""

from __future__ import annotations

import json
import sys
import time

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.mcp_server import runtime
from worldcup_predictor.mcp_server.tools import health


def _sample_fixture_id() -> int | None:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT f.fixture_id
            FROM fixtures f
            JOIN worldcup_stored_predictions w ON w.fixture_id = f.fixture_id
            JOIN ecse_prediction_snapshots e ON e.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0
            ORDER BY f.kickoff_utc DESC
            LIMIT 1
            """
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def main() -> int:
    out: dict = {"tests": []}

    t0 = time.perf_counter()
    h = health.server_health()
    out["tests"].append(
        {
            "name": "server_health",
            "ok": h.get("service_worldcup_api") == "active",
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "sample": {k: h[k] for k in ("hostname", "service_worldcup_api", "mcp_version")},
        }
    )

    t0 = time.perf_counter()
    ms = runtime.model_status()
    out["tests"].append(
        {
            "name": "model_status",
            "ok": ms.get("db_connectivity"),
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "wde_available": ms.get("wde_available"),
            "ecse_available": ms.get("ecse_available"),
        }
    )

    sample_fid = _sample_fixture_id()
    t0 = time.perf_counter()
    if sample_fid:
        conn = connect(get_settings().sqlite_path)
        try:
            row = conn.execute(
                "SELECT home_team, away_team, date(kickoff_utc) FROM fixtures WHERE fixture_id=?",
                (sample_fid,),
            ).fetchone()
        finally:
            conn.close()
        home, away, kick_date = row[0], row[1], row[2]
        resolved = runtime.resolve_fixtures(
            [{"home_team": home, "away_team": away, "date": str(kick_date)}]
        )
    else:
        resolved = runtime.resolve_fixtures(
            [{"home_team": "France", "away_team": "Morocco", "date": "2026-07-09"}]
        )
    fid = resolved[0].get("fixture_id") if resolved else None
    if fid is None and sample_fid:
        fid = sample_fid
    out["tests"].append(
        {
            "name": "resolve_fixtures",
            "ok": fid is not None,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "result": resolved[0] if resolved else None,
        }
    )

    if fid:
        t0 = time.perf_counter()
        audit = runtime.odds_freshness_audit([int(fid)])
        out["tests"].append(
            {
                "name": "odds_freshness_audit",
                "ok": bool(audit),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "result": audit[0],
            }
        )

        t0 = time.perf_counter()
        pred = runtime.run_fixture_prediction(int(fid), refresh_if_stale=False)
        out["tests"].append(
            {
                "name": "run_fixture_prediction",
                "ok": (pred.get("quality") or {}).get("status") in ("OK", "PARTIAL", "BLOCKED"),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "status": (pred.get("quality") or {}).get("status"),
                "wde_pick": (pred.get("wde") or {}).get("prediction"),
                "ecse_top1": ((pred.get("ecse") or {}).get("top_scores") or [{}])[0],
            }
        )

    out["all_ok"] = all(t.get("ok") for t in out["tests"])
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
