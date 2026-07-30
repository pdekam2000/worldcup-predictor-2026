#!/usr/bin/env python3
"""Phase A–D: result reconciliation, duplicate freeze forensics, clean datasets, corrected metrics.

Does NOT mutate frozen prediction payloads. Writes only to actual_results via sync_result_for_fixture
and research artifacts under artifacts/dataset_reconciliation_experiments/<run_id>/.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Prefer production env for provider credentials when present (never print secrets).
os.environ.setdefault("APP_ENV", os.environ.get("APP_ENV") or "production")
prod_env = ROOT / ".env.production"
if prod_env.is_file():
    os.environ.setdefault("ENV_FILE", str(prod_env))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = ROOT / "artifacts" / "dataset_reconciliation_experiments" / RUN_ID
PREV = ROOT / "artifacts" / "deep_model_forensic_audit" / "20260730T115455Z"
TERMINAL = {"FT", "AET", "PEN", "FINISHED", "AWD", "WO"}
# Synthetic/unit-test fixture IDs live in the 900000–999999 band.
# Real API-Football IDs are typically >= 1_000_000 (e.g. 1494225).
TEST_FIXTURE_LO = 900000
TEST_FIXTURE_HI = 1000000


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    k: (
                        json.dumps(v, default=str)
                        if isinstance(v, (dict, list))
                        else ("" if v is None else v)
                    )
                    for k, v in r.items()
                }
            )


def fnum(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def jload(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def as_fraction(p: float | None) -> float | None:
    if p is None:
        return None
    if p > 1.5:  # percent-like
        return p / 100.0
    return p


def bootstrap_ci(hits: list[bool], n_boot: int = 1500, alpha: float = 0.05) -> dict[str, Any]:
    n = len(hits)
    if n == 0:
        return {"n": 0, "rate": None, "ci_low": None, "ci_high": None}
    rate = sum(hits) / n
    rng = random.Random(42)
    stats = sorted(sum(hits[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return {
        "n": n,
        "rate": round(rate, 4),
        "ci_low": round(stats[int((alpha / 2) * n_boot)], 4),
        "ci_high": round(stats[int((1 - alpha / 2) * n_boot) - 1], 4),
    }


def actual_1x2(h: int, a: int) -> str:
    if h > a:
        return "home_win"
    if h < a:
        return "away_win"
    return "draw"


def tops_from_freeze(fr: dict[str, Any], con: sqlite3.Connection) -> list[dict[str, Any]]:
    payload = jload(fr.get("complete_payload_json")) or {}
    ecse = payload.get("ecse") or {}
    tops: list[dict[str, Any]] = []
    t10 = ecse.get("top10") or []
    if t10:
        for item in sorted(t10, key=lambda x: int(x.get("rank") or 99)):
            score = item.get("scoreline") or item.get("score")
            tops.append(
                {
                    "rank": int(item.get("rank") or len(tops) + 1),
                    "score": score,
                    "probability": fnum(item.get("probability")),
                }
            )
    if len(tops) < 5:
        for i in range(1, 11):
            cell = ecse.get(f"top{i}")
            if isinstance(cell, dict):
                tops.append(
                    {
                        "rank": i,
                        "score": cell.get("score") or cell.get("scoreline"),
                        "probability": fnum(cell.get("probability")),
                    }
                )
            elif isinstance(cell, str):
                tops.append({"rank": i, "score": cell, "probability": None})
    if len(tops) < 5:
        ranks = con.execute(
            "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
            (fr.get("prediction_id"),),
        ).fetchall()
        for r in ranks:
            tops.append({"rank": r["rank"], "score": r["score"], "probability": fnum(r["probability"])})
    # dedupe by score keep best rank
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for t in sorted(tops, key=lambda x: int(x.get("rank") or 99)):
        sc = str(t.get("score") or "")
        if not sc or sc in seen:
            continue
        seen.add(sc)
        out.append(t)
    # backfill probs from top10 by score if needed
    prob_map = {
        str(t.get("scoreline") or t.get("score")): fnum(t.get("probability"))
        for t in (ecse.get("top10") or [])
        if isinstance(t, dict)
    }
    for t in out:
        if t.get("probability") is None and str(t.get("score")) in prob_map:
            t["probability"] = prob_map[str(t.get("score"))]
    return out[:10]


def is_test_fixture(fid: int, match_name: str | None) -> bool:
    n = int(fid)
    if TEST_FIXTURE_LO <= n < TEST_FIXTURE_HI:
        return True
    name = str(match_name or "")
    return "Alpha FC" in name and "Beta FC" in name


# ---------------- Phase A ----------------
def phase_a(prod: sqlite3.Connection, ev: sqlite3.Connection) -> dict[str, Any]:
    missing = [
        int(r[0])
        for r in ev.execute(
            """
            SELECT DISTINCT f.fixture_id
            FROM frozen_predictions f
            LEFT JOIN actual_results a ON a.fixture_id = f.fixture_id
            WHERE a.fixture_id IS NULL
            ORDER BY f.fixture_id
            """
        )
    ]
    attempts: list[dict[str, Any]] = []
    newly: list[dict[str, Any]] = []
    still: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for fid in missing:
        fr = ev.execute(
            "SELECT match_name, kickoff, competition FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at LIMIT 1",
            (fid,),
        ).fetchone()
        match_name = fr["match_name"] if fr else None
        testish = is_test_fixture(fid, match_name)
        # Skip provider calls for synthetic test fixtures
        allow_provider = not testish
        try:
            out = sync_result_for_fixture(
                fid,
                prod_conn=prod,
                eval_conn=ev,
                dry_run=False,
                allow_provider_fetch=allow_provider,
            )
        except Exception as exc:
            out = {
                "fixture_id": fid,
                "status": "error",
                "result_available": False,
                "reason": f"exception:{type(exc).__name__}",
            }
        row = {
            "fixture_id": fid,
            "match_name": match_name,
            "kickoff": fr["kickoff"] if fr else None,
            "competition": fr["competition"] if fr else None,
            "is_test_fixture": testish,
            "allow_provider_fetch": allow_provider,
            "status": out.get("status"),
            "reason": out.get("reason"),
            "result_available": out.get("result_available"),
            "regulation_score": out.get("regulation_score"),
            "result_quality_status": out.get("result_quality_status"),
            "provider": out.get("provider"),
            "conflict": out.get("conflict"),
            "inserted": out.get("inserted"),
            "reused": out.get("reused"),
        }
        attempts.append(row)
        if out.get("conflict"):
            conflicts.append(row)
        # check if actual_results now present with FT goals
        ar = ev.execute("SELECT * FROM actual_results WHERE fixture_id=?", (fid,)).fetchone()
        if ar and ar["actual_home_goals"] is not None and ar["actual_away_goals"] is not None:
            newly.append(
                {
                    **row,
                    "actual_home_goals": ar["actual_home_goals"],
                    "actual_away_goals": ar["actual_away_goals"],
                    "actual_score": ar["actual_score"],
                    "result_source": ar["result_source"],
                    "result_quality_status": ar["result_quality_status"],
                    "score_basis": ar["score_basis"] if "score_basis" in ar.keys() else None,
                }
            )
        else:
            still.append({**row, "final_reason": out.get("reason") or "unresolved"})

    write_csv(OUT / "result_sync_attempts.csv", attempts)
    write_csv(OUT / "newly_resolved_results.csv", newly)
    write_csv(OUT / "still_unresolved_results.csv", still)
    write_csv(OUT / "result_provider_conflicts.csv", conflicts)
    summary = {
        "missing_before": len(missing),
        "attempts": len(attempts),
        "newly_resolved": len(newly),
        "still_unresolved": len(still),
        "conflicts": len(conflicts),
        "test_fixtures_skipped_provider": sum(1 for a in attempts if a.get("is_test_fixture")),
        "real_attempts": sum(1 for a in attempts if not a.get("is_test_fixture")),
    }
    write_text(
        OUT / "result_sync_summary.md",
        "\n".join(
            [
                "# Result sync summary",
                "",
                f"- Missing fixtures before sync: **{summary['missing_before']}**",
                f"- Newly resolved: **{summary['newly_resolved']}**",
                f"- Still unresolved: **{summary['still_unresolved']}**",
                f"- Provider conflicts: **{summary['conflicts']}**",
                f"- Test/synthetic fixtures (no provider fetch): **{summary['test_fixtures_skipped_provider']}**",
                f"- Real fixture attempts: **{summary['real_attempts']}**",
                "",
                "Resolution order: eval actual_results → production fixture_results → API-Football provider → explicit unresolved.",
                "FT90 only via regulation score policy; ET/PEN not treated as FT90.",
                "Historical frozen prediction payloads were not mutated.",
            ]
        ),
    )
    write_json(OUT / "result_sync_summary.json", summary)
    return summary


# ---------------- Phase B ----------------
def classify_timing(hours: float | None) -> str:
    if hours is None:
        return "UNKNOWN"
    if hours < 0:
        return "POST_KICKOFF"
    if hours < 6:
        return "LATE"
    if hours < 24:
        return "MID"
    if hours < 72:
        return "EARLY"
    return "VERY_EARLY"


def phase_b(ev: sqlite3.Connection) -> dict[str, Any]:
    by_fix: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in ev.execute("SELECT * FROM frozen_predictions"):
        d = dict(r)
        by_fix[int(d["fixture_id"])].append(d)

    groups = []
    classifications = []
    drift_rows = []
    first_vs_last = []

    for fid, rows in by_fix.items():
        if len(rows) < 2:
            continue
        rows_sorted = sorted(rows, key=lambda r: str(r.get("frozen_at") or ""))
        kickoff = parse_dt(rows_sorted[0].get("kickoff"))
        items = []
        for fr in rows_sorted:
            frozen_at = parse_dt(fr.get("frozen_at"))
            hours = None
            if kickoff and frozen_at:
                hours = (kickoff - frozen_at).total_seconds() / 3600.0
            prematch = hours is not None and hours >= 0
            items.append(
                {
                    "fixture_id": fid,
                    "prediction_id": fr.get("prediction_id"),
                    "frozen_at": fr.get("frozen_at"),
                    "kickoff": fr.get("kickoff"),
                    "hours_to_kickoff": round(hours, 3) if hours is not None else None,
                    "timing_bucket": classify_timing(hours),
                    "prematch_valid": prematch,
                    "odds_timestamp": fr.get("odds_timestamp") or fr.get("odds_fetched_at_utc"),
                    "wde_decision": fr.get("wde_decision"),
                    "wde_model_version": fr.get("wde_model_version"),
                    "ecse_model_version": fr.get("ecse_model_version"),
                    "top5_mass": fr.get("top5_mass"),
                    "entropy": fr.get("entropy"),
                    "payload_hash": fr.get("payload_hash") or fr.get("content_hash"),
                    "freeze_status": fr.get("freeze_status"),
                    "supersedes_freeze_id": fr.get("supersedes_freeze_id"),
                    "match_name": fr.get("match_name"),
                    "is_test_fixture": is_test_fixture(fid, fr.get("match_name")),
                }
            )
        hashes = {i["payload_hash"] for i in items if i.get("payload_hash")}
        wdes = {i["wde_decision"] for i in items}
        reason = "UNKNOWN_DUPLICATE_REASON"
        if all(i.get("is_test_fixture") for i in items):
            reason = "TEST_FIXTURE_REPEATED_SEED"
        elif len(hashes) == 1:
            reason = "IDENTICAL_PAYLOAD_RETRY"
        elif any(i.get("timing_bucket") != items[0].get("timing_bucket") for i in items):
            reason = "TIMING_EXPERIMENT_OR_REFRESH"
        elif wdes and len(wdes) > 1:
            reason = "MATERIAL_OUTPUT_DRIFT"
        else:
            reason = "ACCIDENTAL_OR_CONCURRENT_JOB"

        groups.append(
            {
                "fixture_id": fid,
                "n_freezes": len(items),
                "prediction_ids": [i["prediction_id"] for i in items],
                "frozen_ats": [i["frozen_at"] for i in items],
                "unique_payload_hashes": len(hashes),
                "unique_wde": len(wdes),
                "duplicate_reason": reason,
                "is_test_fixture": items[0]["is_test_fixture"],
            }
        )
        for i in items:
            classifications.append(
                {
                    **i,
                    "duplicate_reason": reason,
                    "cohort_tags": ",".join(
                        [
                            "ALL_VALID_TIMING_EXPERIMENTS" if i["prematch_valid"] else "INVALID_OR_POST_KICKOFF",
                            "FIRST_VALID_PREMATCH"
                            if i["prediction_id"]
                            == next((x["prediction_id"] for x in items if x["prematch_valid"]), None)
                            else "",
                            "LAST_VALID_PREMATCH"
                            if i["prediction_id"]
                            == next((x["prediction_id"] for x in reversed(items) if x["prematch_valid"]), None)
                            else "",
                        ]
                    ),
                }
            )

        first = next((x for x in items if x["prematch_valid"]), items[0])
        last = next((x for x in reversed(items) if x["prematch_valid"]), items[-1])
        first_vs_last.append(
            {
                "fixture_id": fid,
                "first_id": first["prediction_id"],
                "last_id": last["prediction_id"],
                "same_freeze": first["prediction_id"] == last["prediction_id"],
                "wde_changed": first.get("wde_decision") != last.get("wde_decision"),
                "hash_changed": first.get("payload_hash") != last.get("payload_hash"),
                "hours_first": first.get("hours_to_kickoff"),
                "hours_last": last.get("hours_to_kickoff"),
                "duplicate_reason": reason,
            }
        )
        if first["prediction_id"] != last["prediction_id"]:
            drift_rows.append(
                {
                    "fixture_id": fid,
                    "first_wde": first.get("wde_decision"),
                    "last_wde": last.get("wde_decision"),
                    "first_top5_mass": first.get("top5_mass"),
                    "last_top5_mass": last.get("top5_mass"),
                    "first_entropy": first.get("entropy"),
                    "last_entropy": last.get("entropy"),
                    "material_change": first.get("payload_hash") != last.get("payload_hash")
                    or first.get("wde_decision") != last.get("wde_decision"),
                }
            )

    write_csv(OUT / "duplicate_freeze_groups.csv", groups)
    write_csv(OUT / "duplicate_freeze_classification.csv", classifications)
    write_csv(OUT / "first_vs_last_freeze_performance.csv", first_vs_last)  # filled with hits later
    write_csv(OUT / "prediction_drift_between_freezes.csv", drift_rows)
    write_text(
        OUT / "canonical_freeze_selection_rules.md",
        "\n".join(
            [
                "# Canonical freeze selection rules",
                "",
                "1. Exclude test/synthetic fixtures (fixture_id in 900000–999999 or Alpha FC vs Beta FC).",
                "2. Exclude post-kickoff freezes (`hours_to_kickoff < 0`).",
                "3. Prefer freeze marked ACTIVE with supersedes chain tip if present (`CANONICAL_MARKED_FREEZE`).",
                "4. Else prefer **LAST_VALID_PREMATCH** when odds/freshness metadata is richer; else **FIRST_VALID_PREMATCH** for historical headline stability.",
                "5. Headline dataset uses: last valid prematch freeze with non-null WDE decision; fallback to first valid.",
                "6. All freezes retained in `evaluation_all_valid_freezes` / timing experiment cohorts.",
                "7. Never delete or rewrite freeze rows.",
            ]
        ),
    )
    return {"n_duplicate_groups": len(groups), "n_classified_rows": len(classifications)}


# ---------------- Phase C/D helpers ----------------
def build_eval_row(fr: dict[str, Any], act: dict[str, Any], tops: list[dict[str, Any]], *, selection_reason: str, cohort: str) -> dict[str, Any]:
    ah, aa = int(act["actual_home_goals"]), int(act["actual_away_goals"])
    actual_score = f"{ah}-{aa}"
    top_scores = [str(t.get("score")) for t in tops if t.get("score")]
    rank_map = {str(t.get("score")): int(t.get("rank") or 99) for t in tops if t.get("score")}
    probs = [as_fraction(t.get("probability")) for t in tops[:10]]
    actual_rank = rank_map.get(actual_score)
    wde = fr.get("wde_decision") or fr.get("effective_1x2")
    a1 = actual_1x2(ah, aa)
    ab = "yes" if ah > 0 and aa > 0 else "no"
    ao = "over_2_5" if (ah + aa) > 2 else "under_2_5"
    btts_pred = fr.get("btts_prediction")
    ou_pred = fr.get("ou25_prediction")
    # log loss exact if we have actual prob
    actual_prob = None
    for t in tops:
        if str(t.get("score")) == actual_score:
            actual_prob = as_fraction(t.get("probability"))
            break
    exact_ll = None
    if actual_prob is not None and actual_prob > 0:
        exact_ll = -math.log(max(actual_prob, 1e-12))

    # WDE brier
    hp = as_fraction(fnum(fr.get("home_probability")))
    dp = as_fraction(fnum(fr.get("draw_probability")))
    ap = as_fraction(fnum(fr.get("away_probability")))
    brier = None
    if hp is not None and dp is not None and ap is not None:
        y = {"home_win": (1, 0, 0), "draw": (0, 1, 0), "away_win": (0, 0, 1)}[a1]
        brier = (hp - y[0]) ** 2 + (dp - y[1]) ** 2 + (ap - y[2]) ** 2

    top5_mass = fr.get("top5_mass")
    if top5_mass is None:
        p5 = [as_fraction(t.get("probability")) for t in tops[:5]]
        if all(p is not None for p in p5):
            top5_mass = sum(p5)  # type: ignore

    meta_complete = all(
        [
            fr.get("odds_home") is not None,
            fr.get("top5_mass") is not None or top5_mass is not None,
            any(t.get("probability") is not None for t in tops[:5]),
        ]
    )

    return {
        "fixture_id": fr["fixture_id"],
        "prediction_id": fr["prediction_id"],
        "match_name": fr.get("match_name"),
        "competition": fr.get("competition"),
        "kickoff": fr.get("kickoff"),
        "frozen_at": fr.get("frozen_at"),
        "cohort": cohort,
        "canonical_selection_reason": selection_reason,
        "freeze_source": fr.get("prediction_scope") or fr.get("batch_id"),
        "result_source": act.get("result_source"),
        "result_confidence": act.get("result_quality_status"),
        "fixture_identity_confidence": "HIGH" if not is_test_fixture(int(fr["fixture_id"]), fr.get("match_name")) else "TEST",
        "model_version_wde": fr.get("wde_model_version"),
        "model_version_ecse": fr.get("ecse_model_version"),
        "evaluation_eligible": True,
        "exclusion_reason": None,
        "wde_decision": wde,
        "home_probability": fr.get("home_probability"),
        "draw_probability": fr.get("draw_probability"),
        "away_probability": fr.get("away_probability"),
        "wde_confidence": fr.get("wde_confidence"),
        "btts_prediction": btts_pred,
        "ou25_prediction": ou_pred,
        "lambda_home": fr.get("lambda_home"),
        "lambda_away": fr.get("lambda_away"),
        "top5_mass": top5_mass,
        "entropy": fr.get("entropy"),
        "odds_home": fr.get("odds_home"),
        "odds_draw": fr.get("odds_draw"),
        "odds_away": fr.get("odds_away"),
        "bookmaker_count": fr.get("bookmaker_count"),
        "odds_freshness": fr.get("odds_freshness") or fr.get("odds_freshness_status"),
        "consensus": fr.get("consensus"),
        "no_bet": (jload(fr.get("complete_payload_json")) or {}).get("no_bet"),
        "top1": top_scores[0] if top_scores else None,
        "top2": top_scores[1] if len(top_scores) > 1 else None,
        "top3": top_scores[2] if len(top_scores) > 2 else None,
        "top4": top_scores[3] if len(top_scores) > 3 else None,
        "top5": top_scores[4] if len(top_scores) > 4 else None,
        "actual_ft_home": ah,
        "actual_ft_away": aa,
        "actual_exact_score": actual_score,
        "actual_1x2": a1,
        "actual_btts": ab,
        "actual_ou_2_5": ao,
        "exact_top1_hit": actual_score == (top_scores[0] if top_scores else None),
        "exact_top2_hit": actual_score in top_scores[:2],
        "exact_top3_hit": actual_score in top_scores[:3],
        "exact_top5_hit": actual_score in top_scores[:5],
        "exact_top10_hit": actual_score in top_scores[:10],
        "actual_exact_rank": actual_rank,
        "outside_grid": actual_rank is None,
        "exact_score_log_loss": exact_ll,
        "WDE_hit": (str(wde) == a1) if wde else None,
        "BTTS_hit": (str(btts_pred).lower() == ab) if btts_pred else None,
        "OU_hit": (str(ou_pred) == ao) if ou_pred else None,
        "wde_brier": brier,
        "metadata_complete": meta_complete,
        "is_test_fixture": is_test_fixture(int(fr["fixture_id"]), fr.get("match_name")),
    }


def metrics_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for r in rows if not r.get("is_test_fixture")]
    n = len(rows)
    if n == 0:
        return {"n": 0}

    def rate(key: str) -> dict[str, Any]:
        hits = [bool(r[key]) for r in rows if r.get(key) is not None]
        return bootstrap_ci(hits)

    ranks = [r["actual_exact_rank"] for r in rows if r.get("actual_exact_rank") is not None]
    mae = {}
    for name, fn in [
        ("home_goal_mae", lambda r: abs(float(r["actual_ft_home"]) - float(r["lambda_home"])) if r.get("lambda_home") is not None else None),
        ("away_goal_mae", lambda r: abs(float(r["actual_ft_away"]) - float(r["lambda_away"])) if r.get("lambda_away") is not None else None),
        ("total_goal_mae", lambda r: abs(float(r["actual_ft_home"] + r["actual_ft_away"]) - (float(r["lambda_home"]) + float(r["lambda_away"]))) if r.get("lambda_home") is not None else None),
        ("goal_diff_mae", lambda r: abs(float(r["actual_ft_home"] - r["actual_ft_away"]) - (float(r["lambda_home"]) - float(r["lambda_away"]))) if r.get("lambda_home") is not None else None),
    ]:
        vals = [fn(r) for r in rows]
        vals = [v for v in vals if v is not None]
        mae[name] = round(sum(vals) / len(vals), 4) if vals else None

    lls = [r["exact_score_log_loss"] for r in rows if r.get("exact_score_log_loss") is not None]
    briers = [r["wde_brier"] for r in rows if r.get("wde_brier") is not None]

    # balanced WDE accuracy
    by_cls = defaultdict(list)
    for r in rows:
        if r.get("WDE_hit") is None:
            continue
        by_cls[r["actual_1x2"]].append(bool(r["WDE_hit"]))
    recalls = {k: (sum(v) / len(v) if v else None) for k, v in by_cls.items()}
    bal = None
    if recalls:
        vals = [v for v in recalls.values() if v is not None]
        bal = round(sum(vals) / len(vals), 4) if vals else None

    return {
        "n_rows": n,
        "n_unique_fixtures": len({r["fixture_id"] for r in rows}),
        "exact_top1": rate("exact_top1_hit"),
        "exact_top2": rate("exact_top2_hit"),
        "exact_top3": rate("exact_top3_hit"),
        "exact_top5": rate("exact_top5_hit"),
        "exact_top10": rate("exact_top10_hit"),
        "mean_actual_rank": round(sum(ranks) / len(ranks), 3) if ranks else None,
        "outside_grid_rate": round(sum(1 for r in rows if r.get("outside_grid")) / n, 4),
        "exact_score_log_loss_mean": round(sum(lls) / len(lls), 4) if lls else None,
        "exact_score_log_loss_n": len(lls),
        "wde": rate("WDE_hit"),
        "wde_balanced_accuracy": bal,
        "wde_per_class_recall": recalls,
        "wde_brier_mean": round(sum(briers) / len(briers), 4) if briers else None,
        "btts": rate("BTTS_hit"),
        "ou25": rate("OU_hit"),
        **mae,
    }


def phase_c_d(ev: sqlite3.Connection) -> dict[str, Any]:
    actuals = {int(r["fixture_id"]): dict(r) for r in ev.execute("SELECT * FROM actual_results") if r["actual_home_goals"] is not None}
    freezes_by_fix: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in ev.execute("SELECT * FROM frozen_predictions"):
        freezes_by_fix[int(r["fixture_id"])].append(dict(r))

    all_valid: list[dict[str, Any]] = []
    first_rows: list[dict[str, Any]] = []
    last_rows: list[dict[str, Any]] = []
    canonical_rows: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []
    complete_meta: list[dict[str, Any]] = []

    for fid, rows in freezes_by_fix.items():
        act = actuals.get(fid)
        if not act:
            continue
        rows_sorted = sorted(rows, key=lambda r: str(r.get("frozen_at") or ""))
        kickoff = parse_dt(rows_sorted[0].get("kickoff"))
        valid = []
        for fr in rows_sorted:
            frozen_at = parse_dt(fr.get("frozen_at"))
            hours = (kickoff - frozen_at).total_seconds() / 3600.0 if kickoff and frozen_at else None
            if hours is not None and hours < 0:
                continue
            if is_test_fixture(fid, fr.get("match_name")):
                continue
            tops = tops_from_freeze(fr, ev)
            if len(tops) < 5:
                continue
            valid.append((fr, tops, hours))

        if not valid:
            continue

        for fr, tops, hours in valid:
            row = build_eval_row(fr, act, tops, selection_reason="ALL_VALID_PREMATCH", cohort="all_valid")
            row["hours_to_kickoff"] = round(hours, 3) if hours is not None else None
            row["timing_bucket"] = classify_timing(hours)
            all_valid.append(row)
            timing_rows.append(row)
            if row.get("metadata_complete"):
                complete_meta.append({**row, "cohort": "complete_metadata", "canonical_selection_reason": "COMPLETE_METADATA"})

        first_fr, first_tops, _ = valid[0]
        last_fr, last_tops, _ = valid[-1]
        first_rows.append(
            build_eval_row(first_fr, act, first_tops, selection_reason="FIRST_VALID_PREMATCH", cohort="first_valid")
        )
        last_rows.append(
            build_eval_row(last_fr, act, last_tops, selection_reason="LAST_VALID_PREMATCH", cohort="last_valid")
        )

        # canonical: prefer last with odds, else last, else first
        canon = None
        reason = "LAST_VALID_PREMATCH"
        for fr, tops, hours in reversed(valid):
            if fr.get("odds_home") is not None:
                canon = (fr, tops)
                reason = "LAST_VALID_PREMATCH_WITH_ODDS"
                break
        if canon is None:
            # marked supersedes tip
            tip = [v for v in valid if not any(str(x[0].get("supersedes_freeze_id") or "") == str(v[0].get("prediction_id")) for x in valid)]
            if tip:
                canon = (tip[-1][0], tip[-1][1])
                reason = "CANONICAL_MARKED_OR_LAST"
            else:
                canon = (last_fr, last_tops)
                reason = "LAST_VALID_PREMATCH"
        canonical_rows.append(build_eval_row(canon[0], act, canon[1], selection_reason=reason, cohort="canonical_one_per_fixture"))

    write_csv(OUT / "evaluation_all_valid_freezes.csv", all_valid)
    write_csv(OUT / "evaluation_one_canonical_freeze_per_fixture.csv", canonical_rows)
    write_csv(OUT / "evaluation_first_valid_freeze.csv", first_rows)
    write_csv(OUT / "evaluation_last_valid_freeze.csv", last_rows)
    write_csv(OUT / "evaluation_timing_experiments.csv", timing_rows)
    write_csv(OUT / "evaluation_complete_metadata_only.csv", complete_meta)

    m_all = metrics_for(all_valid)
    m_can = metrics_for(canonical_rows)
    m_first = metrics_for(first_rows)
    m_last = metrics_for(last_rows)
    m_meta = metrics_for(complete_meta)

    corrected = {
        "run_id": RUN_ID,
        "all_valid": m_all,
        "canonical_one_per_fixture": m_can,
        "first_valid": m_first,
        "last_valid": m_last,
        "complete_metadata": m_meta,
    }
    write_json(OUT / "corrected_metric_summary.json", corrected)

    # previous audit metrics
    prev_metric = {}
    prev_path = PREV / "metric_summary.json"
    if prev_path.exists():
        prev_metric = json.loads(prev_path.read_text(encoding="utf-8"))

    def delta(new_m: dict, key: str, prev_key: str) -> dict[str, Any]:
        new_rate = (new_m.get(key) or {}).get("rate")
        old = prev_metric.get(prev_key) or {}
        old_rate = old.get("rate") if isinstance(old, dict) else None
        return {
            "metric": key,
            "previous_rate": old_rate,
            "previous_n": old.get("n") if isinstance(old, dict) else prev_metric.get("n_evaluated"),
            "corrected_rate": new_rate,
            "corrected_n": (new_m.get(key) or {}).get("n"),
            "delta_rate": None if new_rate is None or old_rate is None else round(new_rate - old_rate, 4),
        }

    deltas = [
        delta(m_can, "exact_top1", "exact_top1"),
        delta(m_can, "exact_top3", "exact_top3"),
        delta(m_can, "exact_top5", "exact_top5"),
        delta(m_can, "exact_top10", "exact_top10"),
        delta(m_can, "wde", "wde"),
        delta(m_can, "btts", "btts"),
        delta(m_can, "ou25", "ou25"),
    ]
    write_csv(OUT / "metric_delta_vs_previous_audit.csv", deltas)

    cohort_cmp = [
        {"cohort": "all_valid", **{k: m_all.get(k) for k in ("n_rows", "n_unique_fixtures", "exact_top1", "exact_top5", "wde", "btts", "ou25")}},
        {"cohort": "canonical", **{k: m_can.get(k) for k in ("n_rows", "n_unique_fixtures", "exact_top1", "exact_top5", "wde", "btts", "ou25")}},
        {"cohort": "first", **{k: m_first.get(k) for k in ("n_rows", "n_unique_fixtures", "exact_top1", "exact_top5", "wde", "btts", "ou25")}},
        {"cohort": "last", **{k: m_last.get(k) for k in ("n_rows", "n_unique_fixtures", "exact_top1", "exact_top5", "wde", "btts", "ou25")}},
        {"cohort": "complete_metadata", **{k: m_meta.get(k) for k in ("n_rows", "n_unique_fixtures", "exact_top1", "exact_top5", "wde", "btts", "ou25")}},
    ]
    write_csv(OUT / "cohort_comparison.csv", cohort_cmp)

    # enrich first_vs_last with hits if file exists
    fvl_path = OUT / "first_vs_last_freeze_performance.csv"
    if fvl_path.exists() and first_rows and last_rows:
        first_by = {r["fixture_id"]: r for r in first_rows}
        last_by = {r["fixture_id"]: r for r in last_rows}
        enriched = []
        for r in csv.DictReader(fvl_path.open(encoding="utf-8")):
            fid = int(r["fixture_id"])
            a, b = first_by.get(fid), last_by.get(fid)
            if a and b:
                r["first_top5"] = a.get("exact_top5_hit")
                r["last_top5"] = b.get("exact_top5_hit")
                r["first_wde_hit"] = a.get("WDE_hit")
                r["last_wde_hit"] = b.get("WDE_hit")
            enriched.append(r)
        write_csv(fvl_path, enriched)

    write_text(
        OUT / "corrected_global_performance.md",
        "\n".join(
            [
                "# Corrected global performance",
                "",
                f"Run: `{RUN_ID}`",
                "",
                "## Canonical one-freeze-per-fixture (headline)",
                json.dumps(m_can, indent=2),
                "",
                "## Cohort comparison",
                json.dumps(cohort_cmp, indent=2, default=str),
                "",
                "## Delta vs previous audit (n=142 earliest-freeze methodology)",
                json.dumps(deltas, indent=2),
            ]
        ),
    )
    return corrected


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    prod = connect(settings.sqlite_path)
    ev = connect_eval_db(ROOT)
    print("OUT", OUT)
    print("Phase A…")
    a = phase_a(prod, ev)
    print("Phase A", a)
    print("Phase B…")
    b = phase_b(ev)
    print("Phase B", b)
    print("Phase C/D…")
    c = phase_c_d(ev)
    print(
        "Phase C/D canonical",
        c.get("canonical_one_per_fixture", {}).get("n_unique_fixtures"),
        c.get("canonical_one_per_fixture", {}).get("exact_top5"),
    )
    write_json(
        OUT / "phase_abcd_status.json",
        {"run_id": RUN_ID, "phase_a": a, "phase_b": b, "phase_cd_canonical": c.get("canonical_one_per_fixture")},
    )
    prod.close()
    ev.close()


if __name__ == "__main__":
    main()
