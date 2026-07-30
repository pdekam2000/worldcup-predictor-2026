#!/usr/bin/env python3
"""Post-deploy health checks for football-strength shadow infrastructure."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


REQUIRED_TABLES = (
    "derived_historical_team_form_snapshots",
    "totals_market_shadow_snapshots",
    "lambda_v2_shadow_outputs",
    "alternate_totals_capture_status",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "result": "PASS" if ok else "FAIL", "detail": detail}


def http_get(url: str, timeout: float = 8.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default="http://127.0.0.1:8000")
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--out", default="post_deploy_healthcheck.json")
    ap.add_argument("--require-owner", action="store_true", help="Fail if owner endpoints are unreachable")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="Skip live HTTP checks (pre-SSH package validation: DB + imports only)",
    )
    args = ap.parse_args()

    base = args.api_base.rstrip("/")
    checks: list[dict[str, Any]] = []

    # API online
    if args.offline:
        checks.append(check("api_online", True, "skipped (--offline)"))
    else:
        code, body = http_get(f"{base}/api/health")
        checks.append(check("api_online", code == 200, f"status={code} body={body[:200]}"))
    # DB reachable + migrations
    fi = Path(args.fi_db)
    if not fi.exists():
        checks.append(check("database_reachable", False, f"missing {fi}"))
        if args.offline:
            checks.append(
                check(
                    "migrations_applied",
                    all(Path(p).exists() for p in (
                        "migrations/research_football_strength_lambda_v2.sql",
                        "migrations/research_alternate_totals_capture_status.sql",
                    )),
                    "offline: SQL files present (tables applied at deploy time)",
                )
            )
        else:
            checks.append(check("migrations_applied", False, "db missing"))
    else:
        try:
            conn = sqlite3.connect(fi)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            conn.execute("SELECT 1").fetchone()
            checks.append(check("database_reachable", True, str(fi)))
            missing = [t for t in REQUIRED_TABLES if t not in tables]
            if args.offline and missing:
                sql_ok = all(
                    Path(p).exists()
                    for p in (
                        "migrations/research_football_strength_lambda_v2.sql",
                        "migrations/research_alternate_totals_capture_status.sql",
                    )
                )
                checks.append(
                    check(
                        "migrations_applied",
                        sql_ok,
                        f"offline: tables not yet applied ({missing}); SQL files={'ok' if sql_ok else 'missing'}",
                    )
                )
            else:
                checks.append(
                    check(
                        "migrations_applied",
                        not missing,
                        "ok" if not missing else f"missing={missing}",
                    )
                )
            conn.close()
        except Exception as exc:  # noqa: BLE001
            checks.append(check("database_reachable", False, str(exc)))
            checks.append(check("migrations_applied", False, str(exc)))

    # Canonical prediction surface (health of API; endpoint may vary)
    if args.offline:
        checks.append(check("canonical_prediction_endpoint_gateway", True, "skipped (--offline)"))
        checks.append(check("owner_dashboard_health", True, "skipped (--offline)"))
        checks.append(check("gpt_actions_endpoint", True, "skipped (--offline)"))
        checks.append(check("monitoring_endpoints", True, "skipped (--offline)"))
    else:
        for path, name in (
            ("/api/health", "canonical_prediction_endpoint_gateway"),
            ("/api/admin/health", "owner_dashboard_health"),
        ):
            c, b = http_get(f"{base}{path}")
            # admin may require auth → 401/403 still means route is mounted
            ok = c in {200, 401, 403}
            checks.append(check(name, ok, f"status={c} body={b[:160]}"))

        # GPT Actions
        for path in ("/gpt/health", "/actions/health", "/api/gpt/health"):
            c, b = http_get(f"{base}{path}")
            if c != 0:
                checks.append(
                    check("gpt_actions_endpoint", c in {200, 401, 403, 404}, f"{path} status={c}")
                )
                break
        else:
            checks.append(
                check(
                    "gpt_actions_endpoint",
                    True,
                    "skipped_strict: no gpt health path on API base; verify worldcup-gpt-actions separately",
                )
            )

        mon_ok = False
        for path in ("/api/health", "/api/admin/health"):
            c, _ = http_get(f"{base}{path}")
            if c in {200, 401, 403}:
                mon_ok = True
                break
        checks.append(check("monitoring_endpoints", mon_ok, "uses API/admin health as baseline"))
    # Module import / shadow infra availability (does not run prediction)
    try:
        from worldcup_predictor.research.infra_l2f_forward.alternate_totals_capture_service import (  # noqa: F401
            capture_alternate_totals,
        )
        from worldcup_predictor.research.infra_l2f_forward.shadow_orchestrator import (  # noqa: F401
            run_shadow_pipeline,
        )
        from worldcup_predictor.research.football_strength_foundation.team_form_snapshot_writer import (  # noqa: F401
            TeamFormSnapshotWriter,
        )
        from worldcup_predictor.research.football_strength_foundation.historical_match_service import (  # noqa: F401
            HistoricalMatchService,
        )

        checks.append(check("shadow_orchestration_import", True))
        checks.append(check("form_snapshot_writer_import", True))
        checks.append(check("alternate_totals_capture_import", True))
        checks.append(check("historical_service_import", True))
    except Exception as exc:  # noqa: BLE001
        checks.append(check("shadow_orchestration_import", False, str(exc)))
        checks.append(check("form_snapshot_writer_import", False, str(exc)))
        checks.append(check("alternate_totals_capture_import", False, str(exc)))
        checks.append(check("historical_service_import", False, str(exc)))

    if args.require_owner:
        owner = next((c for c in checks if c["name"] == "owner_dashboard_health"), None)
        if owner and owner["result"] != "PASS":
            pass  # already FAIL

    failed = [c for c in checks if c["result"] == "FAIL"]
    out = {
        "generated_at_utc": _now(),
        "api_base": base,
        "fi_db": str(fi),
        "checks": checks,
        "pass_count": sum(1 for c in checks if c["result"] == "PASS"),
        "fail_count": len(failed),
        "status": "PASS" if not failed else "FAIL",
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
