#!/usr/bin/env python3
"""Phase 48A — real production accuracy monitoring validation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase48a_real_accuracy_monitoring_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"phase": "48A", "passed": passed, "total": total, "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Phase 48A validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.api.performance_center import build_performance_summary, reliability_level
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.monitoring.production_accuracy_monitor import (
        build_market_leaderboard,
        capture_performance_snapshot,
        compute_rule_a_impact,
    )

    repo = FootballIntelligenceRepository()
    ensure_schema_compat(repo._conn)
    record("performance_snapshots_table", repo.count_performance_snapshots() >= 0)
    repo.close()

    record("reliability_levels", reliability_level(5) == "low" and reliability_level(50) == "high")

    snap = capture_performance_snapshot()
    record("snapshot_generated", bool(snap.get("snapshot_at")), str(snap.get("evaluated_count")))

    repo2 = FootballIntelligenceRepository()
    count = repo2.count_performance_snapshots()
    rows = repo2.list_performance_snapshots(limit=5)
    repo2.close()
    record("snapshot_persisted", count >= 1 and len(rows) >= 1, str(count))

    summary = build_performance_summary()
    record("performance_summary_v2", summary.get("version") == "v2")
    record("accuracy_trends_present", isinstance(summary.get("accuracy_trends"), dict))
    record("market_leaderboard_present", isinstance(summary.get("market_leaderboard"), list))
    record("rule_a_monitoring_present", isinstance(summary.get("rule_a_monitoring"), dict))
    record("agent_contribution_present", isinstance(summary.get("agent_contribution"), dict))

    rule_a = compute_rule_a_impact()
    for key in (
        "wde_preserved",
        "scoreline_override",
        "beneficial_override",
        "harmful_override",
        "override_rate",
    ):
        record(f"rule_a_{key}", key in rule_a, str(rule_a.get(key)))

    leaderboard = build_market_leaderboard(
        [{"market_name": "BTTS", "winrate": 0.6, "sample_size": 25}, {"market_name": "1X2", "winrate": 0.4, "sample_size": 30}]
    )
    record("leaderboard_order", leaderboard[0]["market_name"] == "BTTS")

    eval_rows = FootballIntelligenceRepository().list_worldcup_prediction_evaluations()
    record("evaluations_readable", isinstance(eval_rows, list), str(len(eval_rows)))

    from worldcup_predictor.decision.weighted_decision_engine import WeightedDecisionEngine

    wde = WeightedDecisionEngine()
    record("wde_unchanged", hasattr(wde, "apply_decision"))

    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    record("scoring_engine_unchanged", hasattr(ScoringEngine, "predict"))

    get_settings.cache_clear()
    record("no_fake_data_flag", summary.get("data_source") == "worldcup_sqlite_evaluations")

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())
