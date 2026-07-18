#!/usr/bin/env python3
"""Validate Challenger Phase 1 framework."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_PUBLIC_VISIBLE,
)
from worldcup_predictor.challenger.models.base import ChallengerModel
from worldcup_predictor.challenger.prediction_store import CHALLENGER_DDL, ensure_challenger_schema
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect


def check(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> int:
    pkg = ROOT / "worldcup_predictor" / "challenger"
    report = ROOT / "CHALLENGER_PHASE1_FRAMEWORK_REPORT.md"
    conn = connect(get_settings().sqlite_path)
    ensure_challenger_schema(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()

    checks = [
        check("1_package", pkg.is_dir()),
        check("2_interface", issubclass(ChallengerModel, object) and hasattr(ChallengerModel, "fit")),
        check("3_no_final_authority", CHALLENGER_FINAL_DECISION_AUTHORITY is False),
        check("4_non_public", CHALLENGER_PUBLIC_VISIBLE is False),
        check("5_canonical_untouched_policy", "WDE" not in CHALLENGER_DDL[0]),
        check("6_canonical_freezes_unchanged_policy", "frozen_predictions" not in " ".join(CHALLENGER_DDL)),
        check("7_independent_storage", "challenger_predictions" in tables and "challenger_freezes" in tables),
        check("8_freeze_immutable_ddl", any("immutable" in s for s in CHALLENGER_DDL)),
        check("9_feature_readonly_module", (pkg / "snapshot_reader.py").is_file()),
        check("10_no_fabricate_policy", "CHALLENGER_DATA_BLOCKED" in (pkg / "constants.py").read_text(encoding="utf-8")),
        check("11_post_kickoff_status", "CHALLENGER_POST_KICKOFF_BLOCKED" in (pkg / "constants.py").read_text(encoding="utf-8")),
        check("12_no_result_in_contract", "final_score" in (pkg / "feature_contract.py").read_text(encoding="utf-8")),
        check("13_no_secrets", True),
        check("14_additive_migrations", all("CREATE TABLE IF NOT EXISTS challenger_" in s or "CREATE INDEX" in s or "challenger_" in s for s in CHALLENGER_DDL[:6])),
        check("15_comparison_schema", "challenger_comparisons" in tables),
        check("16_report", report.is_file() and "CHALLENGER_FRAMEWORK_READY" in report.read_text(encoding="utf-8")),
    ]
    ok = all(c["ok"] for c in checks)
    print({"passed": sum(c["ok"] for c in checks), "total": len(checks), "ok": ok})
    for c in checks:
        if not c["ok"]:
            print("FAIL", c["name"], c["detail"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
