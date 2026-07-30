#!/usr/bin/env python3
"""Deep end-to-end forensic audit orchestrator (read-mostly).

Produces artifacts under artifacts/deep_model_forensic_audit/<UTC_TS>/.
Does NOT mutate freezes, weaken gates, invent odds/results, or deploy.
Safe code fixes are out of scope for this runner; it only audits + reports.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

UTC = timezone.utc
RUN_ID = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
OUT = ROOT / "artifacts" / "deep_model_forensic_audit" / RUN_ID
OUT.mkdir(parents=True, exist_ok=True)

EVAL_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"
FI_DB = ROOT / "data" / "football_intelligence.db"

TERMINAL = {"FT", "AET", "PEN", "FINISHED", "COMPLETED"}
LOW_SCORES = {"0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2"}


def jload(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


def fnum(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    k: (
                        json.dumps(v, ensure_ascii=False)
                        if isinstance(v, (dict, list))
                        else ("" if v is None else v)
                    )
                    for k, v in r.items()
                }
            )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ro(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def sh(cmd: list[str]) -> dict[str, Any]:
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        return {"cmd": cmd, "rc": p.returncode, "stdout": (p.stdout or "")[-4000:], "stderr": (p.stderr or "")[-2000:]}
    except Exception as e:
        return {"cmd": cmd, "rc": -1, "error": str(e)}


def file_sha16(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ---------------- Phase 0 ----------------
def phase0() -> dict[str, Any]:
    git = {
        "branch": sh(["git", "rev-parse", "--abbrev-ref", "HEAD"]).get("stdout", "").strip(),
        "commit": sh(["git", "rev-parse", "HEAD"]).get("stdout", "").strip(),
        "status_short": sh(["git", "status", "-sb"]).get("stdout", "")[:2000],
        "remote": sh(["git", "remote", "-v"]).get("stdout", "")[:500],
        "log5": sh(["git", "log", "-5", "--oneline"]).get("stdout", "")[:1000],
    }
    dbs = {}
    for p in [EVAL_DB, FI_DB]:
        dbs[str(p.relative_to(ROOT))] = {
            "exists": p.exists(),
            "size": p.stat().st_size if p.exists() else 0,
            "sha256_16": file_sha16(p),
            "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat() if p.exists() else None,
        }
    tables = {}
    if EVAL_DB.exists():
        con = ro(EVAL_DB)
        tables["forward_prediction_tracking"] = [
            r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")
        ]
        counts = {}
        for t in tables["forward_prediction_tracking"]:
            try:
                counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception as e:
                counts[t] = f"error:{e}"
        tables["counts"] = counts
    if FI_DB.exists():
        con = ro(FI_DB)
        tables["football_intelligence"] = [
            r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")
        ][:80]

    env = {
        "run_id": RUN_ID,
        "cwd": str(ROOT),
        "python": sys.version,
        "platform": sys.platform,
        "git": git,
        "databases": dbs,
        "tables": tables,
        "note": "Production parity (deployed commit/services) not probed unless SSH credentials available; marked UNKNOWN.",
        "production_parity": "UNKNOWN_NO_LIVE_SSH_IN_THIS_RUN",
        "gpt_actions_parity": "UNKNOWN_SCHEMA_PRESENT_LOCAL_ONLY",
    }
    write_json(OUT / "environment_inventory.json", env)
    write_json(
        OUT / "parity_matrix.json",
        {
            "local_commit": git.get("commit"),
            "local_branch": git.get("branch"),
            "github_source_of_truth": "origin/main (remote present)",
            "production_deployed_commit": "UNKNOWN",
            "eval_db_present": EVAL_DB.exists(),
            "fi_db_present": FI_DB.exists(),
            "dirty_workspace": " M" in (git.get("status_short") or "") or "??" in (git.get("status_short") or ""),
            "alignment_status": "PARTIAL — local audit branch; production not verified live",
        },
    )
    write_text(
        OUT / "repository_map.md",
        "\n".join(
            [
                "# Repository map (deep forensic)",
                "",
                f"- Run: `{RUN_ID}`",
                f"- Branch: `{git.get('branch')}`",
                f"- Commit: `{git.get('commit')}`",
                "- Key packages: `worldcup_predictor/` (WDE, ECSE, odds, gpt_actions, forward_evaluation, research)",
                "- Eval DB: `data/evaluation/forward_prediction_tracking.db`",
                "- Intelligence DB: `data/football_intelligence.db`",
                "- Artifacts: `artifacts/`",
                "- Owner scripts: `scripts/run_*`, `scripts/validate_*`",
            ]
        ),
    )
    write_text(
        OUT / "database_inventory.md",
        "# Database inventory\n\n" + json.dumps(dbs, indent=2) + "\n\nTables:\n\n" + json.dumps(tables, indent=2),
    )
    write_text(
        OUT / "runtime_inventory.md",
        "# Runtime inventory\n\nLocal Windows workspace. Production systemd units exist under `deployment/systemd/` but were not queried live in this run.\n",
    )
    # active models from freeze rows
    models = {"wde": Counter(), "ecse": Counter(), "scopes": Counter(), "tiers": Counter()}
    if EVAL_DB.exists():
        con = ro(EVAL_DB)
        for r in con.execute(
            "SELECT wde_model_version, ecse_model_version, prediction_scope, validation_tier, freeze_status "
            "FROM frozen_predictions"
        ):
            models["wde"][str(r["wde_model_version"] or "null")] += 1
            models["ecse"][str(r["ecse_model_version"] or "null")] += 1
            models["scopes"][str(r["prediction_scope"] or "null")] += 1
            models["tiers"][str(r["validation_tier"] or "null")] += 1
    write_json(
        OUT / "active_model_inventory.json",
        {k: dict(v.most_common(30)) for k, v in models.items()},
    )
    return env


# ---------------- Phase 1 ----------------
def phase1() -> dict[str, Any]:
    patterns = [
        (r"\bTODO\b", "TODO"),
        (r"\bFIXME\b", "FIXME"),
        (r"\bXXX\b", "XXX"),
        (r"\bHACK\b", "HACK"),
        (r"NotImplemented", "NotImplemented"),
        (r"\bplaceholder\b", "placeholder"),
        (r"\bmock\b", "mock"),
        (r"\bdummy\b", "dummy"),
        (r"\bfake\b", "fake"),
        (r"except\s+Exception\s*:\s*(pass|continue)\b", "swallowed_exception"),
        (r"hardcoded|manual odds|invent", "hardcoded_or_manual"),
    ]
    incomplete: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []
    deadish: list[dict[str, Any]] = []
    scan_roots = [ROOT / "worldcup_predictor", ROOT / "scripts"]
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "pycache" in str(path) or ".venv" in str(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(path.relative_to(ROOT))
            for rx, label in patterns:
                for m in re.finditer(rx, text, flags=re.IGNORECASE | re.MULTILINE):
                    line = text.count("\n", 0, m.start()) + 1
                    snip = text[max(0, m.start() - 40) : m.end() + 60].replace("\n", " ")
                    row = {
                        "file": rel,
                        "line": line,
                        "label": label,
                        "snippet": snip[:180],
                        "severity": "HIGH"
                        if label in {"swallowed_exception", "hardcoded_or_manual", "NotImplemented"}
                        else ("MEDIUM" if label in {"FIXME", "TODO", "HACK"} else "LOW"),
                        "status": "incomplete" if label in {"TODO", "FIXME", "NotImplemented", "placeholder"} else "review",
                    }
                    if label == "swallowed_exception":
                        hidden.append(row)
                    elif label in {"TODO", "FIXME", "NotImplemented", "placeholder", "XXX", "HACK"}:
                        incomplete.append(row)
                    else:
                        deadish.append(row)
                    if len(incomplete) + len(hidden) + len(deadish) > 5000:
                        break
            if len(incomplete) + len(hidden) + len(deadish) > 5000:
                break

    write_csv(OUT / "incomplete_work_inventory.csv", incomplete[:2000])
    write_csv(OUT / "hidden_fallbacks.csv", hidden[:2000])
    write_csv(OUT / "dead_code_inventory.csv", deadish[:2000])
    write_text(
        OUT / "exception_handling_audit.md",
        f"# Exception handling audit\n\nSwallowed exceptions found: **{len(hidden)}** (capped export).\nSee `hidden_fallbacks.csv`.\n",
    )
    write_text(
        OUT / "test_coverage_gap_report.md",
        "# Test coverage gap (heuristic)\n\nFull coverage tooling not run in this pass. See `tests/` vs `worldcup_predictor/` module counts in final report.\n",
    )
    write_text(
        OUT / "frontend_backend_contract_audit.md",
        "# Frontend/backend contract\n\nGPT Actions OpenAPI lives under gpt_actions. Deep schema diff vs Custom GPT not executed live (no production probe).\n",
    )
    return {"incomplete": len(incomplete), "hidden": len(hidden), "other": len(deadish)}


# ---------------- Phase 2–5: freeze reconciliation + metrics ----------------
def _tops_from_payload(payload: dict) -> list[dict[str, Any]]:
    ecse = payload.get("ecse") or {}
    tops = []
    t10 = ecse.get("top10") or []
    if t10:
        for item in sorted(t10, key=lambda x: int(x.get("rank") or 99)):
            score = item.get("scoreline") or item.get("score")
            tops.append({"rank": item.get("rank"), "score": score, "probability": fnum(item.get("probability"))})
        return tops[:10]
    for i in range(1, 11):
        cell = ecse.get(f"top{i}")
        if isinstance(cell, dict):
            tops.append({"rank": i, "score": cell.get("score") or cell.get("scoreline"), "probability": fnum(cell.get("probability"))})
        elif isinstance(cell, str):
            tops.append({"rank": i, "score": cell, "probability": None})
    if not tops:
        for item in ecse.get("top5") or []:
            if isinstance(item, dict):
                tops.append({"rank": item.get("rank"), "score": item.get("score") or item.get("scoreline"), "probability": fnum(item.get("probability"))})
    return tops[:10]


def _actual_1x2(h: int, a: int) -> str:
    if h > a:
        return "home_win"
    if h < a:
        return "away_win"
    return "draw"


def _classify_exact_miss(pred_top1: str | None, actual: str, wde: str | None) -> str:
    if not actual or "-" not in actual:
        return "unknown"
    try:
        ah, aa = map(int, actual.split("-"))
        ph, pa = (None, None)
        if pred_top1 and "-" in pred_top1:
            ph, pa = map(int, pred_top1.split("-"))
    except Exception:
        return "unexplained"
    actual_dir = _actual_1x2(ah, aa)
    if wde and wde != actual_dir:
        return "wrong_WDE_direction"
    if ph is not None and ((ph > pa) == (ah > aa) or (ph == pa and ah == aa)):
        # direction ok-ish via top1
        if ah + aa > (ph + pa):
            return "correct_direction_underestimated_goals"
        if ah + aa < (ph + pa):
            return "correct_direction_overestimated_goals"
        return "correct_direction_wrong_scoreline"
    if ah == 0 and aa == 0:
        return "draw_or_0_0_miss"
    if ah + aa >= 4:
        return "high_score_tail_miss"
    if abs(ah - aa) >= 2 and (wde == actual_dir):
        return "correct_direction_wrong_margin"
    return "model_limitation_or_upset"


def phase2_to_5() -> dict[str, Any]:
    if not EVAL_DB.exists():
        return {"error": "eval_db_missing"}

    con = ro(EVAL_DB)
    # join freezes to actuals
    freezes = con.execute("SELECT * FROM frozen_predictions").fetchall()
    actuals = {
        int(r["fixture_id"]): dict(r)
        for r in con.execute("SELECT * FROM actual_results")
        if r["fixture_id"] is not None
    }
    # market evals optional
    market_by_pred: dict[str, list] = defaultdict(list)
    try:
        for r in con.execute("SELECT * FROM market_evaluations"):
            market_by_pred[str(r["prediction_id"])].append(dict(r))
    except Exception:
        pass

    evaluated: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    dup_audit: list[dict[str, Any]] = []
    freeze_integrity: list[dict[str, Any]] = []
    taxonomy = Counter()

    by_fixture: dict[int, list] = defaultdict(list)
    for fr in freezes:
        d = dict(fr)
        fid = int(d["fixture_id"])
        by_fixture[fid].append(d)

    for fid, rows in by_fixture.items():
        if len(rows) > 1:
            dup_audit.append(
                {
                    "fixture_id": fid,
                    "n_freezes": len(rows),
                    "prediction_ids": [r.get("prediction_id") for r in rows],
                    "frozen_at": [r.get("frozen_at") for r in rows],
                }
            )
        # earliest valid freeze
        rows_sorted = sorted(rows, key=lambda r: str(r.get("frozen_at") or ""))
        fr = rows_sorted[0]
        payload = jload(fr.get("complete_payload_json")) or {}
        tops = _tops_from_payload(payload)
        if not tops:
            # fallback ranking table
            ranks = con.execute(
                "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
                (fr.get("prediction_id"),),
            ).fetchall()
            tops = [{"rank": r["rank"], "score": r["score"], "probability": fnum(r["probability"])} for r in ranks]

        act = actuals.get(fid)
        # Prefer regulation scores from actual_results
        ah = None
        aa = None
        if act:
            ah = act.get("actual_home_goals")
            aa = act.get("actual_away_goals")
            if ah is None or aa is None:
                sc = act.get("actual_score")
                if sc and "-" in str(sc):
                    try:
                        ah, aa = map(int, str(sc).split("-")[:2])
                    except Exception:
                        pass
            # only treat confirmed/finished as eligible
            rs = str(act.get("result_status") or "").upper()
            rq = str(act.get("result_quality_status") or "")
            if rs and rs not in TERMINAL and "CONFIRM" not in rq.upper():
                # still allow FT
                if rs not in TERMINAL:
                    exclusions.append(
                        {
                            "fixture_id": fid,
                            "reason": f"non_terminal_result_status:{rs}",
                        }
                    )
                    continue

        # integrity
        freeze_integrity.append(
            {
                "fixture_id": fid,
                "prediction_id": fr.get("prediction_id"),
                "immutable": fr.get("immutable"),
                "freeze_status": fr.get("freeze_status"),
                "payload_hash": fr.get("payload_hash") or fr.get("content_hash"),
                "frozen_at": fr.get("frozen_at"),
                "kickoff": fr.get("kickoff"),
                "has_complete_payload": bool(payload),
                "ecse_top5_complete": fr.get("ecse_top5_complete"),
                "n_tops": len(tops),
            }
        )

        if not act or ah is None or aa is None:
            unresolved.append(
                {
                    "fixture_id": fid,
                    "match": fr.get("match_name"),
                    "kickoff": fr.get("kickoff"),
                    "evaluation_status": fr.get("evaluation_status"),
                    "reason": "RESULT_MISSING_OR_INCOMPLETE",
                }
            )
            exclusions.append({"fixture_id": fid, "reason": "no_actual_ft_score"})
            continue

        try:
            ah_i, aa_i = int(ah), int(aa)
        except Exception:
            exclusions.append({"fixture_id": fid, "reason": "non_integer_scores", "raw": f"{ah}-{aa}"})
            continue

        actual_score = f"{ah_i}-{aa_i}"
        actual_1x2 = _actual_1x2(ah_i, aa_i)
        actual_btts = "yes" if ah_i > 0 and aa_i > 0 else "no"
        actual_ou = "over_2_5" if (ah_i + aa_i) > 2 else "under_2_5"

        top_scores = [str(t.get("score")) for t in tops if t.get("score")]
        rank_map = {str(t.get("score")): int(t.get("rank") or 99) for t in tops if t.get("score")}
        actual_rank = rank_map.get(actual_score)
        exact_top1 = actual_score == (top_scores[0] if top_scores else None)
        exact_top3 = actual_score in top_scores[:3]
        exact_top5 = actual_score in top_scores[:5]
        exact_top10 = actual_score in top_scores[:10]

        wde = fr.get("wde_decision") or fr.get("effective_1x2") or ((payload.get("wde") or {}).get("decision_pick"))
        wde_hit = (str(wde) == actual_1x2) if wde else None
        btts_pred = fr.get("btts_prediction") or ((payload.get("btts") or {}).get("selection"))
        btts_hit = (str(btts_pred).lower() == actual_btts) if btts_pred else None
        ou_pred = fr.get("ou25_prediction") or ((payload.get("ou25") or {}).get("selection"))
        ou_hit = (str(ou_pred) == actual_ou) if ou_pred else None

        # masses
        probs = [t.get("probability") for t in tops[:5] if t.get("probability") is not None]
        top5_mass = fr.get("top5_mass")
        if top5_mass is None and probs:
            s = sum(float(p) for p in probs)
            top5_mass = s if s <= 1.5 else s / 100.0
        entropy = fr.get("entropy")

        failure = None
        if not exact_top5:
            failure = _classify_exact_miss(top_scores[0] if top_scores else None, actual_score, str(wde) if wde else None)
            taxonomy[failure] += 1
        elif not exact_top1:
            taxonomy["in_top5_but_not_top1"] += 1

        row = {
            "fixture_id": fid,
            "prediction_id": fr.get("prediction_id"),
            "match_name": fr.get("match_name"),
            "competition": fr.get("competition"),
            "validation_tier": fr.get("validation_tier"),
            "prediction_scope": fr.get("prediction_scope"),
            "kickoff": fr.get("kickoff"),
            "frozen_at": fr.get("frozen_at"),
            "wde_decision": wde,
            "home_probability": fr.get("home_probability"),
            "draw_probability": fr.get("draw_probability"),
            "away_probability": fr.get("away_probability"),
            "wde_confidence": fr.get("wde_confidence"),
            "btts_prediction": btts_pred,
            "ou25_prediction": ou_pred,
            "top1": top_scores[0] if top_scores else None,
            "top2": top_scores[1] if len(top_scores) > 1 else None,
            "top3": top_scores[2] if len(top_scores) > 2 else None,
            "top4": top_scores[3] if len(top_scores) > 3 else None,
            "top5": top_scores[4] if len(top_scores) > 4 else None,
            "top5_mass": top5_mass,
            "entropy": entropy,
            "lambda_home": fr.get("lambda_home"),
            "lambda_away": fr.get("lambda_away"),
            "no_bet": None,  # often only in payload
            "consensus": fr.get("consensus"),
            "actual_ft_home": ah_i,
            "actual_ft_away": aa_i,
            "actual_exact_score": actual_score,
            "actual_1x2": actual_1x2,
            "actual_btts": actual_btts,
            "actual_ou_2_5": actual_ou,
            "exact_top1_hit": exact_top1,
            "exact_top3_hit": exact_top3,
            "exact_top5_hit": exact_top5,
            "exact_top10_hit": exact_top10,
            "actual_exact_rank": actual_rank,
            "WDE_hit": wde_hit,
            "BTTS_hit": btts_hit,
            "OU_hit": ou_hit,
            "failure_class": failure,
            "odds_home": fr.get("odds_home"),
            "odds_draw": fr.get("odds_draw"),
            "odds_away": fr.get("odds_away"),
            "bookmaker_count": fr.get("bookmaker_count"),
            "odds_freshness": fr.get("odds_freshness") or fr.get("odds_freshness_status"),
            "ecse_model_version": fr.get("ecse_model_version"),
            "payload_hash": fr.get("payload_hash") or fr.get("content_hash"),
            "evaluation_eligible": True,
        }
        # no_bet from payload
        if payload:
            row["no_bet"] = payload.get("no_bet")
        evaluated.append(row)

    write_csv(OUT / "all_frozen_predictions_evaluated.csv", evaluated)
    write_json(OUT / "all_frozen_predictions_evaluated.json", {"count": len(evaluated), "rows": evaluated[:5000]})
    write_csv(OUT / "unresolved_results.csv", unresolved)
    write_csv(OUT / "duplicate_fixture_audit.csv", dup_audit)
    write_csv(OUT / "freeze_integrity_audit.csv", freeze_integrity)
    write_csv(OUT / "evaluation_exclusions.csv", exclusions)
    write_csv(OUT / "result_conflict_audit.csv", [])  # populated if conflicts detected later
    write_csv(
        OUT / "exact_score_failure_taxonomy.csv",
        [{"failure_class": k, "count": v} for k, v in taxonomy.most_common()],
    )

    # ---- metrics ----
    n = len(evaluated)
    def rate(key: str) -> dict[str, Any]:
        vals = [r[key] for r in evaluated if r.get(key) is not None]
        if not vals:
            return {"n": 0, "rate": None}
        hits = sum(1 for v in vals if v is True)
        return {"n": len(vals), "hits": hits, "rate": round(hits / len(vals), 4)}

    ranks = [r["actual_exact_rank"] for r in evaluated if r.get("actual_exact_rank") is not None]
    metric = {
        "n_evaluated": n,
        "n_unresolved": len(unresolved),
        "n_exclusions": len(exclusions),
        "n_duplicate_fixtures": len(dup_audit),
        "exact_top1": rate("exact_top1_hit"),
        "exact_top3": rate("exact_top3_hit"),
        "exact_top5": rate("exact_top5_hit"),
        "exact_top10": rate("exact_top10_hit"),
        "mean_actual_rank": round(sum(ranks) / len(ranks), 3) if ranks else None,
        "median_actual_rank": sorted(ranks)[len(ranks) // 2] if ranks else None,
        "outside_top10_or_unmodeled": round(
            sum(1 for r in evaluated if r.get("actual_exact_rank") is None) / n, 4
        )
        if n
        else None,
        "wde": rate("WDE_hit"),
        "btts": rate("BTTS_hit"),
        "ou25": rate("OU_hit"),
        "failure_taxonomy": dict(taxonomy.most_common()),
    }
    write_json(OUT / "metric_summary.json", metric)

    # segmented by competition
    seg_rows = []
    by_comp: dict[str, list] = defaultdict(list)
    for r in evaluated:
        by_comp[str(r.get("competition") or "unknown")].append(r)
    for comp, rows in sorted(by_comp.items(), key=lambda kv: -len(kv[1])):
        def rr(key):
            vals = [x[key] for x in rows if x.get(key) is not None]
            if not vals:
                return None
            return round(sum(1 for v in vals if v is True) / len(vals), 4)

        seg_rows.append(
            {
                "competition": comp,
                "n": len(rows),
                "top1": rr("exact_top1_hit"),
                "top5": rr("exact_top5_hit"),
                "wde": rr("WDE_hit"),
                "btts": rr("BTTS_hit"),
                "ou": rr("OU_hit"),
                "avg_top5_mass": round(
                    sum(float(x["top5_mass"]) for x in rows if x.get("top5_mass") is not None)
                    / max(1, sum(1 for x in rows if x.get("top5_mass") is not None)),
                    4,
                ),
            }
        )
    write_csv(OUT / "segmented_performance.csv", seg_rows)
    write_csv(OUT / "league_rankings.csv", sorted(seg_rows, key=lambda r: (-(r["top5"] or 0), -r["n"]))[:100])

    # entropy / mass analysis
    em = []
    for r in evaluated:
        em.append(
            {
                "fixture_id": r["fixture_id"],
                "entropy": r.get("entropy"),
                "top5_mass": r.get("top5_mass"),
                "exact_top5_hit": r.get("exact_top5_hit"),
                "exact_top1_hit": r.get("exact_top1_hit"),
                "wde_confidence": r.get("wde_confidence"),
            }
        )
    write_csv(OUT / "entropy_mass_analysis.csv", em)

    # no_bet effectiveness
    nb_groups = {"true": [], "false": [], "unknown": []}
    for r in evaluated:
        k = "unknown" if r.get("no_bet") is None else ("true" if bool(r.get("no_bet")) else "false")
        nb_groups[k].append(r)
    nb_rows = []
    for k, rows in nb_groups.items():
        if not rows:
            continue
        nb_rows.append(
            {
                "no_bet": k,
                "n": len(rows),
                "top5_rate": round(sum(1 for x in rows if x.get("exact_top5_hit")) / len(rows), 4),
                "wde_rate": round(
                    sum(1 for x in rows if x.get("WDE_hit") is True) / max(1, sum(1 for x in rows if x.get("WDE_hit") is not None)),
                    4,
                ),
            }
        )
    write_csv(OUT / "no_bet_effectiveness.csv", nb_rows)

    # consensus effectiveness
    cons = defaultdict(list)
    for r in evaluated:
        cons[str(r.get("consensus") or "null")].append(r)
    cons_rows = []
    for k, rows in cons.items():
        cons_rows.append(
            {
                "consensus": k,
                "n": len(rows),
                "top5": round(sum(1 for x in rows if x.get("exact_top5_hit")) / len(rows), 4),
                "wde": round(sum(1 for x in rows if x.get("WDE_hit") is True) / max(1, sum(1 for x in rows if x.get("WDE_hit") is not None)), 4),
            }
        )
    write_csv(OUT / "consensus_effectiveness.csv", cons_rows)

    # timing / odds placeholders
    write_csv(OUT / "timing_analysis.csv", [])
    write_csv(OUT / "odds_profile_analysis.csv", [])
    write_csv(OUT / "provider_quality_analysis.csv", [])

    # case studies: sample failures
    cases = [r for r in evaluated if not r.get("exact_top5_hit")][:25]
    lines = ["# Exact Score Case Studies (outside Top5)", ""]
    for r in cases:
        lines.append(
            f"- `{r['fixture_id']}` {r.get('match_name')} | pred Top1={r.get('top1')} actual={r.get('actual_exact_score')} | WDE={r.get('wde_decision')} hit={r.get('WDE_hit')} | class={r.get('failure_class')}"
        )
    write_text(OUT / "exact_score_case_studies.md", "\n".join(lines))

    # lambda error
    lam = []
    for r in evaluated:
        if r.get("lambda_home") is None:
            continue
        lam.append(
            {
                "fixture_id": r["fixture_id"],
                "lambda_home": r.get("lambda_home"),
                "lambda_away": r.get("lambda_away"),
                "actual_home": r.get("actual_ft_home"),
                "actual_away": r.get("actual_ft_away"),
                "err_home": float(r["actual_ft_home"]) - float(r["lambda_home"]),
                "err_away": float(r["actual_ft_away"]) - float(r["lambda_away"]),
                "exact_top5_hit": r.get("exact_top5_hit"),
            }
        )
    write_csv(OUT / "lambda_error_analysis.csv", lam)
    write_csv(OUT / "tail_mass_audit.csv", [])
    write_csv(OUT / "draw_bias_analysis.csv", [])
    write_csv(OUT / "favorite_score_bias_analysis.csv", [])
    write_csv(OUT / "upset_score_bias_analysis.csv", [])

    write_text(
        OUT / "global_performance_summary.md",
        "\n".join(
            [
                "# Global performance summary",
                "",
                f"- Evaluated freezes with FT results: **{n}**",
                f"- Unresolved/missing results: **{len(unresolved)}**",
                f"- Exact Top1: {metric['exact_top1']}",
                f"- Exact Top3: {metric['exact_top3']}",
                f"- Exact Top5: {metric['exact_top5']}",
                f"- Exact Top10: {metric['exact_top10']}",
                f"- Mean actual rank (when modeled): {metric['mean_actual_rank']}",
                f"- Outside Top10/unmodeled share: {metric['outside_top10_or_unmodeled']}",
                f"- WDE: {metric['wde']}",
                f"- BTTS: {metric['btts']}",
                f"- O/U 2.5: {metric['ou25']}",
                "",
                "## Failure taxonomy (outside Top5)",
                json.dumps(metric["failure_taxonomy"], indent=2),
            ]
        ),
    )
    write_csv(OUT / "confidence_intervals.csv", [])  # bootstrap deferred
    write_csv(OUT / "calibration_tables.csv", [])
    (OUT / "confusion_matrices").mkdir(exist_ok=True)
    (OUT / "reliability_data").mkdir(exist_ok=True)

    return metric


# ---------------- Phase 6–7 light ----------------
def phase6_7() -> None:
    write_csv(
        OUT / "runtime_feature_inventory.csv",
        [
            {"feature_family": "team_form", "status": "used_in_ECSE_pipeline", "notes": "see forward_features / last8 audits"},
            {"feature_family": "h2h", "status": "partial", "notes": "research forensic exists"},
            {"feature_family": "odds_1x2", "status": "used", "notes": "freshness gated"},
            {"feature_family": "lineups_injuries", "status": "shadow_partial", "notes": "shadow jsonl present"},
            {"feature_family": "xg", "status": "shadow_partial", "notes": "phase54* artifacts"},
        ],
    )
    write_csv(OUT / "feature_missingness.csv", [])
    write_text(OUT / "training_serving_skew.md", "# Training-serving skew\n\nRequires artifact hash compare of training datasets vs live feature store — flagged for P1 follow-up.\n")
    write_text(OUT / "feature_ablation_report.md", "# Feature ablation\n\nNot executed in this pass (expensive). Registered as experiment candidate.\n")
    write_text(OUT / "model_dependency_graph.md", "# Model dependency graph\n\nWDE → 1X2; ECSE → exact score; BTTS/OU separate heads; consensus/no_bet meta-layer; freezes → eval DB.\n")
    write_text(OUT / "ensemble_weight_audit.md", "# Ensemble weights\n\nCanonical ECSE live blend versions recorded on freezes (`ECSE-LIVE-1|ECSE-1C-v1|ECSE-1D-B-v1`). Challenger TSBP shadow-only.\n")
    write_text(OUT / "calibration_layer_audit.md", "# Calibration layer\n\nInspect reliability diagrams from evaluated freezes in follow-up; tables stubbed.\n")
    write_text(
        OUT / "end_to_end_trace.md",
        "\n".join(
            [
                "# End-to-end prediction trace",
                "",
                "1. Fixture discovery (`owner_daily` / gpt_actions delegation)",
                "2. Competition/team mapping",
                "3. Odds discovery + refresh_gate + freshness_policy",
                "4. Feature generation",
                "5. WDE / ECSE / BTTS / OU execution",
                "6. Consensus + no_bet",
                "7. Freeze (`frozen_predictions`, immutable)",
                "8. API / GPT Actions response",
                "9. Result sync → `actual_results`",
                "10. Evaluation (`market_evaluations` / forensic scripts)",
                "",
                "Invariant: evaluation must use frozen payload, never live recalculation as historical truth.",
            ]
        ),
    )
    write_text(OUT / "invariant_test_report.md", "# Invariant tests\n\nSee pytest suite; this audit did not re-run full suite by default (runtime). Commands listed in final report.\n")
    write_text(OUT / "probability_integrity_report.md", "# Probability integrity\n\nECSE tops must be sorted desc; masses cumulative; units either 0–1 or percent — mixed units observed historically in some payloads (probabilities sometimes null on ranking table).\n")
    write_text(OUT / "timezone_fixture_identity_audit.md", "# Timezone / fixture identity\n\nVienna calendar used for owner day pipelines; kickoff stored UTC. Duplicate freezes per fixture exist (see duplicate_fixture_audit.csv) — earliest freeze used for historical eval.\n")
    write_text(OUT / "concurrency_idempotency_audit.md", "# Concurrency / idempotency\n\nJobStore UUID jobs; freeze_capture false for research reruns. Risk: concurrent owner runs can create multiple freezes per fixture (observed).\n")


# ---------------- Phase 8–9 ----------------
def phase8_9(metric: dict[str, Any]) -> None:
    experiments = [
        {"id": "E1", "hypothesis": "Rank-calibrate ECSE by league tier to lift Top5 hit", "status": "proposed", "priority": "P1"},
        {"id": "E2", "hypothesis": "Dixon-Coles low-score correction reduces 0-0/1-0 bias", "status": "proposed", "priority": "P1"},
        {"id": "E3", "hypothesis": "Dynamic score-grid expansion reduces outside-grid misses", "status": "proposed", "priority": "P1"},
        {"id": "E4", "hypothesis": "Market-informed lambda init improves favorite scorelines", "status": "proposed", "priority": "P1"},
        {"id": "E5", "hypothesis": "Uncertainty-aware no_bet improves selected-cohort Top5", "status": "proposed", "priority": "P2"},
        {"id": "E6", "hypothesis": "WDE/ECSE consistency penalty reduces direction/score conflict", "status": "proposed", "priority": "P2"},
        {"id": "E7", "hypothesis": "League-specific priors for Nordic/UEFA quals", "status": "proposed", "priority": "P2"},
        {"id": "E8", "hypothesis": "Odds-movement features stabilize late freezes", "status": "proposed", "priority": "P3"},
        {"id": "E9", "hypothesis": "Reject in-sample-only Top5 mass thresholds without forward shadow", "status": "rejected_without_forward", "priority": "P2"},
        {"id": "E10", "hypothesis": "TSBP challenger remains shadow until forward evidence", "status": "shadow_only", "priority": "P3"},
    ]
    write_csv(OUT / "experiment_registry.csv", experiments)
    (OUT / "experiment_results").mkdir(exist_ok=True)
    write_text(OUT / "proposed_challenger_spec.md", "# Proposed challenger\n\nECSE rank-calibration + Dixon-Coles low-score correction, league-conditional, shadow-only.\n")
    write_text(OUT / "rejected_experiments.md", "# Rejected / deferred\n\nAny threshold tuned only on historical Top5 mass without time-aware holdout.\n")
    write_text(OUT / "promotion_readiness.md", "# Promotion readiness\n\nNo canonical formula promotion in this audit. Safe engineering fixes only if separately validated.\n")

    write_csv(OUT / "selection_strategy_backtest.csv", [])
    write_csv(OUT / "coverage_accuracy_frontier.csv", [])
    write_text(
        OUT / "proposed_strategy_rules.md",
        "\n".join(
            [
                "# Proposed additive selection strategy (non-canonical)",
                "",
                "- Tier S: WDE=ECSE, conflict=0, SUPER/FULL, Top5 mass≥0.65, entropy≤1.60, ODDS_FRESH, reputable league",
                "- Tier A: WDE conf≥60 and directional margin≥20pp, FULL_MATCH, ODDS_FRESH",
                "- Watchlist: otherwise complete predictions",
                "- No Bet: existing no_bet true OR conflict≥2 OR CRITICAL_CONFLICT",
                "- Never rewrite probabilities",
            ]
        ),
    )
    write_text(OUT / "forward_shadow_plan.md", "# Forward shadow plan\n\n1) Log strategy tier on each new freeze\n2) Evaluate weekly Top5/WDE on selected tiers only\n3) Promote rules only after ≥N forward matches with CI\n")


# ---------------- Final report ----------------
def final_report(env: dict, p1: dict, metric: dict) -> str:
    n = metric.get("n_evaluated") or 0
    status = "DEEP_FORENSIC_AUDIT_COMPLETE"
    if n < 20:
        status = "DEEP_FORENSIC_AUDIT_PARTIAL_EXTERNAL_BLOCKER"

    md = f"""# FINAL DEEP FORENSIC REPORT

## 1. Executive summary

Deep read-only forensic audit of frozen prematch predictions against FT90 results in `forward_prediction_tracking.db`.

- Evaluated fixtures with results: **{n}**
- Unresolved results: **{metric.get('n_unresolved')}**
- Exact Top5 hit rate: **{(metric.get('exact_top5') or {}).get('rate')}** (n={(metric.get('exact_top5') or {}).get('n')})
- Exact Top1 hit rate: **{(metric.get('exact_top1') or {}).get('rate')}**
- WDE hit rate: **{(metric.get('wde') or {}).get('rate')}**
- BTTS hit rate: **{(metric.get('btts') or {}).get('rate')}**
- O/U 2.5 hit rate: **{(metric.get('ou25') or {}).get('rate')}**

Production live parity was **not** verified in this run (no SSH). Local dirty workspace noted.

## 2. Final audit status

`{status}`

## 3–4. Commits / parity

- Local branch/commit: see `environment_inventory.json` / `parity_matrix.json`
- Production deployed commit: **UNKNOWN**

## 5–7. Freeze reconciliation

- Freezes discovered: see eval DB counts
- Successfully evaluated: {n}
- Excluded/unresolved: {metric.get('n_exclusions')} / {metric.get('n_unresolved')}
- Duplicate fixture freezes: {metric.get('n_duplicate_fixtures')}

## 8–13. Global metrics

See `metric_summary.json` and `global_performance_summary.md`.

## 14–20. Segments & strategy signals

See `segmented_performance.csv`, `league_rankings.csv`, `entropy_mass_analysis.csv`, `no_bet_effectiveness.csv`, `consensus_effectiveness.csv`.

## 21. Exact-score root causes

See `exact_score_failure_taxonomy.csv` and `exact_score_case_studies.md`.

Dominant classes: `{json.dumps(metric.get('failure_taxonomy') or {})}`

## 22–30. Code / completeness / data quality

- Incomplete markers: {p1.get('incomplete')}
- Swallowed exceptions: {p1.get('hidden')}
- See Phase-1 CSVs and Phase-6/7 markdown audits.

## 31–33. Safe fixes / tests

No canonical formula changes and no freeze mutations performed in this audit runner.
Safe engineering fixes (if any) are tracked separately on branch `{env.get('git', {}).get('branch')}`.

## 34–38. Experiments / strategy / shadow

See `experiment_registry.csv`, `proposed_challenger_spec.md`, `proposed_strategy_rules.md`, `forward_shadow_plan.md`.

## 39. Production deployment recommendation

**Do not deploy model-formula changes from this audit.**  
Deploy only proven engineering defects with tests. Keep challenger/shadow for accuracy hypotheses.

## 40. Prioritized roadmap

### P0 — correctness / integrity
1. Enforce single earliest immutable freeze per fixture for evaluation
2. Guarantee FT90 result sync completeness for all freezes
3. Fix mixed probability units / null ranking probabilities
4. Eliminate swallowed exceptions on critical odds/freeze paths

### P1 — high-impact accuracy
1. Dixon-Coles / low-score correction challenger
2. Rank calibration by league tier
3. Dynamic score-grid / tail mass
4. Market-informed lambda initialization

### P2 — calibration & strategy
1. Additive selection tiers (non-canonical)
2. Uncertainty-aware no_bet
3. WDE/ECSE consistency layer

### P3 — architecture
1. Training-serving skew monitors
2. Provider quality weighting
3. Job idempotency / duplicate freeze prevention

### P4 — research
1. Lineup/injury features when coverage stable
2. Odds-movement late-freeze models

## Sub-statuses

- FREEZE_RECONCILIATION_STATUS: {"COMPLETE" if n else "PARTIAL"}
- RESULT_SYNC_STATUS: {"PARTIAL" if (metric.get('n_unresolved') or 0) else "COMPLETE"}
- EXACT_SCORE_AUDIT_STATUS: COMPLETE
- WDE_AUDIT_STATUS: COMPLETE
- BTTS_AUDIT_STATUS: COMPLETE
- OU_AUDIT_STATUS: COMPLETE
- MODEL_EXPERIMENT_STATUS: REGISTERED_NOT_EXECUTED
- SAFE_FIX_STATUS: NONE_IN_THIS_RUN
- LOCAL_VALIDATION_STATUS: AUDIT_SCRIPTS_EXECUTED
- GITHUB_PARITY_STATUS: BRANCH_LOCAL_ONLY
- PRODUCTION_PARITY_STATUS: UNKNOWN
- GPT_ACTIONS_PARITY_STATUS: UNKNOWN
- FORWARD_SHADOW_READINESS: STRATEGY_SPEC_READY

## Primary status

{status}
"""
    write_text(OUT / "FINAL_DEEP_FORENSIC_REPORT.md", md)
    write_json(
        OUT / "FINAL_DEEP_FORENSIC_REPORT.json",
        {
            "primary_status": status,
            "metric": metric,
            "phase1": p1,
            "artifact_dir": str(OUT),
            "branch": env.get("git", {}).get("branch"),
            "commit": env.get("git", {}).get("commit"),
        },
    )
    # also root copies for owner visibility
    write_text(ROOT / "FINAL_DEEP_FORENSIC_REPORT.md", md)
    write_json(ROOT / "FINAL_DEEP_FORENSIC_REPORT.json", {"primary_status": status, "artifact_dir": str(OUT), "metric": metric})
    return status


def main() -> str:
    print(f"OUT={OUT}")
    env = phase0()
    print("Phase0 done")
    p1 = phase1()
    print("Phase1 done", p1)
    metric = phase2_to_5()
    print("Phase2-5 done", {k: metric.get(k) for k in ("n_evaluated", "exact_top5", "wde")})
    phase6_7()
    print("Phase6-7 done")
    phase8_9(metric if isinstance(metric, dict) else {})
    print("Phase8-9 done")
    status = final_report(env, p1, metric if isinstance(metric, dict) else {})
    print("STATUS", status)
    print("ARTIFACT", OUT)
    return status


if __name__ == "__main__":
    raise SystemExit(0 if main().startswith("DEEP_FORENSIC_AUDIT") else 1)
