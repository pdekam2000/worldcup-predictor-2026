#!/usr/bin/env python3
"""PHASE EURO-A2 — Validate UEFA result backfill repair."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.data_import.european_fixture_feed import verify_domestic_results
from worldcup_predictor.data_import.european_result_backfill import list_missing_result_fixtures
from worldcup_predictor.integrations.fixture_api_parser import FINISHED_STATUSES

SUMMARY_PATH = ROOT / "artifacts" / "euro_a2_result_backfill_repair_summary.json"
AUDIT_PATH = ROOT / "artifacts" / "euro_a2_missing_uefa_results_audit.json"
MIN_CONFIDENCE = 0.88


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    checks: list[dict] = []

    finished_statuses = tuple(FINISHED_STATUSES) + ("FINISHED", "AWD", "WO", "COMPLETED")
    ph = ",".join("?" for _ in finished_statuses)

    # No international mislabels
    bad_intl = repo._conn.execute(
        "SELECT COUNT(*) AS c FROM fixtures WHERE competition_key = 'international'"
    ).fetchone()["c"]
    checks.append(_check("no_international_fixture_keys", int(bad_intl) == 0, f"rows={bad_intl}"))

    # competition_key preserved on results
    for key in UEFA_CUP_KEYS:
        wrong = repo._conn.execute(
            """
            SELECT COUNT(*) AS c FROM fixture_results
            WHERE competition_key = ? AND fixture_id IN (
                SELECT fixture_id FROM fixtures WHERE competition_key != ?
            )
            """,
            (key, key),
        ).fetchone()["c"]
        checks.append(_check(f"competition_key_preserved_{key}", int(wrong) == 0))

    # No duplicate fixture_results
    dup = repo._conn.execute(
        "SELECT fixture_id, COUNT(*) AS c FROM fixture_results GROUP BY fixture_id HAVING c > 1"
    ).fetchall()
    checks.append(_check("no_duplicate_fixture_results", len(dup) == 0, f"groups={len(dup)}"))

    # Only finished fixtures have results (UEFA)
    non_finished_with_results = repo._conn.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM fixture_results r
        INNER JOIN fixtures f ON f.fixture_id = r.fixture_id
        WHERE f.competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
          AND UPPER(COALESCE(f.status, '')) NOT IN ({ph})
        """,
        (*UEFA_CUP_KEYS, *finished_statuses),
    ).fetchone()["c"]
    checks.append(_check("only_finished_fixtures_have_results", int(non_finished_with_results) == 0))

    # Results have goals
    null_goals = repo._conn.execute(
        f"""
        SELECT COUNT(*) AS c FROM fixture_results
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
          AND (home_goals IS NULL OR away_goals IS NULL)
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("no_fake_null_goal_results", int(null_goals) == 0))

    # outcome_source tagged for euro_a2 backfills
    tagged = repo._conn.execute(
        f"""
        SELECT COUNT(*) AS c FROM fixture_results
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
          AND outcome_source LIKE 'euro_a2|%'
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("euro_a2_outcome_source_present", int(tagged) > 0, f"tagged={tagged}"))

    # Low-confidence not persisted (outcome_source confidence parse)
    low_conf = repo._conn.execute(
        f"""
        SELECT outcome_source FROM fixture_results
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
          AND outcome_source LIKE 'euro_a2|%'
        """,
        UEFA_CUP_KEYS,
    ).fetchall()
    bad_conf = 0
    for row in low_conf:
        parts = str(row["outcome_source"] or "").split("|")
        if len(parts) >= 4:
            try:
                conf = float(parts[3])
                if conf < MIN_CONFIDENCE:
                    bad_conf += 1
            except ValueError:
                pass
    checks.append(_check("low_confidence_not_persisted", bad_conf == 0, f"bad={bad_conf}"))

    # PL/Bundesliga unchanged
    for key in ("premier_league", "bundesliga"):
        v = verify_domestic_results(key, settings=settings, sample_size=20)
        checks.append(_check(f"domestic_results_intact_{key}", bool(v.get("passed"))))

    # No predictions
    ecse = repo._conn.execute(
        f"""
        SELECT COUNT(*) AS c FROM ecse_prediction_snapshots
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("no_ecse_snapshots", int(ecse) == 0, f"count={ecse}"))

    wde = repo._conn.execute(
        f"""
        SELECT COUNT(*) AS c FROM worldcup_stored_predictions
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("no_wde_stored", int(wde) == 0, f"count={wde}"))

    for tbl in ("ecse_score_distributions", "ecse_score_distributions_dc", "ecse_score_distributions_m1"):
        exists = repo._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (tbl,)
        ).fetchone()
        checks.append(_check(f"baseline_table_present_{tbl}", exists is not None))

    # Artifacts exist
    checks.append(_check("audit_artifact_exists", AUDIT_PATH.exists(), str(AUDIT_PATH)))
    checks.append(_check("summary_artifact_exists", SUMMARY_PATH.exists(), str(SUMMARY_PATH)))

    # Unresolved reported in audit
    if AUDIT_PATH.exists():
        audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        checks.append(
            _check(
                "unresolved_rows_reported",
                "rows" in audit,
                f"missing_count={audit.get('missing_count')}",
            )
        )

    remaining = {k: len(list_missing_result_fixtures(repo, k)) for k in UEFA_CUP_KEYS}
    checks.append(_check("remaining_missing_reported", True, json.dumps(remaining)))

    failed = [c for c in checks if not c["passed"]]
    report = {
        "phase": "EURO-A2",
        "checks": checks,
        "failed": failed,
        "passed": len(failed) == 0,
        "remaining_missing_by_competition": remaining,
        "summary_path": str(SUMMARY_PATH),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
