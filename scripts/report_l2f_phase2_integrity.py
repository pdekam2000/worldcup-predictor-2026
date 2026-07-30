#!/usr/bin/env python3
"""Phase 2 integrity + stratified metrics report (read-mostly; additive JSON only)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE
from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    COHORT_HISTORICAL,
    EVAL_TABLE,
    aggregate_eval_metrics,
)
from worldcup_predictor.research.infra_l2f_forward.leakage_checks import (
    assert_prediction_before_kickoff,
    check_shadow_payloads_no_results,
)
from worldcup_predictor.research.infra_l2f_forward.true_forward_report import true_forward_summary


def _df() -> str:
    try:
        return subprocess.check_output(["df", "-h", "/"], text=True).strip().splitlines()[-1]
    except Exception:
        return "N/A"


def main() -> int:
    eval_db = Path(sys.argv[1] if len(sys.argv) > 1 else "data/evaluation/forward_prediction_tracking.db")
    fi_db = Path(sys.argv[2] if len(sys.argv) > 2 else "data/football_intelligence.db")
    out = Path(sys.argv[3] if len(sys.argv) > 3 else "artifacts/l2f_phase2_integrity.json")

    eval_conn = sqlite3.connect(str(eval_db))
    eval_conn.row_factory = sqlite3.Row
    fi_conn = sqlite3.connect(str(fi_db))
    fi_conn.row_factory = sqlite3.Row

    freeze_rows = eval_conn.execute(
        "SELECT prediction_id, fixture_id, frozen_at, lambda_home, lambda_away, freeze_status "
        "FROM frozen_predictions ORDER BY prediction_id"
    ).fetchall()
    freeze_hash = hashlib.sha256(repr([tuple(r) for r in freeze_rows]).encode()).hexdigest()

    # Leakage sample: all historical_replay eval fixtures
    fx_rows = fi_conn.execute(
        f"SELECT DISTINCT fixture_id, freeze_id FROM {EVAL_TABLE} WHERE cohort_type=?",
        (COHORT_HISTORICAL,),
    ).fetchall()
    leak_issues = []
    boundary_issues = []
    for r in fx_rows:
        fid = int(r["fixture_id"])
        leak_issues.extend(check_shadow_payloads_no_results(fi_conn, fid))
        fr = eval_conn.execute(
            "SELECT frozen_at, kickoff FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
            (fid,),
        ).fetchone()
        if fr:
            issue = assert_prediction_before_kickoff(fr["frozen_at"], fr["kickoff"])
            if issue:
                boundary_issues.append({"fixture_id": fid, "issue": issue})

    smoke_dup_fx = (1497638, 1508818, 1508819)
    non_smoke_dups = fi_conn.execute(
        f"""
        SELECT COUNT(*) FROM (
          SELECT fixture_id, model_id FROM {SHADOW_TABLE}
          WHERE fixture_id NOT IN (?,?,?)
          GROUP BY fixture_id, model_id HAVING COUNT(*) > 1
        )
        """,
        smoke_dup_fx,
    ).fetchone()[0]

    # Stratified Exact V2 SELECTED vs canonical top5 by competition
    by_league: dict[str, dict[str, float]] = {}
    join_rows = fi_conn.execute(
        f"""
        SELECT e.fixture_id, e.top5, e.canonical_top5, e.lambda_total_err
        FROM {EVAL_TABLE} e
        WHERE e.cohort_type=? AND e.model_id='EXACT_V2_SELECTED'
        """,
        (COHORT_HISTORICAL,),
    ).fetchall()
    buckets: dict[str, list] = defaultdict(list)
    for r in join_rows:
        comp = eval_conn.execute(
            "SELECT competition FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
            (int(r["fixture_id"]),),
        ).fetchone()
        league = (comp["competition"] if comp else None) or "unknown"
        buckets[league].append(r)
    for league, rows in sorted(buckets.items(), key=lambda x: -len(x[1])):
        n = len(rows)
        by_league[league] = {
            "n": n,
            "exact_v2_selected_top5": sum(float(x["top5"] or 0) for x in rows) / n,
            "canonical_top5": sum(float(x["canonical_top5"] or 0) for x in rows if x["canonical_top5"] is not None)
            / max(1, sum(1 for x in rows if x["canonical_top5"] is not None)),
            "mae_total": sum(float(x["lambda_total_err"] or 0) for x in rows) / n,
        }

    # Total-goal buckets
    by_tg: dict[str, dict[str, float]] = {}
    tg_buckets: dict[str, list] = defaultdict(list)
    for r in join_rows:
        ar = eval_conn.execute(
            "SELECT actual_home_goals, actual_away_goals FROM actual_results WHERE fixture_id=?",
            (int(r["fixture_id"]),),
        ).fetchone()
        if not ar or ar["actual_home_goals"] is None:
            key = "unknown"
        else:
            tg = int(ar["actual_home_goals"]) + int(ar["actual_away_goals"])
            if tg <= 1:
                key = "0-1"
            elif tg == 2:
                key = "2"
            elif tg == 3:
                key = "3"
            else:
                key = "4+"
        tg_buckets[key].append(r)
    for key, rows in sorted(tg_buckets.items()):
        n = len(rows)
        by_tg[key] = {
            "n": n,
            "exact_v2_selected_top5": sum(float(x["top5"] or 0) for x in rows) / n,
            "canonical_top5": sum(float(x["canonical_top5"] or 0) for x in rows if x["canonical_top5"] is not None)
            / max(1, sum(1 for x in rows if x["canonical_top5"] is not None)),
        }

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "disk": _df(),
        "freeze_row_count": len(freeze_rows),
        "freeze_content_hash": freeze_hash,
        "leakage_payload_issues": leak_issues[:50],
        "leakage_payload_issue_count": len(leak_issues),
        "boundary_issues": boundary_issues[:50],
        "boundary_issue_count": len(boundary_issues),
        "non_smoke_duplicate_groups": non_smoke_dups,
        "smoke_duplicate_fixtures_known": list(smoke_dup_fx),
        "metrics_historical": aggregate_eval_metrics(fi_conn, cohort_type=COHORT_HISTORICAL),
        "metrics_combined_non_promotion": aggregate_eval_metrics(fi_conn, cohort_type=None),
        "by_league_exact_v2_selected": by_league,
        "by_total_goals_exact_v2_selected": by_tg,
        "true_forward": true_forward_summary(fi_conn),
        "shadow_row_counts": {
            "lambda_v2": fi_conn.execute(
                f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'LAMBDA_V2_%'"
            ).fetchone()[0],
            "exact_v2": fi_conn.execute(
                f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'EXACT_V2_%'"
            ).fetchone()[0],
        },
        "jobs": dict(
            fi_conn.execute("SELECT status, COUNT(*) FROM l2f_forward_shadow_jobs GROUP BY status").fetchall()
        ),
        "historical_eval_fixtures": len(fx_rows),
        "no_model_promotion": True,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(out), "leakage": len(leak_issues), "boundary": len(boundary_issues), "non_smoke_dups": non_smoke_dups}, indent=2))
    return 0 if not leak_issues and not boundary_issues and non_smoke_dups == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
