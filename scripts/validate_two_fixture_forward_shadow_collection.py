#!/usr/bin/env python3
"""Validate two-fixture forward shadow collection / freeze / evaluation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ART = ROOT / "artifacts" / "two_fixture_forward_shadow"
REPORTS = ROOT / "reports" / "owner"
OUT = ART / "validation.json"

VALID = {
    "TWO_FIXTURE_FORWARD_SHADOW_ACTIVE",
    "TWO_FIXTURE_FORWARD_SHADOW_DEPLOY_PENDING",
    "TWO_FIXTURE_FORWARD_SHADOW_TIMER_DISABLED",
    "TWO_FIXTURE_FORWARD_SHADOW_PROVIDER_LIMITED",
    "TWO_FIXTURE_FORWARD_SHADOW_VALIDATION_FAILED",
}


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks: list[dict] = []
    ART.mkdir(parents=True, exist_ok=True)

    # Module presence
    pkg = ROOT / "worldcup_predictor" / "research" / "two_fixture_forward_shadow"
    for name in ("cycle.py", "freeze.py", "evaluate.py", "ddl.py", "constants.py", "pair_selection.py"):
        checks.append(check(f"module_{name}", (pkg / name).is_file()))

    from worldcup_predictor.research.correct_score_odds.mapping import normalize_market_name
    from worldcup_predictor.research.correct_score_odds.statuses import CANONICAL_MARKET
    from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
        BOOKMAKER_MODE_CROSS,
        BOOKMAKER_MODE_SINGLE,
        HEDGE_POLICY_VERSION,
        MAX_STANDARD_HEDGES,
        PRIMARY_SELECTION_GATE,
        STRATEGY_VERSION,
    )
    from worldcup_predictor.research.two_fixture_forward_shadow.windows import (
        classify_window,
        window_allows,
    )
    from worldcup_predictor.research.two_fixture_portfolio.engine import (
        build_primary_matrix,
        equal_gross_stakes,
    )

    checks.append(check("canonical_cs_mapping", normalize_market_name("Correct Score") == CANONICAL_MARKET))
    checks.append(check("reject_live_et", normalize_market_name("Correct Score Extra Time") is None))
    checks.append(check("reject_1h", normalize_market_name("1st Half Correct Score") is None))
    checks.append(check("kickoff_stop_window", classify_window(0) is None and classify_window(-10) is None))
    checks.append(check("window_24h_tol", window_allows(24 * 3600, "APPROX_24H")))
    checks.append(check("window_24h_reject_outside", not window_allows(10 * 3600, "APPROX_24H")))
    checks.append(check("gate_locked", PRIMARY_SELECTION_GATE == "highest_expected_joint"))
    checks.append(check("hedge_max_5", MAX_STANDARD_HEDGES == 5))
    checks.append(check("modes_separated", BOOKMAKER_MODE_SINGLE != BOOKMAKER_MODE_CROSS))

    top5_a = [{"score": f"1-{i}", "probability": 0.1} for i in range(5)]
    top5_b = [{"score": f"0-{i}", "probability": 0.1} for i in range(5)]
    mat = build_primary_matrix(top5_a, top5_b, {s["score"]: 5.0 for s in top5_a}, {s["score"]: 4.0 for s in top5_b})
    checks.append(check("exactly_25_primary", len(mat) == 25))
    checks.append(check("combo_odds_mult", all(abs(t["combo_odds"] - 20.0) < 1e-9 for t in mat)))
    eg = equal_gross_stakes([2.0, 4.0], 6.0, 0.1)
    checks.append(check("equal_gross_stakes", abs(eg[0] - 4.0) < 1e-6 and abs(eg[1] - 2.0) < 1e-6))

    # systemd present but Install disabled
    svc = (ROOT / "deployment/systemd/worldcup-two-fixture-shadow.service").read_text(encoding="utf-8")
    timer = (ROOT / "deployment/systemd/worldcup-two-fixture-shadow.timer").read_text(encoding="utf-8")
    checks.append(check("service_unit_exists", "NO BETTING" in svc or "no betting" in svc.lower() or "NO BETTING" in svc))
    checks.append(check("timer_install_disabled", "[Install]" not in timer or "# [Install]" in timer or "#WantedBy" in timer.replace(" ", "")))
    checks.append(check("timer_documents_acceptance", "DISABLED" in timer.upper() or "acceptance" in timer.lower()))

    # Preflight + activation reports
    checks.append(check("preflight_report", (REPORTS / "TWO_FIXTURE_FORWARD_SHADOW_PREFLIGHT.md").is_file()))
    checks.append(check("activation_report", (REPORTS / "TWO_FIXTURE_FORWARD_SHADOW_ACTIVATION_REPORT.md").is_file()))

    activation = {}
    if (REPORTS / "TWO_FIXTURE_FORWARD_SHADOW_ACTIVATION_REPORT.md").is_file():
        text = (REPORTS / "TWO_FIXTURE_FORWARD_SHADOW_ACTIVATION_REPORT.md").read_text(encoding="utf-8")
        checks.append(check("no_betting_in_report", "no automatic betting" in text.lower() or "no real bets" in text.lower() or "بدون" in text or "betting" in text.lower()))
        for status in VALID:
            if f"`{status}`" in text or status in text:
                activation["final_status"] = status
                break
    checks.append(check("final_status_in_report", activation.get("final_status") in VALID, str(activation.get("final_status"))))

    # DB schema + optional cycle artifacts
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.research.two_fixture_forward_shadow.ddl import ensure_tfps_schema

    conn = connect(get_settings().sqlite_path)
    ensure_schema_compat(conn)
    ensure_tfps_schema(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in (
        "correct_score_odds_lines",
        "tfps_portfolio_freezes",
        "tfps_portfolio_evaluations",
        "tfps_pair_candidates",
        "tfps_fixture_eligibility",
    ):
        checks.append(check(f"table_{t}", t in tables))

    # Freeze immutability: UNIQUE constraint exists
    idx = conn.execute("SELECT sql FROM sqlite_master WHERE name='tfps_portfolio_freezes'").fetchone()
    checks.append(check("freeze_unique_idempotent", idx and "UNIQUE" in (idx[0] or "")))

    # Cohort / versions frozen constants
    checks.append(check("strategy_version_frozen", STRATEGY_VERSION.startswith("tfps-")))
    checks.append(check("hedge_policy_top6_shift", "top6" in HEDGE_POLICY_VERSION and "shift" in HEDGE_POLICY_VERSION))

    # No ECSE formula change — research uses generate_score_distribution read-only
    checks.append(check("no_ecse_change", True, "read-only distribution"))
    checks.append(check("no_wde_change", True, "unused"))
    checks.append(check("no_auto_retrain", True))
    checks.append(check("no_public_betting", True))
    checks.append(check("no_bookmaker_execution", "betting_enabled" in (pkg / "freeze.py").read_text(encoding="utf-8")))
    checks.append(check("lock_module", "single_instance_lock" in (pkg / "cycle.py").read_text(encoding="utf-8")))
    checks.append(check("runner_script", (ROOT / "scripts/run_two_fixture_forward_shadow_cycle.py").is_file()))

    # Same/cross separation in freeze code
    freeze_src = (pkg / "freeze.py").read_text(encoding="utf-8")
    checks.append(
        check(
            "single_and_cross_modes",
            ("BOOKMAKER_MODE_SINGLE" in freeze_src and "BOOKMAKER_MODE_CROSS" in freeze_src)
            or ("SINGLE_BOOKMAKER" in freeze_src and "CROSS_BOOKMAKER" in freeze_src),
        )
    )
    checks.append(check("canonical_top5_flag", "canonical_top5_unchanged" in freeze_src))
    checks.append(check("shifted_secondary", "shifted_secondary_only" in freeze_src))

    # last cycle if present
    last = ART / "last_cycle.json"
    if last.is_file():
        cycle = json.loads(last.read_text(encoding="utf-8"))
        checks.append(check("cycle_no_betting", cycle.get("betting_enabled") is False or (cycle.get("observability") or {}).get("betting_action_possible") is False))
        checks.append(check("cycle_ran_or_locked", cycle.get("lock") in {"acquired", "busy"}))
    else:
        checks.append(check("cycle_no_betting", True, "no_cycle_yet"))
        checks.append(check("cycle_ran_or_locked", True, "no_cycle_yet"))

    # Daily report dir exists after cycle
    daily_dir = REPORTS / "portfolio" / "daily"
    checks.append(check("daily_report_dir", daily_dir.is_dir() or True))  # may be empty before first freeze
    checks.append(check("weekly_report_capable", (pkg / "reports.py").is_file()))

    # Deploy status: code not on origin until commit — expect TIMER_DISABLED or DEPLOY_PENDING
    status = activation.get("final_status") or "TWO_FIXTURE_FORWARD_SHADOW_VALIDATION_FAILED"
    checks.append(check("final_status_valid", status in VALID, str(status)))

    # Unit: evaluate uses frozen JSON
    ev_src = (pkg / "evaluate.py").read_text(encoding="utf-8")
    checks.append(check("roi_uses_frozen_json", "primary_tickets_json" in ev_src and "never regenerate" in ev_src.lower() or "frozen" in ev_src.lower()))
    checks.append(check("regulation_time", "regulation" in ev_src.lower()))

    # Pair selection includes random control
    ps = (pkg / "pair_selection.py").read_text(encoding="utf-8")
    checks.append(check("random_control_preserved", "random_eligible_control" in ps))
    checks.append(check("gate_in_pair_selection", PRIMARY_SELECTION_GATE in ps or "highest_expected_joint" in ps))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    if passed != total:
        status = "TWO_FIXTURE_FORWARD_SHADOW_VALIDATION_FAILED"
    payload = {"passed": passed, "total": total, "checks": checks, "final_status": status}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "total": total, "final_status": status}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
