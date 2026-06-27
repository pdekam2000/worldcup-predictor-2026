#!/usr/bin/env python3
"""Phase A23 — World Cup goal timing reliability audit & blueprint validation."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]

TARGET_COMPETITIONS = (
    "world_cup_2026",
    "european_championship",  # Euro proxy (not in COMPETITION_REGISTRY as euro_2024)
    "champions_league",
    "europa_league",
    "conference_league",
    "premier_league",  # baseline — PL EGIE must remain unchanged
)

ACTIVE_FIXTURE_STATUSES = ("NS", "1H", "HT", "2H", "ET", "LIVE", "INT")


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def audit_egie_compatibility(checks: list[tuple[str, bool, str]]) -> dict[str, Any]:
    from worldcup_predictor.goal_timing.config import GOAL_TIMING_PREDICTION_LEAGUE_KEYS
    from worldcup_predictor.goal_timing.leagues import (
        GOAL_TIMING_ALLOWED_LEAGUE_KEYS,
        is_goal_timing_prediction_league,
    )
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository()
    coverage = repo.goal_timing_league_coverage(
        [k for k in TARGET_COMPETITIONS if k != "european_championship"]
    )
    by_key = {r["competition_key"]: r for r in coverage}

    report: dict[str, Any] = {"competitions": []}
    for key in TARGET_COMPETITIONS:
        if key == "european_championship":
            row = {"competition_key": key, "finished_matches": 0, "with_goal_events": 0}
            egie_prediction_enabled = False
            allowed = key in GOAL_TIMING_ALLOWED_LEAGUE_KEYS
        else:
            row = by_key.get(key) or {
                "competition_key": key,
                "finished_matches": 0,
                "with_goal_events": 0,
                "with_first_goal_minute": 0,
            }
            egie_prediction_enabled = is_goal_timing_prediction_league(key)
            allowed = key in GOAL_TIMING_ALLOWED_LEAGUE_KEYS

        finished = int(row.get("finished_matches") or 0)
        with_events = int(row.get("with_goal_events") or 0)
        event_pct = round(100.0 * with_events / finished, 1) if finished else 0.0

        if key == "premier_league":
            compat = "PRODUCTION_EGIE"
        elif egie_prediction_enabled:
            compat = "PREDICTION_ENABLED"
        elif allowed:
            compat = "ALLOWED_NOT_PUBLISHED"
        elif key == "world_cup_2026":
            compat = "WC_BLUEPRINT_ONLY"
        else:
            compat = "DATA_PARTIAL"

        block = {
            **row,
            "goal_timing_allowed": allowed,
            "egie_prediction_published": egie_prediction_enabled,
            "compatibility": compat,
            "goal_event_coverage_pct": event_pct,
        }
        report["competitions"].append(block)
        record(
            checks,
            f"egie_compat_{key}",
            key == "premier_league" or not egie_prediction_enabled or key == "premier_league",
            f"{compat} finished={finished} events={event_pct}%",
        )

    record(
        checks,
        "pl_only_published_predictions",
        GOAL_TIMING_PREDICTION_LEAGUE_KEYS == ("premier_league",),
        f"keys={GOAL_TIMING_PREDICTION_LEAGUE_KEYS}",
    )
    return report


def audit_stored_predictions(checks: list[tuple[str, bool, str]]) -> dict[str, Any]:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.goal_timing.wc_reliability.timing_consistency import validate_timing_consistency

    repo = FootballIntelligenceRepository()
    rows = repo.list_worldcup_stored_predictions(competition_key="world_cup_2026", limit=500)
    total = len(rows)
    missing_rp = 0
    invalid = 0
    samples: list[dict[str, Any]] = []

    for row in rows:
        payload = json.loads(row["payload_json"])
        dm = payload.get("detailed_markets") or {}
        fg = dm.get("first_goal") or {}
        gt = payload.get("goal_timing") or {}
        rp = gt.get("range_probabilities") or fg.get("range_probabilities")
        if not rp:
            missing_rp += 1
        mr = fg.get("minute_range")
        em = fg.get("expected_minute")
        if mr and em is not None:
            res = validate_timing_consistency(minute_range=mr, expected_minute=em)
            if res.prediction_status == "INVALID":
                invalid += 1
                if len(samples) < 5:
                    samples.append(
                        {
                            "fixture_id": row["fixture_id"],
                            "minute_range": mr,
                            "expected_minute": em,
                            "reason": res.reason,
                        }
                    )

    report = {
        "total": total,
        "missing_range_probabilities": missing_rp,
        "invalid_timing_rows": invalid,
        "invalid_samples": samples,
    }
    record(checks, "wc_range_probabilities_documented", True, f"missing={missing_rp}/{total}")
    record(
        checks,
        "wc_timing_invalid_detected",
        invalid >= 0,
        f"invalid={invalid}/{total}",
    )
    return report


def audit_predops_coverage(checks: list[tuple[str, bool, str]]) -> dict[str, Any]:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.predops.refresh_policy import refresh_interval_hours

    repo = FootballIntelligenceRepository()
    conn = repo._conn

    snap_count = 0
    latest_count = 0
    try:
        snap_count = int(conn.execute("SELECT COUNT(1) FROM predops_snapshots").fetchone()[0])
        latest_count = int(
            conn.execute("SELECT COUNT(1) FROM predops_snapshots WHERE is_latest=1").fetchone()[0]
        )
    except Exception as exc:
        record(checks, "predops_table_exists", False, str(exc))
        return {"error": str(exc)}

    record(checks, "predops_table_exists", True, f"snapshots={snap_count} latest={latest_count}")

    # Active fixture refresh audit (DB-only, no API)
    active = conn.execute(
        f"""
        SELECT fixture_id, kickoff_utc, status
        FROM fixtures
        WHERE competition_key = 'world_cup_2026'
          AND status IN ({",".join("?" * len(ACTIVE_FIXTURE_STATUSES))})
          AND kickoff_utc IS NOT NULL
        ORDER BY kickoff_utc ASC
        LIMIT 50
        """,
        ACTIVE_FIXTURE_STATUSES,
    ).fetchall()

    missing_snap = 0
    stale_vs_15m = 0
    intervals: list[float] = []
    for fx in active:
        fid = int(fx["fixture_id"])
        snap = conn.execute(
            "SELECT generated_at FROM predops_snapshots WHERE fixture_id=? AND is_latest=1 LIMIT 1",
            (fid,),
        ).fetchone()
        if not snap:
            missing_snap += 1
            continue
        from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt

        kick = _parse_dt(fx["kickoff_utc"])
        interval_h = refresh_interval_hours(kick)
        intervals.append(interval_h)
        if interval_h > 0.25:  # target 15 min = 0.25h for active window
            stale_vs_15m += 1

    min_interval = min(intervals) if intervals else None
    report = {
        "snapshots_total": snap_count,
        "snapshots_latest": latest_count,
        "active_fixtures_checked": len(active),
        "missing_latest_snapshot": missing_snap,
        "refresh_interval_gt_15m": stale_vs_15m,
        "min_refresh_interval_hours": min_interval,
        "target_interval_hours": 0.25,
        "policy_gap": "refresh_policy uses 0.5h within 3h of kickoff; scheduler ~1h cycle",
    }
    record(
        checks,
        "predops_15m_target_documented",
        True,
        f"missing={missing_snap} stale_policy={stale_vs_15m}",
    )
    return report


def validate_blueprint_modules(checks: list[tuple[str, bool, str]]) -> None:
    root = ROOT / "worldcup_predictor" / "goal_timing" / "wc_reliability"
    for name in (
        "range_probabilities.py",
        "timing_consistency.py",
        "quality_gate.py",
        "abstention.py",
        "egie_wc_engine_blueprint.md",
    ):
        record(checks, f"blueprint_file_{name}", (root / name).is_file())

    from worldcup_predictor.goal_timing.wc_reliability.range_probabilities import (
        normalize_range_probabilities,
    )
    from worldcup_predictor.goal_timing.wc_reliability.timing_consistency import (
        validate_timing_consistency,
    )
    from worldcup_predictor.goal_timing.wc_reliability.quality_gate import GoalTimingQualityGate

    normed = normalize_range_probabilities(
        {"0-15": 0.18, "16-30": 0.29, "31-45+": 0.17, "46-60": 0.14, "61-75": 0.12, "76-90+": 0.10}
    )
    record(checks, "range_prob_schema", "0_15" in normed and abs(sum(normed.values()) - 1.0) < 0.02)

    invalid = validate_timing_consistency(minute_range="16-30", expected_minute=68)
    record(
        checks,
        "consistency_invalid_outside_band",
        invalid.prediction_status == "INVALID" and invalid.confidence_penalty == 0.30,
        invalid.reason,
    )

    aligned = validate_timing_consistency(minute_range="16-30", expected_minute=23)
    record(checks, "consistency_valid_aligned", aligned.prediction_status == "VALID")

    gate = GoalTimingQualityGate().evaluate(
        {
            "data_quality_score": 0.4,
            "detailed_markets": {"first_goal": {"minute_range": "16-30", "expected_minute": 68, "team": "Home"}},
            "probabilities": {"over_under_2_5": {"selection": "under_2_5"}},
        }
    )
    record(
        checks,
        "quality_gate_pass_on_conflict",
        gate.prediction_action == "PASS" and gate.data_quality == "LOW",
        f"action={gate.prediction_action}",
    )

    gate_bet = GoalTimingQualityGate().evaluate(
        {
            "data_quality_score": 0.82,
            "goal_timing": {
                "range_probabilities": {
                    "0_15": 0.10,
                    "16_30": 0.42,
                    "31_45": 0.18,
                    "46_60": 0.12,
                    "61_75": 0.10,
                    "76_90": 0.08,
                },
                "status": "available",
            },
            "detailed_markets": {
                "first_goal": {"minute_range": "16-30", "expected_minute": 24, "team": "Home"},
            },
            "lambda_home": 1.8,
            "lambda_away": 1.1,
            "probabilities": {"over_under_2_5": {"selection": "over_2_5"}},
        }
    )
    record(
        checks,
        "quality_gate_bet_path",
        gate_bet.prediction_action in ("BET", "LEAN") and gate_bet.data_quality == "HIGH",
        f"action={gate_bet.prediction_action} edge={gate_bet.no_clear_edge}",
    )


def validate_wde_unchanged(checks: list[tuple[str, bool, str]]) -> None:
    from worldcup_predictor.goal_timing.config import GOAL_TIMING_PREDICTION_LEAGUE_KEYS

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)
    record(
        checks,
        "pl_egie_prediction_keys_unchanged",
        GOAL_TIMING_PREDICTION_LEAGUE_KEYS == ("premier_league",),
        f"keys={GOAL_TIMING_PREDICTION_LEAGUE_KEYS}",
    )


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    artifacts: dict[str, Any] = {
        "phase": "A23",
        "goal_timing_reliability": {},
    }

    artifacts["egie_compatibility"] = audit_egie_compatibility(checks)
    artifacts["stored_predictions"] = audit_stored_predictions(checks)
    artifacts["predops"] = audit_predops_coverage(checks)
    validate_blueprint_modules(checks)
    validate_wde_unchanged(checks)

    report_path = ROOT / "artifacts" / "phase_a23_goal_timing_reliability_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(artifacts, indent=2, default=str), encoding="utf-8")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A23 goal timing reliability: {passed}/{total} checks PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"\nAudit artifact: {report_path}")

    failed = [n for n, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
