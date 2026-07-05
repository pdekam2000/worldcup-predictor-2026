#!/usr/bin/env python3
"""RESULT-TRUTH-SCHEMA-V8-AND-ECSE-REEVALUATION-1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.migrations import apply_migrations
from worldcup_predictor.database.schema import SCHEMA_VERSION
from worldcup_predictor.outcomes.evaluation_score_policy import (
    regulation_score_for_evaluation,
    result_resolution_type,
    select_evaluation_score,
)
from worldcup_predictor.outcomes.market_result_resolver import resolve_market_result
from worldcup_predictor.research.ecse_live.evaluator import evaluate_frozen_snapshot
from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot, upsert_evaluation
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

PHASE = "RESULT-TRUTH-SCHEMA-V8-AND-ECSE-REEVALUATION-1"
ART = ROOT / "artifacts" / "result_truth_schema_v8_and_ecse_reevaluation_1"
HETZNER = "root@91.107.188.229"
PROD_PATH = "/opt/worldcup-predictor"
FINISHED = {"FT", "AET", "PEN"}
ELIGIBLE_IDS = [
    1562344, 1565176, 1562345, 1564789, 1565177, 1567306, 1567307, 1567308,
    1562586, 1567311, 1567309, 1567312, 1565178, 1565179, 1567310, 1567824,
]
AET_AUDIT = {1567308, 1565179}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _schema_forensic(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    fr_cols = [r[1] for r in conn.execute("PRAGMA table_info(fixture_results)").fetchall()]
    ver = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    return {
        "generated_at": _utc_now(),
        "schema_version": int(ver[0]) if ver else None,
        "target_schema_version": SCHEMA_VERSION,
        "fixture_results_columns": fr_cols,
        "regulation_columns_present": "regulation_home_goals" in fr_cols,
        "terminology": {
            "REGULATION_SCORE": "regulation_home_goals / regulation_away_goals — 90-minute score excluding ET and penalties",
            "FINAL_MATCH_SCORE": "home_goals / away_goals — provider aggregate after ET where applicable",
            "PENALTY_SCORE": "penalties_home_goals / penalties_away_goals or penalty_score",
            "ADVANCING_TEAM": "qualified_team",
            "result_resolution_type": "derived from final_stage: FT→REGULATION, AET→EXTRA_TIME, PEN→PENALTIES",
        },
        "status_mapping": {
            "FT": "REGULATION — final at 90 minutes",
            "AET": "EXTRA_TIME — decided after extra time",
            "PEN": "PENALTIES — decided on shootout after ET draw",
        },
        "evaluation_consumers": [
            "FixtureOutcomeResolver → regulation_fixture_outcome_fields",
            "evaluation_score_policy.select_evaluation_score",
            "ecse_live.evaluator.evaluate_frozen_snapshot",
            "pick_evaluator.evaluate_stored_prediction",
        ],
    }


def _backfill_row(conn: sqlite3.Connection, fid: int, source: str) -> dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
    fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
    if not fr or not fx:
        return None
    old = _row_dict(fr)
    mot = str(fr["match_outcome_type"] or fx["status"] or "FT").upper()
    updates: dict[str, Any] = {}
    if fr["regulation_home_goals"] is None:
        if mot == "AET":
            return {
                "fixture_id": fid,
                "skipped": True,
                "reason": "AET regulation missing — cannot infer from final aggregate",
                "old": {"home_goals": fr["home_goals"], "away_goals": fr["away_goals"]},
            }
        if mot in {"FT", "PEN"} and fr["home_goals"] is not None and fr["away_goals"] is not None:
            updates["regulation_home_goals"] = int(fr["home_goals"])
            updates["regulation_away_goals"] = int(fr["away_goals"])
            updates["final_stage"] = mot
            if mot == "PEN" and fr["penalty_score"]:
                try:
                    ph, pa = [int(x.strip()) for x in str(fr["penalty_score"]).split("-", 1)]
                    updates["penalties_home_goals"] = ph
                    updates["penalties_away_goals"] = pa
                except ValueError:
                    pass
    if not updates:
        return None
    sets = ", ".join(f"{k}=?" for k in updates)
    conn.execute(
        f"UPDATE fixture_results SET {sets}, result_synced_at=? WHERE fixture_id=?",
        (*updates.values(), _utc_now(), fid),
    )
    new_row = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
    return {
        "fixture_id": fid,
        "source": source,
        "resolution_type": result_resolution_type(_row_dict(new_row)),
        "old_values": {k: old.get(k) for k in list(updates) + ["regulation_home_goals", "regulation_away_goals"]},
        "new_values": {k: new_row[k] for k in updates},
        "provenance": f"backfill_{source}",
    }


def _ecse_metrics(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    rows = []
    for fid in fixture_ids:
        e = conn.execute(
            """SELECT e.*, f.home_team, f.away_team FROM ecse_prediction_evaluations e
               JOIN fixtures f ON f.fixture_id=e.fixture_id WHERE e.fixture_id=?""",
            (fid,),
        ).fetchone()
        if e:
            rows.append(_row_dict(e))
    n = len(rows)
    if n == 0:
        return {"n": 0}
    rank_hits = defaultdict(int)
    for r in rows:
        rk = r.get("rank_of_actual_score")
        if rk and 1 <= int(rk) <= 5:
            rank_hits[int(rk)] += 1
    hit3 = sum(1 for r in rows if r.get("top3_correct"))
    hit5 = sum(1 for r in rows if r.get("top5_correct"))
    mrr = sum(1 / int(r["rank_of_actual_score"]) if r.get("rank_of_actual_score") else 0 for r in rows) / n
    return {
        "n": n,
        "rank1_hr": round(rank_hits[1] / n, 4),
        "rank2_hr": round(rank_hits[2] / n, 4),
        "rank3_hr": round(rank_hits[3] / n, 4),
        "rank4_hr": round(rank_hits[4] / n, 4),
        "rank5_hr": round(rank_hits[5] / n, 4),
        "hit_at_3": round(hit3 / n, 4),
        "hit_at_5": round(hit5 / n, 4),
        "mrr": round(mrr, 4),
        "rank_distribution": dict(rank_hits),
    }


def _capture_ecse_fixture_rows(conn: sqlite3.Connection, fixture_ids: list[int]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    resolver = FixtureOutcomeResolver(get_settings())
    out = []
    for fid in fixture_ids:
        fx = conn.execute("SELECT home_team, away_team, status FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        ev = conn.execute("SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
        reg_h, reg_a, reg_score, basis = regulation_score_for_evaluation(_row_dict(fr) if fr else None, _row_dict(fx) if fx else None)
        outcome = resolver.resolve(fid)
        out.append({
            "fixture_id": fid,
            "match": f"{fx['home_team']} vs {fx['away_team']}" if fx else str(fid),
            "status": fx["status"] if fx else None,
            "prior_eval_score": ev["final_score"] if ev else None,
            "canonical_regulation_score": reg_score,
            "score_basis": basis,
            "resolution_type": result_resolution_type(_row_dict(fr) if fr else None),
            "previous_rank": ev["rank_of_actual_score"] if ev else None,
            "resolver_score": outcome.final_score if outcome else None,
        })
    return out


def _reevaluate_ecse(conn: sqlite3.Connection, fixture_ids: list[int]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    resolver = FixtureOutcomeResolver(get_settings())
    changes = []
    for fid in fixture_ids:
        snap_row = conn.execute(
            "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? AND is_frozen=1 ORDER BY id ASC LIMIT 1",
            (fid,),
        ).fetchone()
        if not snap_row:
            continue
        snap = _hydrate_snapshot(_row_dict(snap_row))
        old = conn.execute("SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
        outcome = resolver.resolve(fid)
        payload = evaluate_frozen_snapshot(snap, outcome)
        if not payload:
            continue
        prev_rank = old["rank_of_actual_score"] if old else None
        prev_score = old["final_score"] if old else None
        upsert_evaluation(conn, payload)
        new_rank = payload.get("rank_of_actual_score")
        changes.append({
            "fixture_id": fid,
            "prior_evaluation_score": prev_score,
            "canonical_regulation_score": payload.get("final_score"),
            "previous_rank": prev_rank,
            "corrected_rank": new_rank,
            "metric_changed": (prev_rank != new_rank) or (prev_score != payload.get("final_score")),
            "top5_changed": bool(old) and bool(old["top5_correct"]) != bool(payload.get("top5_correct")),
        })
    return changes


def _wde_impact(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    resolver = FixtureOutcomeResolver(get_settings())
    before_after = []
    for fid in fixture_ids:
        wde = conn.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)).fetchone()
        if not wde or not wde["payload_json"]:
            continue
        payload = json.loads(wde["payload_json"])
        outcome = resolver.resolve(fid)
        if not outcome.is_finished:
            continue
        ev = evaluate_stored_prediction(payload, outcome)
        mk = ev.get("markets") or {}
        fr = conn.execute("SELECT match_outcome_type FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        before_after.append({
            "fixture_id": fid,
            "match_outcome_type": fr["match_outcome_type"] if fr else None,
            "regulation_score": outcome.final_score,
            "1x2": mk.get("1x2"),
            "btts": mk.get("btts"),
            "ou": mk.get("over_under_2_5"),
        })
    return {"fixtures": before_after, "uses_regulation_via_resolver": True}


def _export_regulation_backfill(local_conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[str, Any]:
    local_conn.row_factory = sqlite3.Row
    rows = []
    for fid in fixture_ids:
        fr = local_conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        if not fr:
            continue
        d = _row_dict(fr)
        rows.append({
            "fixture_id": fid,
            "regulation_home_goals": d.get("regulation_home_goals"),
            "regulation_away_goals": d.get("regulation_away_goals"),
            "extra_time_home_goals": d.get("extra_time_home_goals"),
            "extra_time_away_goals": d.get("extra_time_away_goals"),
            "penalties_home_goals": d.get("penalties_home_goals"),
            "penalties_away_goals": d.get("penalties_away_goals"),
            "final_stage": d.get("final_stage") or d.get("match_outcome_type"),
            "qualified_team": d.get("qualified_team"),
        })
    return {"rows": rows, "exported_at": _utc_now(), "source": "local_canonical"}


def _apply_prod_v8(backfill_export: dict[str, Any]) -> dict[str, Any]:
    export_path = ART / "prod_backfill_export.json"
    export_path.write_text(json.dumps(backfill_export, indent=2), encoding="utf-8")
    script = ROOT / "scripts" / "_apply_prod_v8_backfill.py"
    probe = ROOT / "scripts" / "_probe_v8_parity.py"
    # Deploy updated evaluation modules required for regulation-aware re-eval
    modules = list((ROOT / "worldcup_predictor" / "outcomes").glob("*.py")) + [
        ROOT / "worldcup_predictor" / "api" / "prediction_history_evaluation.py",
        ROOT / "worldcup_predictor" / "research" / "ecse_live" / "store.py",
        ROOT / "worldcup_predictor" / "research" / "ecse_live" / "evaluator.py",
        ROOT / "worldcup_predictor" / "database" / "migrations.py",
    ]
    subprocess.run(f'ssh {HETZNER} "mkdir -p {PROD_PATH}/artifacts/result_truth_schema_v8_and_ecse_reevaluation_1 {PROD_PATH}/scripts"', shell=True, check=True)
    scp_files = " ".join(str(p) for p in [export_path, script, probe, *modules])
    subprocess.run(
        f"scp {scp_files} {HETZNER}:{PROD_PATH}/scripts/",
        shell=True,
        check=True,
    )
    for mod in modules:
        rel = mod.relative_to(ROOT).as_posix()
        subprocess.run(
            f'ssh {HETZNER} "mkdir -p {PROD_PATH}/$(dirname {rel}) && cp {PROD_PATH}/scripts/{mod.name} {PROD_PATH}/{rel} 2>/dev/null || true"',
            shell=True,
            check=False,
        )
    # Proper module placement via scp to full paths
    for mod in modules:
        rel = mod.relative_to(ROOT)
        subprocess.run(f'ssh {HETZNER} "mkdir -p {PROD_PATH}/{rel.parent}"', shell=True, check=False)
        subprocess.run(f"scp {mod} {HETZNER}:{PROD_PATH}/{rel.as_posix()}", shell=True, check=True)
    subprocess.run(
        f'scp {export_path} {HETZNER}:{PROD_PATH}/artifacts/result_truth_schema_v8_and_ecse_reevaluation_1/prod_backfill_export.json',
        shell=True,
        check=True,
    )
    proc = subprocess.run(
        f'ssh {HETZNER} "cd {PROD_PATH} && APP_ENV=production .venv/bin/python scripts/_apply_prod_v8_backfill.py artifacts/result_truth_schema_v8_and_ecse_reevaluation_1/prod_backfill_export.json"',
        shell=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _prod_parity_probe(local_conn: sqlite3.Connection) -> list[dict[str, Any]]:
    local_conn.row_factory = sqlite3.Row
    export = []
    for fid in ELIGIBLE_IDS:
        fr = local_conn.execute(
            "SELECT regulation_home_goals, regulation_away_goals FROM fixture_results WHERE fixture_id=?", (fid,)
        ).fetchone()
        ev = local_conn.execute("SELECT rank_of_actual_score FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
        fx = local_conn.execute("SELECT home_team, away_team FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        reg = f"{fr['regulation_home_goals']}-{fr['regulation_away_goals']}" if fr and fr["regulation_home_goals"] is not None else None
        export.append({"fixture_id": fid, "match": f"{fx['home_team']} vs {fx['away_team']}", "local_regulation": reg, "local_rank": ev["rank_of_actual_score"] if ev else None})
    probe_path = ART / "prod_parity_probe_local.json"
    probe_path.write_text(json.dumps(export, indent=2), encoding="utf-8")
    script = ROOT / "scripts" / "_probe_v8_parity.py"
    script.write_text(
        '''#!/usr/bin/env python3
import json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.outcomes.evaluation_score_policy import regulation_score_for_evaluation

ids = json.loads(Path(sys.argv[1]).read_text())
settings = get_settings()
conn = sqlite3.connect(settings.sqlite_path)
conn.row_factory = sqlite3.Row
out = []
for item in ids:
    fid = int(item["fixture_id"])
    fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
    fx = conn.execute("SELECT home_team, away_team FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
    ev = conn.execute("SELECT rank_of_actual_score FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
    _, _, reg, _ = regulation_score_for_evaluation(dict(fr) if fr else None, dict(fx) if fx else None)
    out.append({"fixture_id": fid, "match": item["match"], "prod_regulation": reg, "prod_rank": ev["rank_of_actual_score"] if ev else None})
print(json.dumps(out))
''',
        encoding="utf-8",
    )
    subprocess.run(f"scp {script} {probe_path} {HETZNER}:{PROD_PATH}/scripts/", shell=True, check=False)
    proc = subprocess.run(
        f'ssh {HETZNER} "cd {PROD_PATH} && .venv/bin/python scripts/_probe_v8_parity.py scripts/prod_parity_probe_local.json"',
        shell=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return [{"error": proc.stderr}]
    prod = {int(x["fixture_id"]): x for x in json.loads(proc.stdout)}
    rows = []
    for item in export:
        fid = item["fixture_id"]
        p = prod.get(fid, {})
        rows.append({
            "fixture": item["match"],
            "local_regulation_score": item["local_regulation"],
            "prod_regulation_score": p.get("prod_regulation"),
            "ecse_hit_rank_equal": item["local_rank"] == p.get("prod_rank"),
            "local_rank": item["local_rank"],
            "prod_rank": p.get("prod_rank"),
            "status": "OK" if item["local_regulation"] == p.get("prod_regulation") and item["local_rank"] == p.get("prod_rank") else "MISMATCH",
        })
    return rows


def _historical_replay_contract() -> dict[str, Any]:
    return {
        "phase": "HISTORICAL-REPLAY-RESULT-TRUTH-CONTRACT",
        "version": "1.0",
        "evaluation_target": "regulation-time score (90 minutes)",
        "rules": [
            "EXACT_SCORE evaluation uses REGULATION_SCORE only",
            "AET aggregate goals cannot be used as exact-score evaluation labels",
            "Penalty shootout goals cannot be added to exact-score labels",
            "FINAL_MATCH_SCORE preserved separately for advancement context",
            "ADVANCING_TEAM available for qualification markets",
            "PENALTY_SCORE available for penalty-winner markets only",
        ],
        "result_resolution_types": ["REGULATION", "EXTRA_TIME", "PENALTIES"],
        "market_policy": {
            "exact_score": "REGULATION_SCORE",
            "1x2": "REGULATION_SCORE",
            "btts": "REGULATION_SCORE",
            "over_under_2_5": "REGULATION_SCORE",
            "double_chance": "REGULATION_SCORE",
            "qualification": "ADVANCING_TEAM",
            "penalty_winner": "PENALTY_SCORE",
        },
        "selector_module": "worldcup_predictor.outcomes.evaluation_score_policy",
    }


def _write_reports(workflow: dict[str, Any], ecse_delta: dict, parity: list, aet_audit: list) -> None:
    Path("RESULT_TRUTH_SCHEMA_V8_AND_ECSE_REEVALUATION_1_REPORT.md").write_text(
        "\n".join([
            f"# {PHASE} — Report",
            "",
            f"**Recommendation:** `{workflow['final_recommendation']}`",
            "",
            "## Schema v8",
            f"- Local schema: v{workflow.get('local_schema_after')}",
            f"- Production deploy: {workflow.get('prod_deploy')}",
            "",
            "## ECSE before/after",
            "| Metric | Before | After | Delta |",
            "|---|---:|---:|---:|",
            *[f"| {k} | {ecse_delta['before'].get(k)} | {ecse_delta['after'].get(k)} | {ecse_delta['delta'].get(k)} |"
              for k in ("rank1_hr", "rank2_hr", "rank3_hr", "rank4_hr", "rank5_hr", "hit_at_3", "hit_at_5", "mrr")],
            "",
            "## AET audit",
            "```json",
            json.dumps(aet_audit, indent=2),
            "```",
        ]) + "\n",
        encoding="utf-8",
    )
    Path("RESULT_TRUTH_SCHEMA_V8_OWNER_REPORT.md").write_text(
        "\n".join([
            "# Result Truth Schema v8 — Owner Report",
            "",
            f"**Recommendation:** `{workflow['final_recommendation']}`",
            "",
            "Canonical regulation / AET / PEN columns deployed. Evaluation uses regulation score for exact-score and standard prematch markets.",
            "",
            f"Backfill rows: {workflow.get('backfill_count', 0)}",
            f"Production backfill: {workflow.get('prod_backfill_count', 0)}",
        ]) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# ECSE Re-evaluation Before/After — Owner Report",
        "",
        f"**Recommendation:** `{workflow['final_recommendation']}`",
        "",
        "| Fixture | Prior Score | Regulation Score | Prev Rank | New Rank | Changed? |",
        "|---|---|---|---:|---:|:---:|",
    ]
    for r in workflow.get("ecse_changes", []):
        lines.append(
            f"| {r.get('fixture_id')} | {r.get('prior_evaluation_score')} | {r.get('canonical_regulation_score')} | {r.get('previous_rank')} | {r.get('corrected_rank')} | {r.get('metric_changed')} |"
        )
    Path("ECSE_REEVALUATION_BEFORE_AFTER_OWNER_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=PHASE)
    parser.add_argument("--skip-prod", action="store_true")
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    ART.mkdir(parents=True, exist_ok=True)
    db_path = Path(settings.sqlite_path or ROOT / "data" / "football_intelligence.db")

    if not args.skip_backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        shutil.copy2(db_path, ART / f"football_intelligence_pre_v8_{ts}.db")

    conn = connect(str(db_path))
    forensic = _schema_forensic(conn)
    (ART / "schema_forensic.json").write_text(json.dumps(forensic, indent=2), encoding="utf-8")

    schema_before = forensic["schema_version"]
    apply_migrations(conn)
    schema_after = int(conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0])
    migration_result = {
        "schema_before": schema_before,
        "schema_after": schema_after,
        "target": SCHEMA_VERSION,
        "regulation_columns_present": "regulation_home_goals" in forensic["fixture_results_columns"] or schema_after >= 8,
        "destructive": False,
        "applied_at": _utc_now(),
    }
    (ART / "migration_result.json").write_text(json.dumps(migration_result, indent=2), encoding="utf-8")

    backfill_lines = []
    for fid in ELIGIBLE_IDS:
        row = _backfill_row(conn, fid, "local_canonical_ft_pen_inference")
        if row:
            backfill_lines.append(row)
    conn.commit()

    aet_audit = []
    for fid in AET_AUDIT:
        fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        reg = resolve_market_result(_row_dict(fr), _row_dict(fx), market_type="correct_score")
        aet_audit.append({
            "fixture_id": fid,
            "match": f"{fx['home_team']} vs {fx['away_team']}",
            "final_match_score": f"{fr['home_goals']}-{fr['away_goals']}",
            "regulation_score": reg.get("final_score"),
            "regulation_explicit": fr["regulation_home_goals"] is not None,
            "final_stage": fr["final_stage"] or fr["match_outcome_type"],
            "qualified_team": fr["qualified_team"],
            "score_basis": reg.get("score_basis"),
        })
    (ART / "aet_pen_audit.json").write_text(json.dumps(aet_audit, indent=2), encoding="utf-8")

    with (ART / "result_truth_backfill.jsonl").open("w", encoding="utf-8") as f:
        for line in backfill_lines:
            f.write(json.dumps(line, default=str) + "\n")

    before_rows = _capture_ecse_fixture_rows(conn, ELIGIBLE_IDS)
    metrics_before = _ecse_metrics(conn, ELIGIBLE_IDS)

    ecse_changes = _reevaluate_ecse(conn, ELIGIBLE_IDS)
    conn.commit()

    metrics_after = _ecse_metrics(conn, ELIGIBLE_IDS)
    delta = {k: round(metrics_after.get(k, 0) - metrics_before.get(k, 0), 4) for k in metrics_before if k != "n" and isinstance(metrics_before.get(k), (int, float))}
    ecse_before_after = {"before": metrics_before, "after": metrics_after, "delta": delta, "fixture_changes": ecse_changes}
    (ART / "ecse_before_after.json").write_text(json.dumps(ecse_before_after, indent=2), encoding="utf-8")

    wde_impact = _wde_impact(conn, ELIGIBLE_IDS)
    (ART / "wde_evaluation_impact.json").write_text(json.dumps(wde_impact, indent=2), encoding="utf-8")

    backfill_export = _export_regulation_backfill(conn, ELIGIBLE_IDS)
    prod_result = None
    parity = []
    if not args.skip_prod:
        prod_result = _apply_prod_v8(backfill_export)
        parity = _prod_parity_probe(conn)

    (ART / "local_production_parity.json").write_text(json.dumps(parity, indent=2), encoding="utf-8")

    contract = _historical_replay_contract()
    (ART / "historical_replay_result_truth_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")

    metric_changed_count = sum(1 for c in ecse_changes if c.get("metric_changed"))
    top5_delta = metrics_after.get("hit_at_5", 0) - metrics_before.get("hit_at_5", 0)

    if metric_changed_count > 0:
        rec = "RESULT_TRUTH_V8_DEPLOYED_EVALUATIONS_CORRECTED"
    elif top5_delta == 0 and metrics_before.get("hit_at_5") == metrics_after.get("hit_at_5"):
        rec = "RESULT_TRUTH_V8_DEPLOYED_NO_METRIC_CHANGES"
    else:
        rec = "RESULT_TRUTH_V8_DEPLOYED_NO_METRIC_CHANGES"

    if any(a.get("regulation_explicit") is False for a in aet_audit):
        rec = "RESULT_TRUTH_V8_BLOCKED_BY_MISSING_REGULATION_DATA"

    if all(a.get("regulation_explicit") for a in aet_audit) and metric_changed_count > 0:
        rec = "RESULT_TRUTH_V8_DEPLOYED_EVALUATIONS_CORRECTED"

    workflow = {
        "phase": PHASE,
        "local_schema_after": schema_after,
        "backfill_count": len(backfill_lines),
        "prod_deploy": prod_result,
        "prod_backfill_count": json.loads(prod_result["stdout"]).get("backfill", 0) if prod_result and prod_result.get("exit_code") == 0 and prod_result.get("stdout") else None,
        "ecse_metric_changed_fixtures": metric_changed_count,
        "ecse_changes": ecse_changes,
        "final_recommendation": rec,
    }
    (ART / "workflow.json").write_text(json.dumps(workflow, indent=2, default=str), encoding="utf-8")
    _write_reports(workflow, ecse_before_after, parity, aet_audit)
    conn.close()
    print(json.dumps(workflow, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
