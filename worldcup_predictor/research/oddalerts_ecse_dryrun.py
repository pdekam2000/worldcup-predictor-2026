"""ECSE dry-run from OddAlerts CSV policy odds_snapshots (owner/internal)."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import SOURCE_DETAIL, SOURCE_PROVIDER
from worldcup_predictor.data_import.oddalerts_csv_promotion_write import GENERATED_FROM
from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

PHASE = "ECSE-ODDALERTS-1"
PROCESS_DATE = "2026-06-30"
REPORT_PATH = Path("ECSE_ODDALERTS_DRYRUN_REPORT.md")

ECSE_REQUIRED_PROB_KEYS = (
    "match_result_home",
    "match_result_draw",
    "match_result_away",
    "goals_over_2_5",
    "goals_under_2_5",
    "btts_yes",
    "btts_no",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _date_tag(process_date: str | None = None) -> str:
    return (process_date or PROCESS_DATE).replace("-", "")


def artifact_paths(process_date: str | None = None) -> dict[str, Path]:
    tag = _date_tag(process_date)
    return {
        "dryrun": Path(f"artifacts/oddalerts_csv_odds_snapshot_promotion_dryrun_{tag}.json"),
        "write": Path(f"artifacts/oddalerts_csv_promotion_write_{tag}.json"),
        "write_validation": Path(f"artifacts/oddalerts_csv_promotion_write_validation_{tag}.json"),
        "fixture_list": Path(f"artifacts/oddalerts_ecse_ready_fixture_list_{tag}.json"),
        "predictions_jsonl": Path(f"artifacts/ecse_oddalerts_dryrun_predictions_{tag}.jsonl"),
        "summary": Path(f"artifacts/ecse_oddalerts_dryrun_summary_{tag}.json"),
        "quality": Path(f"artifacts/ecse_oddalerts_dryrun_quality_{tag}.json"),
        "evaluation": Path(f"artifacts/ecse_oddalerts_dryrun_evaluation_preview_{tag}.json"),
        "validation_out": Path(f"artifacts/ecse_oddalerts_dryrun_validation_{tag}.json"),
    }


def _prob_pct_to_odds(pct: float | None) -> float | None:
    if pct is None:
        return None
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return None
    if p <= 0.5 or p > 99.5:
        return None
    return round(100.0 / p, 4)


def _markets_complete(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    probs = payload.get("normalized_probabilities") or {}
    markets = payload.get("markets") or {}
    missing: list[str] = []
    for key in ECSE_REQUIRED_PROB_KEYS:
        if probs.get(key) is None:
            missing.append(key)
    m1x2 = markets.get("1x2") or {}
    mou = markets.get("over_under_2_5") or {}
    mbtts = markets.get("btts") or {}
    if not all(m1x2.get(k) for k in ("home", "draw", "away")):
        missing.append("1x2_block")
    if not all(mou.get(k) for k in ("over", "under")):
        missing.append("ou25_block")
    if not all(mbtts.get(k) for k in ("yes", "no")):
        missing.append("btts_block")
    return len(missing) == 0, missing


def build_odds_row_from_oddalerts_payload(payload: dict[str, Any], *, fixture_id: int) -> dict[str, Any]:
    """Map OddAlerts probability snapshot to ECSE lambda extraction row shape."""
    probs = payload.get("normalized_probabilities") or {}
    markets = payload.get("markets") or {}
    m1x2 = markets.get("1x2") or {}
    mou = markets.get("over_under_2_5") or markets.get("over_under_2_5") or {}
    mbtts = markets.get("btts") or {}
    optional = markets.get("optional") or {}

    def p(key: str, *fallback_keys: str) -> float | None:
        if probs.get(key) is not None:
            return float(probs[key])
        for fk in fallback_keys:
            if fk in m1x2:
                return float(m1x2[fk]) if m1x2.get(fk) is not None else None
        return None

    row: dict[str, Any] = {
        "registry_fixture_id": int(fixture_id),
        "ft_home_closing": _prob_pct_to_odds(p("match_result_home", "home")),
        "ft_draw_closing": _prob_pct_to_odds(p("match_result_draw", "draw")),
        "ft_away_closing": _prob_pct_to_odds(p("match_result_away", "away")),
        "ou_over_25_closing": _prob_pct_to_odds(
            probs.get("goals_over_2_5") or mou.get("over")
        ),
        "ou_under_25_closing": _prob_pct_to_odds(
            probs.get("goals_under_2_5") or mou.get("under")
        ),
        "btts_yes_closing": _prob_pct_to_odds(probs.get("btts_yes") or mbtts.get("yes")),
        "btts_no_closing": _prob_pct_to_odds(probs.get("btts_no") or mbtts.get("no")),
    }

    for ou_line, over_key, under_key in (
        (1.5, "goals_over_1_5", "goals_under_1_5"),
        (3.5, "goals_over_3_5", "goals_under_3_5"),
    ):
        row[f"ou_over_{str(ou_line).replace('.', '')}_closing"] = _prob_pct_to_odds(
            optional.get(over_key) or probs.get(over_key)
        )
        row[f"ou_under_{str(ou_line).replace('.', '')}_closing"] = _prob_pct_to_odds(
            optional.get(under_key) or probs.get(under_key)
        )

    for side, prefix in (("home", "team_home"), ("away", "team_away")):
        for line, suffix in (("0_5", "05"), ("1_5", "15")):
            ok = f"{side}_goals_over_{line}"
            uk = f"{side}_goals_under_{line}"
            row[f"{prefix}_over_{suffix}_closing"] = _prob_pct_to_odds(
                optional.get(ok) or probs.get(ok)
            )
            row[f"{prefix}_under_{suffix}_closing"] = _prob_pct_to_odds(
                optional.get(uk) or probs.get(uk)
            )

    for dc_key, out_key in (
        ("double_chance_home_draw", "dc_home_draw_closing"),
        ("double_chance_home_away", "dc_home_away_closing"),
        ("double_chance_draw_away", "dc_draw_away_closing"),
    ):
        row[out_key] = _prob_pct_to_odds(optional.get(dc_key) or probs.get(dc_key))

    return row


def check_market_consistency(probs: dict[str, float]) -> dict[str, Any]:
    notes: list[str] = []
    warnings: list[str] = []

    x12 = [
        probs.get("match_result_home"),
        probs.get("match_result_draw"),
        probs.get("match_result_away"),
    ]
    if all(v is not None for v in x12):
        s = sum(float(v) for v in x12)
        notes.append(f"1x2_sum_pct={round(s, 2)}")
        if s < 85 or s > 115:
            warnings.append("1x2_sum_outside_band")

    ou = [probs.get("goals_over_2_5"), probs.get("goals_under_2_5")]
    if all(v is not None for v in ou):
        s = sum(float(v) for v in ou)
        notes.append(f"ou25_sum_pct={round(s, 2)}")
        if abs(s - 100) > 15:
            warnings.append("ou25_sum_anomaly")

    btts = [probs.get("btts_yes"), probs.get("btts_no")]
    if all(v is not None for v in btts):
        s = sum(float(v) for v in btts)
        notes.append(f"btts_sum_pct={round(s, 2)}")
        if abs(s - 100) > 15:
            warnings.append("btts_sum_anomaly")

    return {"notes": notes, "warnings": warnings}


def load_oddalerts_snapshot(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    max_rows: int = 5,
) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT id, fixture_id, snapshot_at, payload_json, competition_key
        FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(fixture_id), int(max_rows)),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if payload.get("source_provider") != SOURCE_PROVIDER:
            continue
        if payload.get("source_detail") != SOURCE_DETAIL:
            continue
        return {
            "odds_snapshot_id": int(row["id"]),
            "fixture_id": int(row["fixture_id"]),
            "snapshot_at": row["snapshot_at"],
            "competition_key": row["competition_key"],
            "payload": payload,
        }
    return None


def load_candidate_fixture_ids(
    *,
    dryrun_path: Path | None = None,
    write_path: Path | None = None,
    write_validation_path: Path | None = None,
) -> list[int]:
    paths = artifact_paths()
    dryrun_path = dryrun_path or paths["dryrun"]
    write_path = write_path or paths["write"]
    write_validation_path = write_validation_path or paths["write_validation"]

    if write_validation_path.exists():
        val = json.loads(write_validation_path.read_text(encoding="utf-8"))
        if val.get("failed", 1) == 0:
            pass  # validation passed — proceed

    ids: list[int] = []
    if write_path.exists():
        write = json.loads(write_path.read_text(encoding="utf-8"))
        if write.get("write_mode") and int(write.get("odds_snapshots_delta") or 0) > 0:
            for w in write.get("written_fixtures") or []:
                if w.get("fixture_id") is not None:
                    ids.append(int(w["fixture_id"]))
            for fid in write.get("written_fixture_ids") or []:
                ids.append(int(fid))

    if dryrun_path.exists():
        dryrun = json.loads(dryrun_path.read_text(encoding="utf-8"))
        for cand in dryrun.get("candidates") or []:
            if cand.get("ecse_readiness_status") != "READY_FULL":
                continue
            if cand.get("promotion_action") not in ("WOULD_INSERT", "WOULD_ENRICH"):
                continue
            fid = cand.get("fixture_id")
            if fid is not None:
                ids.append(int(fid))

    return sorted(set(ids))


def promotion_action_label(dryrun_candidates: dict[int, dict], fixture_id: int) -> str:
    cand = dryrun_candidates.get(fixture_id) or {}
    action = cand.get("promotion_action", "")
    if action == "WOULD_INSERT":
        return "inserted"
    if action == "WOULD_ENRICH":
        return "enriched"
    return str(action or "unknown")


def list_ecse_ready_fixtures(
    conn: sqlite3.Connection,
    fixture_ids: list[int],
    *,
    dryrun_candidates: dict[int, dict] | None = None,
) -> dict[str, Any]:
    dryrun_candidates = dryrun_candidates or {}
    fixtures: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for fid in fixture_ids:
        fx = conn.execute(
            """
            SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key, status
            FROM fixtures WHERE fixture_id = ?
            """,
            (int(fid),),
        ).fetchone()
        snap = load_oddalerts_snapshot(conn, fid)
        if not snap:
            skipped.append({"fixture_id": fid, "reason": "ODDALERTS_SNAPSHOT_NOT_FOUND"})
            continue

        payload = snap["payload"]
        complete, missing = _markets_complete(payload)
        if not complete:
            skipped.append({"fixture_id": fid, "reason": "INCOMPLETE_MARKETS", "missing": missing})
            continue

        meta = payload.get("metadata") or {}
        markets_present = sorted((payload.get("normalized_probabilities") or {}).keys())
        fixtures.append(
            {
                "fixture_id": fid,
                "home_team": fx["home_team"] if fx else None,
                "away_team": fx["away_team"] if fx else None,
                "competition": fx["competition_key"] if fx else snap.get("competition_key"),
                "kickoff_utc": fx["kickoff_utc"] if fx else None,
                "odds_snapshot_id": snap["odds_snapshot_id"],
                "snapshot_at": snap["snapshot_at"],
                "source_provider": payload.get("source_provider"),
                "source_detail": payload.get("source_detail"),
                "markets_present": markets_present,
                "ecse_core_markets": list(ECSE_REQUIRED_PROB_KEYS),
                "crosswalk_confidence": meta.get("crosswalk_confidence", "MATCHED_HIGH_CONFIDENCE"),
                "promotion_action": promotion_action_label(dryrun_candidates, fid),
                "policy_version": payload.get("policy_version"),
                "generated_from": payload.get("generated_from") or meta.get("generated_from"),
            }
        )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "fixture_count": len(fixtures),
        "skipped_count": len(skipped),
        "fixtures": fixtures,
        "skipped": skipped,
    }


def generate_ecse_dryrun_prediction(
    conn: sqlite3.Connection,
    fixture_entry: dict[str, Any],
) -> dict[str, Any]:
    fid = int(fixture_entry["fixture_id"])
    snap = load_oddalerts_snapshot(conn, fid)
    if not snap:
        return {"fixture_id": fid, "status": "failed", "reason": "snapshot_not_found"}

    payload = snap["payload"]
    complete, missing = _markets_complete(payload)
    if not complete:
        return {"fixture_id": fid, "status": "failed", "reason": "incomplete_markets", "missing": missing}

    probs = {k: float(v) for k, v in (payload.get("normalized_probabilities") or {}).items()}
    consistency = check_market_consistency(probs)
    odds_row = build_odds_row_from_oddalerts_payload(payload, fixture_id=fid)
    feat = extract_lambdas(odds_row)
    if not feat:
        return {
            "fixture_id": fid,
            "status": "failed",
            "reason": "lambda_extraction_failed",
            "input_probabilities": probs,
        }

    lh = float(feat["lambda_home"])
    la = float(feat["lambda_away"])
    if lh <= 0 or la <= 0 or lh > 6 or la > 6:
        return {
            "fixture_id": fid,
            "status": "failed",
            "reason": "invalid_lambda",
            "lambda_home": lh,
            "lambda_away": la,
        }

    dist = generate_score_distribution(lh, la)
    if not dist:
        return {"fixture_id": fid, "status": "failed", "reason": "score_distribution_empty"}

    top_10 = [
        {
            "scoreline": e["scoreline"],
            "probability": round(float(e["probability"]), 6),
            "rank": int(e["rank"]),
            "home_goals": int(e["home_goals"]),
            "away_goals": int(e["away_goals"]),
        }
        for e in dist[:10]
    ]
    top_1_prob = top_10[0]["probability"]
    tier = "high" if top_1_prob >= 0.14 else "medium" if top_1_prob >= 0.10 else "low"

    warnings = list(consistency.get("warnings") or [])
    if feat.get("missing_draw_flag"):
        warnings.append("missing_draw_flag")
    if float(feat.get("data_quality_score") or 0) < 0.5:
        warnings.append("low_data_quality")

    meta = payload.get("metadata") or {}
    return {
        "fixture_id": fid,
        "status": "generated",
        "home_team": fixture_entry.get("home_team"),
        "away_team": fixture_entry.get("away_team"),
        "competition": fixture_entry.get("competition"),
        "kickoff_utc": fixture_entry.get("kickoff_utc"),
        "odds_snapshot_id": snap["odds_snapshot_id"],
        "snapshot_at": snap["snapshot_at"],
        "source_provider": payload.get("source_provider"),
        "source_detail": payload.get("source_detail"),
        "promotion_action": fixture_entry.get("promotion_action"),
        "top_10_exact_scores": top_10,
        "top_1_score": top_10[0]["scoreline"],
        "top_3_scores": [e["scoreline"] for e in top_10[:3]],
        "top_5_scores": [e["scoreline"] for e in top_10[:5]],
        "lambda_home": round(lh, 6),
        "lambda_away": round(la, 6),
        "confidence_score": round(top_1_prob, 6),
        "confidence_tier": tier,
        "data_quality_score": feat.get("data_quality_score"),
        "warning_flags": warnings,
        "input_market_probabilities": probs,
        "normalization_notes": consistency.get("notes"),
        "crosswalk_confidence": meta.get("crosswalk_confidence"),
        "policy_version": payload.get("policy_version"),
        "source_row_hash_count": len(meta.get("source_row_hashes") or []),
        "generated_from_snapshot": fixture_entry.get("promotion_action"),
    }


def run_ecse_dryrun_batch(
    conn: sqlite3.Connection,
    fixture_list: dict[str, Any],
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    fixtures = fixture_list.get("fixtures") or []
    if limit is not None:
        fixtures = fixtures[:limit]

    predictions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for entry in fixtures:
        pred = generate_ecse_dryrun_prediction(conn, entry)
        if pred.get("status") == "generated":
            predictions.append(pred)
        else:
            failures.append(pred)

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "candidate_count": len(fixtures),
        "generated_count": len(predictions),
        "failed_count": len(failures),
        "predictions": predictions,
        "failures": failures,
    }


def build_quality_report(batch: dict[str, Any]) -> dict[str, Any]:
    preds = batch.get("predictions") or []
    failures = batch.get("failures") or []
    top1_counter: Counter[str] = Counter()
    lambda_home: list[float] = []
    lambda_away: list[float] = []
    impossible: list[dict] = []
    anomalies: list[dict] = []
    missing_meta: list[int] = []
    dup_fixtures: list[int] = []
    seen: set[int] = set()

    for p in preds:
        fid = int(p["fixture_id"])
        if fid in seen:
            dup_fixtures.append(fid)
        seen.add(fid)
        top1_counter[p.get("top_1_score", "?")] += 1
        lh, la = float(p.get("lambda_home", 0)), float(p.get("lambda_away", 0))
        lambda_home.append(lh)
        lambda_away.append(la)
        if lh <= 0 or la <= 0 or math.isnan(lh) or math.isnan(la):
            impossible.append({"fixture_id": fid, "reason": "non_positive_lambda"})
        if p.get("warning_flags"):
            anomalies.append({"fixture_id": fid, "warnings": p["warning_flags"]})
        if not p.get("source_provider") or not p.get("odds_snapshot_id"):
            missing_meta.append(fid)

    failure_reasons = Counter(f.get("reason", "unknown") for f in failures)

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "generated_count": len(preds),
        "failed_count": len(failures),
        "failure_reasons": dict(failure_reasons),
        "top1_score_distribution": dict(top1_counter.most_common(20)),
        "lambda_home_range": [round(min(lambda_home), 4), round(max(lambda_home), 4)] if lambda_home else None,
        "lambda_away_range": [round(min(lambda_away), 4), round(max(lambda_away), 4)] if lambda_away else None,
        "lambda_home_mean": round(sum(lambda_home) / len(lambda_home), 4) if lambda_home else None,
        "lambda_away_mean": round(sum(lambda_away) / len(lambda_away), 4) if lambda_away else None,
        "impossible_outputs": impossible,
        "anomaly_flags": anomalies[:50],
        "missing_metadata_fixture_ids": missing_meta,
        "duplicate_fixture_outputs": dup_fixtures,
        "market_consistency_warnings": sum(1 for p in preds if p.get("warning_flags")),
        "source_traceability_ok": len(missing_meta) == 0,
    }


def build_evaluation_preview(conn: sqlite3.Connection, predictions: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated: list[dict[str, Any]] = []
    for p in predictions:
        fid = int(p["fixture_id"])
        fx = conn.execute(
            """
            SELECT f.status, r.home_goals, r.away_goals
            FROM fixtures f
            LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
            WHERE f.fixture_id = ?
            """,
            (fid,),
        ).fetchone()
        if not fx or fx["home_goals"] is None or fx["away_goals"] is None:
            continue
        if str(fx["status"] or "").upper() not in ("FT", "AET", "PEN", "FINISHED"):
            continue

        actual = f"{int(fx['home_goals'])}-{int(fx['away_goals'])}"
        top3 = p.get("top_3_scores") or []
        top5 = p.get("top_5_scores") or []
        evaluated.append(
            {
                "fixture_id": fid,
                "actual_score": actual,
                "top_1_hit": p.get("top_1_score") == actual,
                "top_3_hit": actual in top3,
                "top_5_hit": actual in top5,
                "top_1_score": p.get("top_1_score"),
            }
        )

    if not evaluated:
        return {
            "phase": PHASE,
            "status": "WAITING_FOR_RESULTS",
            "evaluated_count": 0,
            "note": "No finished fixtures with results among candidates.",
        }

    n = len(evaluated)
    return {
        "phase": PHASE,
        "status": "PREVIEW",
        "evaluated_count": n,
        "top1_hit_rate": round(sum(1 for e in evaluated if e["top_1_hit"]) / n, 4),
        "top3_hit_rate": round(sum(1 for e in evaluated if e["top_3_hit"]) / n, 4),
        "top5_hit_rate": round(sum(1 for e in evaluated if e["top_5_hit"]) / n, 4),
        "samples": evaluated[:30],
    }


def dryrun_final_recommendation(
    *,
    batch: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> str:
    generated = int(batch.get("generated_count") or 0)
    candidates = int(batch.get("candidate_count") or 0)
    failed = int(batch.get("failed_count") or 0)

    if generated == 0:
        return "NEED_ODDS_INPUT_FIX"

    if failed > candidates * 0.2:
        return "NEED_ECSE_MAPPING_FIX"

    if quality.get("impossible_outputs") or quality.get("duplicate_fixture_outputs"):
        return "NEED_ECSE_MAPPING_FIX"

    if not quality.get("source_traceability_ok", True):
        return "NEED_ODDS_INPUT_FIX"

    if generated >= candidates * 0.95 and failed == 0:
        return "ECSE_ODDALERTS_DRYRUN_READY"

    if generated >= candidates * 0.8:
        return "READY_FOR_ECSE_SHADOW_WRITE"

    if evaluation.get("status") == "WAITING_FOR_RESULTS" and generated > 0:
        return "ECSE_ODDALERTS_DRYRUN_READY"

    return "DO_NOT_WRITE_ECSE"


def build_report_markdown(
    *,
    fixture_list: dict[str, Any],
    batch: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
    validation: dict[str, Any] | None,
    recommendation: str,
) -> str:
    validation = validation or {}
    preds = batch.get("predictions") or []
    sample_lines = []
    for p in preds[:8]:
        sample_lines.append(
            f"| {p.get('fixture_id')} | {p.get('home_team', '')[:18]} vs {p.get('away_team', '')[:18]} | "
            f"{p.get('top_1_score')} | {p.get('lambda_home')}/{p.get('lambda_away')} | {p.get('promotion_action')} |"
        )

    val_lines = [f"- [{'pass' if c.get('passed') else 'FAIL'}] {c.get('check')}" for c in (validation.get("checks") or [])]

    return f"""# ECSE OddAlerts Dry-Run Report

**Phase:** {PHASE}  
**Generated:** {_utc_now()}  
**Mode:** Owner/internal ECSE dry-run — no production ECSE writes, no public publish

---

## Summary

**Final recommendation:** `{recommendation}`

| Metric | Value |
|--------|-------|
| Candidates | {fixture_list.get('fixture_count', 0)} |
| Generated | {batch.get('generated_count', 0)} |
| Failed | {batch.get('failed_count', 0)} |

---

## Top-1 score distribution

{json.dumps(quality.get('top1_score_distribution', {}), indent=2)}

---

## Lambda ranges

- Home: {quality.get('lambda_home_range')} (mean {quality.get('lambda_home_mean')})
- Away: {quality.get('lambda_away_range')} (mean {quality.get('lambda_away_mean')})

---

## Sample predictions

| Fixture | Match | Top-1 | λ h/a | Source |
|---------|-------|-------|-------|--------|
{chr(10).join(sample_lines) if sample_lines else '| — | — | — | — | — |'}

---

## Evaluation preview

Status: **{evaluation.get('status', 'n/a')}**  
Evaluated: {evaluation.get('evaluated_count', 0)}

---

## Validation

{chr(10).join(val_lines) if val_lines else '- pending'}

Passed: **{validation.get('passed', '?')}** / **{(validation.get('passed') or 0) + (validation.get('failed') or 0)}**
"""
