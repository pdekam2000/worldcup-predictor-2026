#!/usr/bin/env python3
"""Validate PHASE ECSE-1D / ECSE-1D-B score distribution engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_lambda_extraction import (
    lambda_fingerprint,
)
from worldcup_predictor.research.ecse_score_distribution import (
    DIXON_COLES_RHO_DEFAULT,
    LEGACY_AVG_OTHER_MASS,
    LEGACY_MAX_GOALS,
    MAX_GOALS,
    METHOD_VERSION,
    PROB_SUM_TOLERANCE,
    audit_ecse_score_distributions,
    audit_grid_upgrade_sample,
    build_ecse_score_distributions,
    dixon_coles_tau,
    distribution_fingerprint,
    ensure_ecse_score_distributions_table,
    fetch_top_scorelines,
    fetch_top_scorelines_including_other,
    generate_score_distribution,
    generation_uses_result_labels,
    grid_scorelines_per_fixture,
    sample_top_n_summary,
)

CHECKS: list[tuple[str, bool, str]] = []
EXPECTED_LAMBDA_ROWS = 168_233
EXPECTED_DATASET = 217_518
SCORELINES_PER_FIXTURE = grid_scorelines_per_fixture(MAX_GOALS)
EXPECTED_DIST_ROWS = EXPECTED_LAMBDA_ROWS * SCORELINES_PER_FIXTURE


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("ECSE-1D-B score distribution validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_score_distributions_table(conn)

    lambda_n = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]
    dataset_n = conn.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    lambda_fp_before = lambda_fingerprint(conn)

    check("source_lambda_unchanged", lambda_n == EXPECTED_LAMBDA_ROWS, f"rows={lambda_n}")
    check("source_dataset_unchanged", dataset_n == EXPECTED_DATASET, f"rows={dataset_n}")

    audit = audit_ecse_score_distributions(conn)
    check("distribution_populated", audit.get("fixtures", 0) > 0, f"fixtures={audit.get('fixtures')}")
    check(
        "fixture_coverage_matches_lambda",
        audit.get("fixtures", 0) == EXPECTED_LAMBDA_ROWS,
        f"dist={audit.get('fixtures')} lambda={EXPECTED_LAMBDA_ROWS}",
    )
    check(
        "rows_per_fixture_7x7",
        audit.get("rows_per_fixture") == SCORELINES_PER_FIXTURE,
        f"rows_per_fixture={audit.get('rows_per_fixture')} expected={SCORELINES_PER_FIXTURE}",
    )
    check(
        "max_grid_goals",
        audit.get("max_grid_goals") == MAX_GOALS,
        f"max={audit.get('max_grid_goals')}",
    )
    check(
        "total_distribution_rows",
        audit.get("rows", 0) == EXPECTED_DIST_ROWS,
        f"rows={audit.get('rows')}",
    )
    check(
        "probabilities_positive",
        audit.get("non_positive_probabilities", 1) == 0,
        f"bad={audit.get('non_positive_probabilities')}",
    )
    check(
        "prob_sum_per_fixture",
        audit.get("fixtures_prob_sum_off", 1) == 0,
        f"off={audit.get('fixtures_prob_sum_off')} tol={PROB_SUM_TOLERANCE}",
    )
    check(
        "ranks_correct",
        audit.get("fixtures_rank_errors", 1) == 0,
        f"errors={audit.get('fixtures_rank_errors')}",
    )
    check(
        "other_mass_decreased_vs_5x5",
        (audit.get("avg_other_probability") or 1.0) < LEGACY_AVG_OTHER_MASS,
        f"other={audit.get('avg_other_probability')} legacy={LEGACY_AVG_OTHER_MASS}",
    )
    check(
        "grid_mass_at_least_99_5_pct",
        (audit.get("avg_grid_mass_pct") or 0) >= 99.5,
        f"grid_mass={audit.get('avg_grid_mass_pct')}%",
    )

    upgrade = audit_grid_upgrade_sample(conn, sample_size=500)
    check(
        "top1_rank_stable",
        (upgrade.get("top1_stable_pct") or 0) >= 85.0,
        f"stable={upgrade.get('top1_stable_pct')}%",
    )
    check(
        "top3_overlap_stable",
        (upgrade.get("avg_top3_overlap") or 0) >= 2.0,
        f"overlap={upgrade.get('avg_top3_overlap')}",
    )

    check(
        "no_result_labels_in_generation",
        not generation_uses_result_labels(),
        "static source audit",
    )
    check("method_version", any(v["version"] == METHOD_VERSION for v in audit.get("method_versions", [])), METHOD_VERSION)

    # Dixon–Coles readiness (disabled by default in build)
    dist_poisson = generate_score_distribution(1.6, 1.5, use_dixon_coles=False)
    dist_dc = generate_score_distribution(1.6, 1.5, use_dixon_coles=True, rho=DIXON_COLES_RHO_DEFAULT)
    check("dixon_coles_optional_off_by_default", len(dist_poisson) == SCORELINES_PER_FIXTURE, "poisson ok")
    check("dixon_coles_optional_enabled", len(dist_dc) == SCORELINES_PER_FIXTURE, "dc ok")
    check(
        "dixon_coles_tau_identity_off",
        dixon_coles_tau(0, 0, 1.6, 1.5, 0.0) == 1.0,
        "rho=0",
    )
    built_dc = conn.execute(
        "SELECT COUNT(1) FROM ecse_score_distributions WHERE method_version LIKE '%DC%'"
    ).fetchone()[0]
    check("dixon_coles_not_in_production_build", built_dc == 0, f"dc_rows={built_dc}")

    fid = conn.execute(
        "SELECT registry_fixture_id FROM ecse_score_distributions ORDER BY registry_fixture_id LIMIT 1"
    ).fetchone()
    if fid:
        top5 = fetch_top_scorelines(conn, int(fid[0]), top_n=5)
        top10 = fetch_top_scorelines_including_other(conn, int(fid[0]), top_n=10)
        check("top5_helper", len(top5) == 5 and top5[0]["rank"] == 1, f"len={len(top5)}")
        check("top10_helper", len(top10) == 10 and top10[0]["rank"] == 1, f"len={len(top10)}")
    else:
        check("top5_helper", False, "no data")
        check("top10_helper", False, "no data")

    sample = sample_top_n_summary(conn, sample_fixtures=2, top_n=5)
    check("top_n_sample_summary", len(sample) >= 1, f"samples={len(sample)}")

    fp_before = distribution_fingerprint(conn)
    before_fixtures = audit.get("fixtures", 0)
    rerun = build_ecse_score_distributions(conn, dry_run=False, rebuild=False)
    after_fixtures = conn.execute(
        "SELECT COUNT(DISTINCT registry_fixture_id) FROM ecse_score_distributions"
    ).fetchone()[0]
    fp_after = distribution_fingerprint(conn)
    check(
        "build_idempotent",
        rerun.fixtures_built == 0 and after_fixtures == before_fixtures,
        f"built={rerun.fixtures_built}",
    )
    check("fingerprint_stable", fp_before == fp_after, f"fp={fp_before}")

    lambda_fp_after = lambda_fingerprint(conn)
    check("lambda_fingerprint_stable", lambda_fp_before == lambda_fp_after, "unchanged")

    summary_path = ROOT / "artifacts" / "ecse_1d_b_distribution_summary.json"
    check("summary_artifact_exists", summary_path.is_file(), str(summary_path))

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    if failed:
        return 1

    out = ROOT / "artifacts" / "ecse_1d_b_validation.json"
    out.write_text(
        json.dumps({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS]}, indent=2),
        encoding="utf-8",
    )
    print(f"Validation artifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
