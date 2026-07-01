#!/usr/bin/env python3
"""Validate PHASE ECSE-1F Dixon–Coles distributions and comparison."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_dixon_coles_distribution import (
    METHOD_VERSION,
    TABLE_NAME,
    audit_ecse_score_distributions_dc,
    poisson_table_unchanged,
)
from worldcup_predictor.research.ecse_score_distribution import (
    DIXON_COLES_RHO_DEFAULT,
    grid_scorelines_per_fixture,
)

CHECKS: list[tuple[str, bool, str]] = []
EXPECTED_LAMBDA_ROWS = 168_233
EXPECTED_POISSON_ROWS = 10_935_145
EXPECTED_DC_ROWS = EXPECTED_LAMBDA_ROWS * grid_scorelines_per_fixture()


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("ECSE-1F Dixon–Coles validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))

    poisson_n = conn.execute("SELECT COUNT(1) FROM ecse_score_distributions").fetchone()[0]
    lambda_n = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]

    check("poisson_table_unchanged", poisson_n == EXPECTED_POISSON_ROWS, f"rows={poisson_n}")
    check("lambda_unchanged", lambda_n == EXPECTED_LAMBDA_ROWS, f"rows={lambda_n}")

    audit = audit_ecse_score_distributions_dc(conn)
    check("dc_table_exists", audit["rows"] > 0, f"rows={audit['rows']}")
    check("dc_row_count", audit["rows"] == EXPECTED_DC_ROWS, f"expected={EXPECTED_DC_ROWS}")
    check("dc_fixture_count", audit["fixtures"] == EXPECTED_LAMBDA_ROWS, f"fixtures={audit['fixtures']}")
    check("dc_prob_sums", audit["fixtures_prob_sum_off"] == 0, f"off={audit['fixtures_prob_sum_off']}")
    check(
        "dc_rho",
        audit.get("rho") is not None and abs(float(audit["rho"]) - DIXON_COLES_RHO_DEFAULT) < 1e-9,
        f"rho={audit.get('rho')}",
    )
    check(
        "poisson_unchanged_guard",
        poisson_table_unchanged(conn, expected_rows=EXPECTED_POISSON_ROWS),
        "count match",
    )

    summary_path = ROOT / "artifacts" / "ecse_1f_dc_summary.json"
    report_path = ROOT / "ECSE_1F_DIXON_COLES_REPORT.md"
    check("summary_artifact", summary_path.is_file(), str(summary_path))
    check("report_artifact", report_path.is_file(), str(report_path))

    if summary_path.is_file():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        check("summary_phase", payload.get("phase") == "ECSE-1F", payload.get("phase", ""))
        check(
            "summary_method",
            payload.get("method_version") == METHOD_VERSION,
            payload.get("method_version", ""),
        )
        check(
            "poisson_table_flag",
            payload.get("poisson_table_unchanged") is True,
            str(payload.get("poisson_table_unchanged")),
        )

        po = payload["backtest_poisson"]["overall"]
        dc = payload["backtest_dixon_coles"]["overall"]
        check(
            "fixtures_evaluated_match",
            payload["backtest_poisson"]["fixtures_evaluated"] == EXPECTED_LAMBDA_ROWS,
            str(payload["backtest_poisson"]["fixtures_evaluated"]),
        )
        check(
            "hit_rates_ordered_poisson",
            po["top1_hit_rate_pct"] <= po["top3_hit_rate_pct"] <= po["top5_hit_rate_pct"],
            f"poisson top1={po['top1_hit_rate_pct']}",
        )
        check(
            "hit_rates_ordered_dc",
            dc["top1_hit_rate_pct"] <= dc["top3_hit_rate_pct"] <= dc["top5_hit_rate_pct"],
            f"dc top1={dc['top1_hit_rate_pct']}",
        )
        check("log_loss_finite", math.isfinite(po["avg_log_loss"]) and math.isfinite(dc["avg_log_loss"]))
        check("comparison_verdict", payload["comparison"]["verdict"] in ("improved", "mixed", "degraded"))

        low_d = payload["backtest_dixon_coles"].get("low_score_actuals", {})
        low_p = payload["backtest_poisson"].get("low_score_actuals", {})
        if low_d.get("n") and low_p.get("n"):
            check(
                "dc_raises_low_score_prob",
                float(low_d["avg_prob_actual"]) >= float(low_p["avg_prob_actual"]),
                f"p={low_p['avg_prob_actual']} dc={low_d['avg_prob_actual']}",
            )

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    if failed:
        return 1

    out = ROOT / "artifacts" / "ecse_1f_validation.json"
    out.write_text(
        json.dumps({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS]}, indent=2),
        encoding="utf-8",
    )
    print(f"Validation artifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
