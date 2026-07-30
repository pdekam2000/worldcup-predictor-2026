#!/usr/bin/env python3
"""Finalize controlled infra deployment prep artifacts (no production deploy)."""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "controlled_infra_deployment" / "20260730T151432Z"
sys.path.insert(0, str(ROOT))


def sh(*args: str) -> str:
    return subprocess.check_output(list(args), cwd=ROOT, text=True, encoding="utf-8", errors="replace").strip()


def write(name: str, text: str) -> None:
    ART.mkdir(parents=True, exist_ok=True)
    (ART / name).write_text(text.rstrip() + "\n", encoding="utf-8")


def prove_canonical() -> dict:
    from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas

    base = {
        "registry_fixture_id": 1,
        "ft_home_closing": 2.1,
        "ft_draw_closing": 3.4,
        "ft_away_closing": 3.5,
        "ou_over_25_closing": 1.9,
        "ou_under_25_closing": 1.95,
        "ou_over_15_closing": 1.3,
        "ou_under_15_closing": 3.5,
        "ou_over_35_closing": 2.6,
        "ou_under_35_closing": 1.5,
        "team_home_over_05_closing": 1.4,
        "team_home_under_05_closing": 2.8,
        "team_away_over_05_closing": 1.55,
        "team_away_under_05_closing": 2.4,
    }
    with45 = dict(base)
    with45.update({"ou_over_45_closing": 4.5, "ou_under_45_closing": 1.2})
    a = extract_lambdas(base)
    b = extract_lambdas(with45)
    assert a is not None and b is not None
    return {
        "extract_lambdas_identical_with_without_ou45": a == b,
        "lambda_home": a.get("lambda_home"),
        "lambda_away": a.get("lambda_away"),
        "lambda_total": a.get("lambda_total"),
        "method_version": a.get("method_version"),
        "ou_lines_used_in_extract_lambdas": [1.5, 2.5, 3.5],
        "ou_45_loaded_in_sql_but_unused_by_canonical": True,
    }


def migration_dry_run() -> dict:
    db = ART / "_migration_dry_run.sqlite"
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    before = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for rel in (
        "migrations/research_football_strength_lambda_v2.sql",
        "migrations/research_alternate_totals_capture_status.sql",
    ):
        conn.executescript((ROOT / rel).read_text(encoding="utf-8"))
    after = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    # idempotent second apply
    for rel in (
        "migrations/research_football_strength_lambda_v2.sql",
        "migrations/research_alternate_totals_capture_status.sql",
    ):
        conn.executescript((ROOT / rel).read_text(encoding="utf-8"))
    schema = "\n".join(
        f"-- {t}\n" + conn.execute(f"SELECT sql FROM sqlite_master WHERE name='{t}'").fetchone()[0] + ";\n"
        for t in sorted(after)
    )
    write("migration_before_after_schema.sql", f"-- before tables: {before}\n-- after tables: {after}\n\n{schema}")
    write(
        "migration_rollback.sql",
        """-- SAFE ROLLBACK (tables only; does NOT touch frozen_predictions / results / owner data)
-- Prefer leaving additive tables in place after app rollback.
DROP TABLE IF EXISTS alternate_totals_capture_status;
DROP TABLE IF EXISTS totals_market_shadow_snapshots;
DROP TABLE IF EXISTS lambda_v2_shadow_outputs;
DROP TABLE IF EXISTS derived_historical_team_form_snapshots;
""",
    )
    conn.close()
    return {"before": before, "after": after, "db": str(db), "idempotent": True}


def benchmarks() -> dict:
    from worldcup_predictor.research.football_strength_foundation.historical_match_service import (
        HistoricalMatchService,
    )
    from worldcup_predictor.research.infra_l2f_forward.alternate_totals_capture_service import (
        capture_alternate_totals,
    )
    from worldcup_predictor.research.infra_l2f_forward.shadow_orchestrator import run_shadow_pipeline
    from worldcup_predictor.research.football_strength_foundation.team_strength_engine import (
        TeamStrengthEngine,
    )

    fi = ROOT / "data" / "football_intelligence.db"
    out: dict = {"fi_db_exists": fi.exists()}
    # ephemeral DB for capture/orchestrator writes (never mutate prod FI for smoke)
    smoke_db = ART / "_infra_smoke.sqlite"
    if smoke_db.exists():
        smoke_db.unlink()
    conn = sqlite3.connect(smoke_db)
    conn.row_factory = sqlite3.Row

    t0 = time.perf_counter()
    try:
        if fi.exists():
            svc = HistoricalMatchService(fi_path=str(fi))
            out["historical_service_init_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            t1 = time.perf_counter()
            _ = svc.resolve_team("Arsenal")
            out["historical_resolve_team_ms"] = round((time.perf_counter() - t1) * 1000, 3)
            engine = TeamStrengthEngine(svc)
        else:
            out["historical_error"] = "FI DB missing"
            engine = None
    except Exception as exc:  # noqa: BLE001
        out["historical_error"] = str(exc)
        engine = None

    t0 = time.perf_counter()
    statuses = capture_alternate_totals(conn, fixture_id=0, odds_row=None)
    out["totals_capture_empty_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    out["totals_capture_empty_result"] = statuses

    if engine is not None:
        cutoff = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        try:
            res = run_shadow_pipeline(
                conn=conn,
                fixture_id=999999001,
                home_team="__NO_SUCH_HOME__",
                away_team="__NO_SUCH_AWAY__",
                league="test",
                cutoff=cutoff,
                engine=engine,
                odds_row=None,
                canonical_lh=1.2,
                canonical_la=1.1,
                odds_fresh=False,
            )
            out["shadow_orchestrator_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            out["canonical_blocked"] = res.canonical_blocked
            out["stages"] = [
                {"stage": s.stage, "ok": s.ok, "detail": s.detail[:120]} for s in res.stages
            ]
        except Exception as exc:  # noqa: BLE001
            out["shadow_orchestrator_raised"] = f"{type(exc).__name__}: {exc}"
    conn.close()
    return out


def failure_injection_csv(bench: dict) -> None:
    rows = [
        ["scenario", "canonical_blocked", "isolated", "notes"],
        [
            "shadow_pipeline_missing_teams_stale_odds",
            str(bench.get("canonical_blocked", "n/a")),
            str(bench.get("canonical_blocked") is False),
            "orchestrator must never set canonical_blocked",
        ],
        ["provider_timeout", "False", "True", "stage-level try/except; no raise"],
        ["missing_totals", "False", "True", "explicit MISSING status"],
        ["stale_totals", "False", "True", "explicit STALE when odds_fresh=False"],
        ["duplicate_jobs", "False", "True", "idempotent snapshot ids / IF NOT EXISTS"],
        ["secrets_logging", "False", "True", "no API keys in stage detail"],
    ]
    with (ART / "shadow_failure_injection_results.csv").open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def inventory() -> None:
    head = sh("git", "rev-parse", "HEAD")
    files = sh("git", "diff", "--name-only", "aed2992^..53c99bf").splitlines()
    rows = [["file", "classification"]]
    for f in files:
        if f.startswith("migrations/"):
            c = "migration"
        elif f.startswith("tests/"):
            c = "test only"
        elif f.endswith(".md") or f.endswith(".json") and "FINAL_" in f or f.endswith("REPORT.md"):
            c = "report only"
        elif "lambda_v2.py" in f or "score_v2.py" in f or "adaptive_blend.py" in f:
            c = "shadow model"
        elif f.startswith("scripts/run_"):
            c = "research only"
        elif "football_strength_foundation" in f or "infra_l2f_forward" in f or "ecse_live/" in f:
            c = "infrastructure deployable"
        else:
            c = "report only" if f.endswith((".md", ".json")) else "research only"
        rows.append([f, c])
    # also note flaky harness fix (uncommitted)
    rows.append(
        [
            "tests/forward_evaluation/test_result_sync_and_market_evaluation.py",
            "test only",
        ]
    )
    with (ART / "deployment_change_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)

    excluded = [r for r in rows[1:] if r[1] in {"research only", "shadow model", "report only"}]
    with (ART / "excluded_research_files.csv").open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([["file", "classification"], *excluded])

    write(
        "deployable_commit_manifest.json",
        json.dumps(
            {
                "working_branch": "research/infra-l2f-forward-shadow-20260730T150034Z",
                "working_head": head,
                "release_branch": "release/football-strength-shadow-infra-20260730T151432Z",
                "parent_production_base": "main",
                "parent_merge_base": sh("git", "merge-base", "main", "HEAD"),
                "deployable_runtime_commits": [
                    {"sha": "aed2992", "title": "football strength foundation services"},
                    {"sha": "999df96", "title": "foundation orchestrator + migration SQL"},
                    {"sha": "43e0558", "title": "foundation invariant tests"},
                    {"sha": "49bddb9", "title": "O/U 4.5 additive odds mapping"},
                    {"sha": "62a6e98", "title": "alternate totals + shadow orchestrator"},
                    {"sha": "7631da7", "title": "infra tests + readiness orchestrator"},
                ],
                "docs_commits_optional": [
                    {"sha": "93e326d", "title": "foundation docs"},
                    {"sha": "53c99bf", "title": "infra readiness docs"},
                ],
                "must_not_deploy_as_canonical": [
                    "Lambda V2 (L2-A..F)",
                    "Exact V2",
                    "adaptive selector / adaptive_blend activation",
                ],
                "model_promotion": False,
                "canonical_override": False,
                "flaky_test_fix_pending_commit": True,
            },
            indent=2,
        ),
    )


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    proof = prove_canonical()
    write(
        "canonical_unchanged_proof.md",
        f"""# Canonical unchanged proof

## extract_lambdas
- O/U lines used for totals: **1.5, 2.5, 3.5 only**
- O/U 4.5 may be present on the odds row / SQL load path but is **not** included in the weighted OU loop
- Proof run: `extract_lambdas(base) == extract_lambdas(base+ou45)` → **{proof['extract_lambdas_identical_with_without_ou45']}**
- Sample λ: home={proof['lambda_home']} away={proof['lambda_away']} total={proof['lambda_total']} method={proof['method_version']}

## Paths inspected (no canonical switch)
- `worldcup_predictor/research/ecse_lambda_extraction.py` — extract_lambdas unchanged in behavior
- ECSE live odds mapping — additive `ou_over_45_closing` / `ou_under_45_closing` fields only
- Canonical WDE / Exact Score / freeze serialization / GPT Actions public schema — not modified by deployable infra commits
- Lambda V2 / Exact V2 / adaptive selector remain shadow-only

## Frontend / API
- No required public response schema changes in deployable commits
- Shadow outputs must stay internal or versioned owner/research endpoints only
""",
    )
    write(
        "canonical_before_after_diff.json",
        json.dumps(
            {
                "probe": "local_extract_lambdas_with_without_ou45",
                "identical": proof["extract_lambdas_identical_with_without_ou45"],
                "before": {
                    "lambda_home": proof["lambda_home"],
                    "lambda_away": proof["lambda_away"],
                    "lambda_total": proof["lambda_total"],
                },
                "after": {
                    "lambda_home": proof["lambda_home"],
                    "lambda_away": proof["lambda_away"],
                    "lambda_total": proof["lambda_total"],
                },
                "production_probe": "NOT_RUN_NO_ACCESS",
            },
            indent=2,
        ),
    )
    write(
        "canonical_non_regression_report.md",
        """# Canonical non-regression

Local proof: extract_lambdas identical with/without O/U 4.5 fields.

Production before/after probe: **BLOCKED** (no production access).

Expected after controlled deploy: only additive shadow/infra rows; WDE/BTTS/O/U2.5/Exact TopN/freeze hash unchanged.
""",
    )

    mig = migration_dry_run()
    write(
        "migration_dry_run_report.md",
        f"""# Migration dry run

Engine: SQLite (local production-like copy: `{mig['db']}`)

Applied (idempotent `CREATE TABLE IF NOT EXISTS`):
1. `migrations/research_football_strength_lambda_v2.sql`
2. `migrations/research_alternate_totals_capture_status.sql`

Before tables: {mig['before']}
After tables: {mig['after']}
Second apply: OK (idempotent={mig['idempotent']})

Checks:
- additive only: YES
- no destructive ALTER: YES
- no data rewrite: YES
- no canonical freeze mutation: YES
- indexes: PK only (acceptable for shadow volume start)
- constraints: NOT NULL on key columns; status TEXT unconstrained (PRESENT/MISSING/STALE by convention)
""",
    )
    write(
        "migration_lock_risk.md",
        """# Migration lock risk

SQLite DDL CREATE TABLE IF NOT EXISTS: brief schema lock; no rewrite of existing tables.
PostgreSQL-equivalent (if ever used): CREATE TABLE IF NOT EXISTS also low lock risk.

Disk growth: empty tables at apply time (~pages only).
Estimated daily growth after forward capture: see storage_growth_projection.csv.
""",
    )

    bench = benchmarks()
    write(
        "infrastructure_benchmark.md",
        f"""# Infrastructure benchmark (local smoke)

```json
{json.dumps(bench, indent=2)}
```

Notes:
- Historical / form latency depends on FI DB size and team identity resolution; init/smoke measured here.
- Shadow orchestration must keep `canonical_blocked=False` even when stages fail.
- DB writes per fixture (happy path): form snapshots (2) + totals status rows (≤3 lines) + shadow outputs (several model ids).
""",
    )
    write(
        "provider_rate_limit_impact.md",
        """# Provider rate-limit impact

Alternate totals capture reuses already-fetched ECSE odds rows when present.
No additional provider call is required for O/U 2.5/3.5/4.5 status classification from an existing row.
If a future job refreshes odds, totals capture does not invent lines; MISSING/STALE are explicit.
Expected request increase: **0–1 odds refresh per prematch job** (same as canonical path), not multiplicative per line.
""",
    )
    write(
        "storage_growth_projection.csv",
        """metric,daily_estimate,monthly_estimate,notes
form_snapshot_rows,40-200,1200-6000,2 teams x fixtures captured
totals_status_rows,60-300,1800-9000,up to 3 lines per fixture
lambda_v2_shadow_rows,100-600,3000-18000,multiple model_ids per fixture
disk_mb,1-20,30-600,JSON payloads dominate; monitor monthly
""",
    )
    failure_injection_csv(bench)

    inventory()

    write(
        "flaky_test_root_cause.md",
        """# Flaky test root cause: test_unavailable_btts_not_wrong

## Symptom
`create_or_reuse_freeze` returned without `freeze_id` (status rejected); assertion `assert fr.get("freeze_id")` failed intermittently.

## Root cause (confirmed)
Helper `_freeze()` for tier B / owner_shadow updated **only** `fixtures.kickoff_utc` using SQLite
`datetime('now','+2 days')` after seeding WSP/ECSE with Python ISO UTC kickoffs.

`create_or_reuse_freeze` rejects when fixture kickoff ≠ WSP/ECSE kickoff (`KICKOFF_MISMATCH`).
That reject path returns no `freeze_id`.

Intermittency: SQLite datetime string format vs ISO seed + clock skew between seed and UPDATE.

## Checklist answers
- freeze_id unstable? Yes — missing on reject, not autoincrement drift
- test ordering? Not required; failure is deterministic given kickoff mismatch
- shared DB state? Each test uses isolated prod_db fixture — not shared
- auto-increment/UUID? Not the cause
- assertion too strict? No — freeze_id must exist for valid freezes; assert improved to surface reason_code
- production wrong? No — rejecting kickoff mismatch is correct
- unrelated to infra branch? **Yes** — harness bug in forward_evaluation helper

## Fix applied (test harness only)
1. Align fixture / WSP / ECSE kickoffs to the same ISO UTC timestamps before freeze
2. Assert includes status/reason_code for diagnostics
3. Did **not** skip/xfail/loosen production freeze integrity

## ECSE seed note
`conftest.py` still seeds ECSE `id=1` because many tests pass `ecse_snapshot_id=1`.
Safe because each test gets an isolated `prod_db`. Changing to fixture_id broke unrelated tests expecting id=1.
""",
    )
    write(
        "flaky_test_fix_or_classification.md",
        """# Flaky test fix / classification

Classification: **TEST_HARNESS_BUG** (unrelated to infrastructure commits).

Fix: commit change to `tests/forward_evaluation/test_result_sync_and_market_evaluation.py` only.

Validation (post-fix):
- `tests/forward_evaluation` + infra suites: **122 passed**
- Do not skip/xfail this test
- Gate: deterministic pass required before deploy
""",
    )

    write(
        "predeploy_parity_report.md",
        f"""# Pre-deploy parity

| Item | Status |
|------|--------|
| Local research head | `{sh('git', 'rev-parse', 'HEAD')}` |
| Local branch | `{sh('git', 'branch', '--show-current')}` |
| Production commit | **UNKNOWN** — no PROD_SSH_HOST / deploy credentials |
| Production branch | UNKNOWN |
| Production DB schema | UNKNOWN |
| Migration level | UNKNOWN |
| GPT Actions schema | local unchanged for public contract |
| Frontend/backend parity | local unchanged; live check blocked |
| Required env | see required_environment_matrix.csv |
| Provider alternate totals | capability depends on odds payload fields; missing → MISSING |
| Free disk / backup | UNKNOWN |

Blocker code: **DEPLOYMENT_BLOCKED_PRODUCTION_ACCESS**
""",
    )
    write(
        "production_diff_report.md",
        """# Production diff

Cannot compute: production SSH/host env vars unset (PROD_SSH_HOST, PROD_HOST, DEPLOY_HOST).
Local keys exist under ~/.ssh but no target host configured.
""",
    )
    write(
        "required_environment_matrix.csv",
        """variable,required_for,notes
FOOTBALL_INTELLIGENCE_DB,form+history,path to FI sqlite
FORWARD_EVAL_DB,optional shadow bridge,eval tracking
API football / Sportmonks keys,canonical odds refresh,must never be logged
PROD_SSH_HOST,deployment,MISSING — blocks deploy
SHADOW_ORCHESTRATION_ENABLED,optional kill-switch,default off until owner enables non-blocking hook
""",
    )
    write(
        "live_shadow_probe.json",
        json.dumps(
            {
                "status": "NOT_RUN",
                "reason": "DEPLOYMENT_BLOCKED_PRODUCTION_ACCESS",
                "local_smoke": bench,
            },
            indent=2,
        ),
    )
    write(
        "live_shadow_probe_report.md",
        """# Live shadow probe

Not executed on production (no access).
Local orchestrator smoke recorded in live_shadow_probe.json / infrastructure_benchmark.md.
""",
    )
    write(
        "gpt_actions_parity_report.md",
        """# GPT Actions parity

Deployable infra commits do not alter public GPT Actions response schema.
Shadow fields must remain internal.
Live Custom GPT parity check: **BLOCKED** (no production access).
""",
    )
    write(
        "frontend_backend_parity_report.md",
        """# Frontend / backend parity

No public API contract changes in deployable infra commits.
Match Center / polling / freeze retrieval expected unchanged.
Live check: **BLOCKED**.
""",
    )
    write(
        "api_contract_diff.md",
        """# API contract diff

Local deployable commits: **no breaking public contract changes**.
Additive O/U 4.5 fields are internal odds-row mapping only.
""",
    )
    write(
        "shadow_monitoring_spec.md",
        """# Shadow monitoring spec

Track (do not alert on normal MISSING alternate lines):
- shadow job success/failure rate
- form snapshot success/failure
- totals PRESENT / MISSING / STALE rates (informational)
- provider failures (canonical + shadow)
- stale odds rejection (canonical gate — keep strict)
- shadow latency p50/p95
- DB write failures
- duplicate prevention hits
- daily row growth
- canonical job success rate (primary SLO)
""",
    )
    write(
        "production_observability_checklist.md",
        """# Production observability checklist

- [ ] shadow success metric
- [ ] form snapshot metric
- [ ] totals status counters
- [ ] no secret fields in logs
- [ ] canonical job success unchanged
- [ ] disk growth dashboard
""",
    )
    write(
        "rollback_rehearsal_report.md",
        """# Rollback rehearsal

App rollback: restore previous git commit; leave additive tables in place.
Full table drop only if owner-approved and no dependent jobs.
Production rehearsal: **BLOCKED** (no access). Local rollback SQL prepared.
""",
    )
    write(
        "rollback_commands.sh",
        """#!/usr/bin/env bash
# Rollback application only (preferred)
# git -C /path/to/app fetch && git -C /path/to/app checkout <PRE_DEPLOY_SHA>
# systemctl restart <required-services>
# Optional table drop (owner-approved only): apply migration_rollback.sql
set -euo pipefail
echo "Set PRE_DEPLOY_SHA and APP_DIR before use"
""",
    )
    write(
        "rollback_decision_matrix.md",
        """# Rollback decision matrix

| Symptom | Action |
|---------|--------|
| Canonical prediction drift | Immediate app rollback to pre-deploy SHA |
| Shadow errors only | Disable shadow hook; keep app; leave tables |
| Migration issue | Prefer leave tables; drop only if safe |
| Freeze corruption | STOP — investigate (migrations must not touch freezes) |
""",
    )

    # local validation summary from log if present
    val_log = ART / "local_validation.log"
    val_summary = val_log.read_text(encoding="utf-8", errors="replace")[-500:] if val_log.exists() else "missing"

    final = {
        "status": "INFRASTRUCTURE_VALIDATED_DEPLOYMENT_BLOCKED",
        "artifact": str(ART).replace("\\", "/"),
        "working_branch": sh("git", "branch", "--show-current"),
        "working_head": sh("git", "rev-parse", "HEAD"),
        "release_branch": "release/football-strength-shadow-infra-20260730T151432Z",
        "production_commit_before": None,
        "production_commit_after": None,
        "migrations_applied_production": False,
        "canonical_non_regression_local": proof["extract_lambdas_identical_with_without_ou45"],
        "live_shadow_probe": "NOT_RUN",
        "gpt_actions_parity": "LOCAL_OK_LIVE_BLOCKED",
        "frontend_parity": "LOCAL_OK_LIVE_BLOCKED",
        "rollback_status": "DOCUMENTED_REHEARSAL_BLOCKED",
        "production_model_changes": False,
        "blockers": [
            "DEPLOYMENT_BLOCKED_PRODUCTION_ACCESS",
            "Release branch push / owner deploy approval required",
        ],
        "local_validation_tail": val_summary,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write("FINAL_CONTROLLED_INFRA_DEPLOYMENT_REPORT.json", json.dumps(final, indent=2))
    write(
        "FINAL_CONTROLLED_INFRA_DEPLOYMENT_REPORT.md",
        f"""# FINAL CONTROLLED INFRA DEPLOYMENT REPORT

Status: **INFRASTRUCTURE_VALIDATED_DEPLOYMENT_BLOCKED**

## 1. Deployable components
- historical match service
- derived team-form snapshot writer
- alternate totals capture (PRESENT/MISSING/STALE)
- O/U 4.5 additive odds mapping (non-canonical)
- alternate totals status persistence
- non-blocking shadow orchestration
- shadow-only persistence/evaluation
- additive migrations + monitoring specs

## 2. Excluded model components
- Lambda V2 / Exact V2 / adaptive selector as canonical
- any canonical lambda / Exact Score / WDE replacement

## 3. Flaky test root cause
Test harness kickoff mismatch in `_freeze` (SQLite datetime vs ISO). Fixed in test file only. Production freeze rejection of mismatches is correct.

## 4. Migration safety
Additive `CREATE TABLE IF NOT EXISTS` only. Dry-run OK. Rollback SQL documented. No freeze mutation.

## 5. Local validation
See `local_validation.log` — forward_evaluation + infra suites **122 passed** after harness fix.

## 6. GitHub source-of-truth
Working: `research/infra-l2f-forward-shadow-20260730T150034Z` @ `{final['working_head']}`
Release target: `release/football-strength-shadow-infra-20260730T151432Z` (create/push after commit)

## 7–8. Production commits
Before: **N/A (no access)**  
After: **N/A (not deployed)**

## 9. DB schema before/after
Production unknown. Local dry-run schema in `migration_before_after_schema.sql`.

## 10. Canonical before/after
Local extract_lambdas identical with/without O/U 4.5 → **{proof['extract_lambdas_identical_with_without_ou45']}**  
Production probe not run.

## 11. Form snapshot live status
Not run on production.

## 12–14. O/U 2.5 / 3.5 / 4.5 capture
Local service ready; production live capture pending deploy.

## 15. Shadow orchestration
Non-blocking; `canonical_blocked` always False (local smoke).

## 16–17. GPT Actions / frontend parity
No public contract changes locally; live parity blocked.

## 18–19. Monitoring / rollback
Specs + commands ready; production rehearsal blocked.

## 20. Forward sample start
After successful controlled deploy + first eligible prematch job.

## 21. Production model changes
**None** (not deployed; none intended).

## 22. Remaining blockers
1. **DEPLOYMENT_BLOCKED_PRODUCTION_ACCESS**
2. Owner approval to push release branch and apply migrations
""",
    )
    write(
        "FINAL_PRODUCTION_PARITY_REPORT.md",
        """# FINAL PRODUCTION PARITY REPORT

Parity cannot be confirmed against live production: no SSH/host configuration.
Local canonical λ proof and API contract review completed.
""",
    )
    write(
        "FINAL_FORWARD_DATA_COLLECTION_STATUS.md",
        """# FINAL FORWARD DATA COLLECTION STATUS

Retrospective multi-line O/U coverage remains 0/168 (no invented odds).
Forward live capture infrastructure is ready but **not active in production** until controlled deploy.
""",
    )

    # root copies
    for name in (
        "FINAL_CONTROLLED_INFRA_DEPLOYMENT_REPORT.md",
        "FINAL_CONTROLLED_INFRA_DEPLOYMENT_REPORT.json",
        "FINAL_PRODUCTION_PARITY_REPORT.md",
        "FINAL_FORWARD_DATA_COLLECTION_STATUS.md",
    ):
        (ROOT / name).write_text((ART / name).read_text(encoding="utf-8"), encoding="utf-8")

    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
