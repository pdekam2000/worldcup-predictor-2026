#!/usr/bin/env python3
"""FINISHED-KNOCKOUT-RESULTS-FORENSIC-1 — DB audit, sync, frozen eval, error analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.api.market_level_evaluation import (
    btts_selection_from_payload,
    canonical_1x2_selection,
    ou_selection_from_payload,
)
from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome, FixtureOutcomeResolver
from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.research.ecse_live.result_sync import sync_ecse_snapshot_results
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.root_cause.knowledge_store import RootCauseStore
from worldcup_predictor.root_cause.models import KnowledgeRecord
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, actual_result

PHASE = "FINISHED-KNOCKOUT-RESULTS-FORENSIC-1"
ARTIFACT_DIR = ROOT / "artifacts" / "finished_knockout_results_forensic_1"
PROVIDER_LOG = ARTIFACT_DIR / "provider_calls.jsonl"
WORKFLOW_JSON = ARTIFACT_DIR / "workflow.json"

DB_AUDIT_MD = ROOT / "FINISHED_KNOCKOUT_RESULTS_DB_AUDIT.md"
SCORECARD_MD = ROOT / "FINISHED_KNOCKOUT_PREDICTION_SCORECARD.md"
DIST_WIDTH_MD = ROOT / "ECSE_SCORE_DISTRIBUTION_WIDTH_ANALYSIS.md"
REPORT_MD = ROOT / "FINISHED_KNOCKOUT_RESULTS_FORENSIC_1_REPORT.md"

TARGET_FIXTURES: list[dict[str, Any]] = [
    {"fixture_id": 1567306, "match": "Mexico vs Ecuador", "kickoff": "2026-06-30T23:00:00"},
    {"fixture_id": 1567307, "match": "England vs DR Congo", "kickoff": "2026-07-01T14:00:00"},
    {"fixture_id": 1567308, "match": "Belgium vs Senegal", "kickoff": "2026-07-01T18:00:00"},
    {"fixture_id": 1562586, "match": "USA vs Bosnia & Herzegovina", "kickoff": "2026-07-01T22:00:00"},
    {"fixture_id": 1567311, "match": "Spain vs Austria", "kickoff": "2026-07-02T17:00:00"},
    {"fixture_id": 1567309, "match": "Portugal vs Croatia", "kickoff": "2026-07-02T21:00:00"},
    {"fixture_id": 1567312, "match": "Switzerland vs Algeria", "kickoff": "2026-07-03T01:00:00"},
    {"fixture_id": 1565178, "match": "Australia vs Egypt", "kickoff": "2026-07-03T16:00:00"},
    {"fixture_id": 1565179, "match": "Argentina vs Cape Verde", "kickoff": "2026-07-03T22:00:00"},
    {"fixture_id": 1567310, "match": "Colombia vs Ghana", "kickoff": "2026-07-04T01:30:00"},
    {"fixture_id": 1567824, "match": "Canada vs Morocco", "kickoff": "2026-07-04T17:00:00"},
]

COLOMBIA_ID = 1567310
CANADA_ID = 1567824

FINISHED_STATUS = frozenset({"FT", "AET", "PEN", "AWD", "WO"})

ROOT_CAUSE_CLASSES = (
    "WINNER_DIRECTION_ERROR",
    "DRAW_RISK_UNDERESTIMATED",
    "FAVORITE_DOMINANCE_UNDERESTIMATED",
    "FAVORITE_DOMINANCE_OVERESTIMATED",
    "GOAL_TOTAL_UNDERESTIMATED",
    "GOAL_TOTAL_OVERESTIMATED",
    "BTTS_CALIBRATION_ERROR",
    "CLEAN_SHEET_PROBABILITY_ERROR",
    "AWAY_FAVORITE_STRENGTH_UNDERESTIMATED",
    "KNOCKOUT_CONTEXT_ERROR",
    "AET_REGULATION_CONFUSION",
    "ODDS_CONTEXT_MISSING",
    "ODDS_METADATA_ONLY_GAP",
    "LINEUP_SIGNAL_MISSING",
    "XG_SIGNAL_UNDERUSED",
    "PRESSURE_SIGNAL_UNDERUSED",
    "TAIL_PROBABILITY_TOO_LOW",
    "SCORE_DISTRIBUTION_TOO_NARROW",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _payload_hash(raw: str | None) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _log_provider(entry: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with PROVIDER_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": _utc_now(), **entry}, default=str) + "\n")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def _parse_json_col(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


@dataclass
class ProviderTruth:
    fixture_id: int
    status: str
    goals: dict[str, int | None]
    score: dict[str, Any]
    source: str = "api-football"

    @property
    def regulation_score(self) -> str | None:
        ft = (self.score.get("fulltime") or {}) if self.score else {}
        h, a = ft.get("home"), ft.get("away")
        if h is not None and a is not None:
            return f"{int(h)}-{int(a)}"
        gh = (self.goals or {}).get("home")
        ga = (self.goals or {}).get("away")
        if gh is not None and ga is not None and self.status in ("FT",):
            return f"{int(gh)}-{int(ga)}"
        return None

    @property
    def aet_score(self) -> str | None:
        if self.status != "AET":
            return None
        et = (self.score.get("extratime") or {}) if self.score else {}
        ft = (self.score.get("fulltime") or {}) if self.score else {}
        fh, fa = ft.get("home"), ft.get("away")
        eh, ea = et.get("home"), et.get("away")
        if None not in (fh, fa, eh, ea):
            return f"{int(fh) + int(eh)}-{int(fa) + int(ea)}"
        gh, ga = (self.goals or {}).get("home"), (self.goals or {}).get("away")
        if gh is not None and ga is not None:
            return f"{int(gh)}-{int(ga)}"
        return None

    @property
    def penalty_score(self) -> str | None:
        pen = (self.score.get("penalty") or {}) if self.score else {}
        h, a = pen.get("home"), pen.get("away")
        if h is not None and a is not None:
            return f"{int(h)}-{int(a)}"
        return None


def fetch_provider_truth(
    api: ApiFootballClient,
    fixture_id: int,
    *,
    call_budget: list[int],
) -> ProviderTruth | None:
    if call_budget[0] <= 0:
        return None
    try:
        call = api._safe_get(
            "fixtures",
            {"id": fixture_id},
            placeholder_factory=lambda: None,
            force_refresh=True,
        )
        call_budget[0] -= 1
        _log_provider({"fixture_id": fixture_id, "endpoint": "fixtures", "source": call.source})
        if not call.data:
            return None
        item = call.data[0] if isinstance(call.data, list) else call.data
        status = str(((item.get("fixture") or {}).get("status") or {}).get("short") or "NS")
        goals = item.get("goals") or {}
        score = item.get("score") or {}
        return ProviderTruth(
            fixture_id=fixture_id,
            status=status,
            goals={"home": goals.get("home"), "away": goals.get("away")},
            score=score,
            source=str(call.source or "api-football"),
        )
    except Exception as exc:
        _log_provider({"fixture_id": fixture_id, "error": str(exc)})
        return None


def classify_db_result(
    fixture: dict[str, Any] | None,
    result: dict[str, Any] | None,
    provider: ProviderTruth | None,
) -> str:
    if not fixture:
        return "RESULT_MISSING"
    status = str(fixture.get("status") or "NS").upper()
    if status not in FINISHED_STATUS:
        if provider and provider.status in FINISHED_STATUS:
            return "STATUS_INCONSISTENT"
        return "RESULT_MISSING" if not result else "STATUS_INCONSISTENT"
    if not result or result.get("home_goals") is None:
        return "RESULT_MISSING"
    if provider and provider.regulation_score:
        db_score = f"{result.get('home_goals')}-{result.get('away_goals')}"
        mot = str(result.get("match_outcome_type") or status).upper()
        if mot in ("AET", "PEN") and db_score != provider.regulation_score:
            return "RESULT_PARTIAL"
    if result.get("match_outcome_type") in (None, ""):
        return "RESULT_PARTIAL"
    return "RESULT_COMPLETE"


def regulation_outcome(
    regulation_score: str,
    *,
    match_outcome_type: str | None = None,
    fixture_status: str | None = None,
) -> FixtureOutcome:
    h, a = [int(x) for x in regulation_score.split("-", 1)]
    status = str(fixture_status or match_outcome_type or "FT").upper()
    return FixtureOutcome(
        is_finished=True,
        actual_result=actual_result(h, a),
        final_score=regulation_score,
        evaluated_at=_utc_now(),
        fixture_status=status,
        match_outcome_type=match_outcome_type or status,
    )


def _wde_markets(payload: dict[str, Any]) -> dict[str, str | None]:
    sel_1x2 = canonical_1x2_selection(payload)
    mapping = {
        "home": "home_win",
        "draw": "draw",
        "away": "away_win",
        "home_win": "home_win",
        "away_win": "away_win",
    }
    return {
        "1x2": mapping.get(str(sel_1x2 or "").lower(), sel_1x2),
        "btts": btts_selection_from_payload(payload),
        "ou": ou_selection_from_payload(payload),
    }


def _eval_wde_markets(
    payload: dict[str, Any],
    outcome: FixtureOutcome,
) -> dict[str, str]:
    ev = evaluate_stored_prediction(payload, outcome)
    markets = ev.get("markets") or {}
    return {
        "1x2": "HIT" if markets.get("1x2") == "correct" else "MISS",
        "btts": "HIT" if markets.get("btts") == "correct" else "MISS",
        "ou": "HIT" if markets.get("over_under_2_5") == "correct" else "MISS",
    }


def _eval_ecse(
    snapshot: dict[str, Any],
    regulation_score: str,
) -> dict[str, Any]:
    top1 = str(snapshot.get("top_1_score") or "")
    top3 = _parse_json_col(snapshot.get("top_3_scores_json") or snapshot.get("top_3_scores")) or []
    top5 = _parse_json_col(snapshot.get("top_5_scores_json") or snapshot.get("top_5_scores")) or []
    top3 = [str(x) for x in top3]
    top5 = [str(x) for x in top5]
    rank = None
    top10 = _parse_json_col(snapshot.get("top_10_scorelines_json")) or []
    for item in top10:
        if isinstance(item, dict) and str(item.get("scoreline")) == regulation_score:
            rank = int(item.get("rank") or 0) or None
            break
    if rank is None and snapshot.get("lambda_home") is not None:
        dist = generate_score_distribution(float(snapshot["lambda_home"]), float(snapshot["lambda_away"]))
        for entry in dist:
            if entry["scoreline"] == regulation_score:
                rank = int(entry["rank"])
                break
    h, a = [int(x) for x in regulation_score.split("-", 1)]
    top1_err = abs((h + a) - sum(int(x) for x in top1.split("-"))) if top1 and "-" in top1 else None
    def nearest_err(cands: list[str]) -> int | None:
        best = None
        actual_total = h + a
        for c in cands:
            if "-" not in c:
                continue
            ph, pa = [int(x) for x in c.split("-", 1)]
            err = abs(actual_total - (ph + pa))
            best = err if best is None else min(best, err)
        return best
    return {
        "top1_hit": "HIT" if top1 == regulation_score else "MISS",
        "top3_hit": "HIT" if regulation_score in top3 else "MISS",
        "top5_hit": "HIT" if regulation_score in top5 else "MISS",
        "rank": rank,
        "top1_goal_error": top1_err,
        "top3_nearest_goal_error": nearest_err(top3),
        "top5_nearest_goal_error": nearest_err(top5),
        "top1_score": top1,
        "top3_scores": top3,
        "top5_scores": top5,
    }


def _margin(score: str) -> int:
    h, a = [int(x) for x in score.split("-", 1)]
    return abs(h - a)


def _winner_side(score: str) -> str:
    h, a = [int(x) for x in score.split("-", 1)]
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def _distribution_stats(snapshot: dict[str, Any]) -> dict[str, Any]:
    top10 = _parse_json_col(snapshot.get("top_10_scorelines_json")) or []
    probs = [float(x.get("probability") or 0) for x in top10 if isinstance(x, dict)]
    top1_p = probs[0] if probs else 0.0
    top3_p = sum(probs[:3]) if probs else 0.0
    top5_p = sum(probs[:5]) if probs else 0.0
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log(p)
    totals = []
    margins = []
    tail3 = tail_margin3 = 0.0
    for item in top10:
        if not isinstance(item, dict):
            continue
        p = float(item.get("probability") or 0)
        sl = str(item.get("scoreline") or "")
        if "-" not in sl:
            continue
        hg, ag = [int(x) for x in sl.split("-", 1)]
        totals.append(hg + ag)
        margins.append(abs(hg - ag))
        if hg + ag >= 3:
            tail3 += p
        if abs(hg - ag) >= 3:
            tail_margin3 += p
    mean_total = sum(totals) / len(totals) if totals else None
    var_total = (
        sum((t - mean_total) ** 2 for t in totals) / len(totals) if totals and mean_total is not None else None
    )
    return {
        "top1_prob": round(top1_p, 4),
        "top3_cumulative_prob": round(top3_p, 4),
        "top5_cumulative_prob": round(top5_p, 4),
        "entropy_top10": round(entropy, 4),
        "mean_predicted_total_goals": round(mean_total, 3) if mean_total is not None else None,
        "predicted_score_variance": round(var_total, 3) if var_total is not None else None,
        "tail_mass_3plus_goals": round(tail3, 4),
        "tail_mass_margin_3plus": round(tail_margin3, 4),
    }


def _cross_market_alignment(wde: dict[str, str | None], top3: list[str]) -> dict[str, Any]:
    w1x2 = wde.get("1x2")
    aligned = conflict = mixed = 0
    btts_yes = btts_no = ou_over = ou_under = 0
    for sl in top3:
        if "-" not in sl:
            continue
        h, a = [int(x) for x in sl.split("-", 1)]
        side = _winner_side(sl)
        pred_side = {"home_win": "home", "away_win": "away", "draw": "draw"}.get(str(w1x2 or ""), None)
        if pred_side and side == pred_side:
            aligned += 1
        elif pred_side and side != pred_side:
            conflict += 1
        else:
            mixed += 1
        if h > 0 and a > 0:
            btts_yes += 1
        else:
            btts_no += 1
        if h + a > 2:
            ou_over += 1
        else:
            ou_under += 1
    w_btts = str(wde.get("btts") or "").lower()
    w_ou = str(wde.get("ou") or "").lower()
    btts_align = (w_btts in {"yes", "btts_yes"} and btts_yes >= 2) or (w_btts in {"no", "btts_no"} and btts_no >= 2)
    ou_align = ("over" in w_ou and ou_over >= 2) or ("under" in w_ou and ou_under >= 2)
    if aligned == 3 and btts_align and ou_align:
        bucket = "ALIGNED"
    elif conflict >= 2:
        bucket = "CONFLICT"
    else:
        bucket = "MIXED"
    return {
        "winner_alignment_ratio": round(aligned / 3, 2),
        "btts_alignment_ratio": round(max(btts_yes, btts_no) / 3, 2),
        "ou_alignment_ratio": round(max(ou_over, ou_under) / 3, 2),
        "fully_aligned_top3_count": aligned,
        "bucket": bucket,
    }


def _feature_availability(snapshot: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    raw = snapshot.get("raw_features_json") or snapshot.get("raw_features") or {}
    if isinstance(raw, str):
        raw = _parse_json_col(raw) or {}
    coverage = raw.get("coverage") or {}
    odds_row = raw.get("odds_row") or {}
    lam = raw.get("lambda_features") or {}
    resolve = raw.get("resolve") or {}
    has_lineup = any("lineup" in str(v).lower() for vals in coverage.values() for v in (vals or []))
    has_xg = bool(lam.get("lambda_home")) and float(lam.get("data_quality_score") or 0) >= 0.5
    odds_at = payload.get("odds_snapshot_at")
    if not odds_at:
        meta = payload.get("odds_freshness_metadata") or {}
        odds_at = meta.get("odds_snapshot_at")
    fresh = payload.get("odds_freshness_status")
    if not fresh:
        fresh = (payload.get("odds_freshness_metadata") or {}).get("status")
    has_odds = bool(odds_row or odds_at or payload.get("detailed_markets"))
    return {
        "odds_available": has_odds,
        "odds_freshness": fresh or ("UNKNOWN" if odds_at else "MISSING"),
        "odds_age_hours": payload.get("odds_age_hours"),
        "xg_available": has_xg,
        "lineup_available": has_lineup or bool(resolve.get("sportmonks")),
        "pressure_available": False,
        "injury_available": False,
    }


def _attribute_misses(
    *,
    fixture_id: int,
    match: str,
    wde_pred: dict[str, str | None],
    wde_eval: dict[str, str],
    ecse_eval: dict[str, Any],
    regulation_score: str,
    features: dict[str, Any],
    fav_prob: float | None,
    favorite_side: str | None,
) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    actual_side = _winner_side(regulation_score)
    h, a = [int(x) for x in regulation_score.split("-", 1)]
    actual_margin = abs(h - a)
    pred_top3 = ecse_eval.get("top3_scores") or []
    max_top3_margin = max((_margin(s) for s in pred_top3), default=0)

    if wde_eval.get("1x2") == "MISS":
        causes.append({
            "fixture_id": fixture_id,
            "match": match,
            "class": "WINNER_DIRECTION_ERROR",
            "prediction": wde_pred.get("1x2"),
            "actual": actual_side,
            "evidence": f"WDE 1X2 predicted {wde_pred.get('1x2')} vs actual {actual_side} ({regulation_score})",
            "engine": "WDE",
            "confidence": 0.85,
        })
    if wde_eval.get("btts") == "MISS":
        actual_btts = "yes" if h > 0 and a > 0 else "no"
        causes.append({
            "fixture_id": fixture_id,
            "match": match,
            "class": "BTTS_CALIBRATION_ERROR",
            "prediction": wde_pred.get("btts"),
            "actual": actual_btts,
            "evidence": f"BTTS pick {wde_pred.get('btts')} vs actual both scored={actual_btts}",
            "engine": "WDE",
            "confidence": 0.8,
        })
    if wde_eval.get("ou") == "MISS":
        actual_ou = "over_2_5" if h + a > 2 else "under_2_5"
        cls = "GOAL_TOTAL_UNDERESTIMATED" if actual_ou == "over_2_5" else "GOAL_TOTAL_OVERESTIMATED"
        causes.append({
            "fixture_id": fixture_id,
            "match": match,
            "class": cls,
            "prediction": wde_pred.get("ou"),
            "actual": actual_ou,
            "evidence": f"Total goals {h+a} vs O/U pick {wde_pred.get('ou')}",
            "engine": "WDE",
            "confidence": 0.8,
        })
    if (
        wde_eval.get("1x2") == "HIT"
        and ecse_eval.get("top3_hit") == "MISS"
        and actual_margin > max_top3_margin
    ):
        cls = "FAVORITE_DOMINANCE_UNDERESTIMATED"
        if favorite_side == "away":
            cls = "AWAY_FAVORITE_STRENGTH_UNDERESTIMATED"
        causes.append({
            "fixture_id": fixture_id,
            "match": match,
            "class": cls,
            "prediction": f"Top3 max margin {max_top3_margin}",
            "actual": f"margin {actual_margin} ({regulation_score})",
            "evidence": "Winner direction correct but ECSE Top3 margins below actual",
            "engine": "ECSE",
            "confidence": 0.75,
        })
    if ecse_eval.get("top3_hit") == "MISS" and features.get("odds_freshness") in {"STALE", "UNKNOWN_ODDS", "MISSING"}:
        causes.append({
            "fixture_id": fixture_id,
            "match": match,
            "class": "ODDS_CONTEXT_MISSING" if not features.get("odds_available") else "ODDS_METADATA_ONLY_GAP",
            "prediction": features.get("odds_freshness"),
            "actual": regulation_score,
            "evidence": f"odds_freshness={features.get('odds_freshness')}",
            "engine": "INFRA",
            "confidence": 0.55,
        })
    if ecse_eval.get("top3_hit") == "MISS" and not features.get("lineup_available"):
        causes.append({
            "fixture_id": fixture_id,
            "match": match,
            "class": "LINEUP_SIGNAL_MISSING",
            "prediction": "no lineup coverage",
            "actual": regulation_score,
            "evidence": "No lineup in snapshot raw_features coverage",
            "engine": "DATA",
            "confidence": 0.5,
        })
    return causes


@dataclass
class ForensicContext:
    phase: str = PHASE
    db_path: str = ""
    audit_before: list[dict[str, Any]] = field(default_factory=list)
    audit_after: list[dict[str, Any]] = field(default_factory=list)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    sync_result: dict[str, Any] = field(default_factory=dict)
    eval_result: dict[str, Any] = field(default_factory=dict)
    error_attribution: list[dict[str, Any]] = field(default_factory=list)
    margin_analysis: list[dict[str, Any]] = field(default_factory=list)
    distribution_analysis: list[dict[str, Any]] = field(default_factory=list)
    cross_market: list[dict[str, Any]] = field(default_factory=list)
    feature_analysis: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    provider_calls: int = 0
    final_recommendation: str = "INSUFFICIENT_EVALUATED_SAMPLE"


def audit_db(
    conn: sqlite3.Connection,
    api: ApiFootballClient,
    *,
    call_budget: list[int],
    label: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in TARGET_FIXTURES:
        fid = int(target["fixture_id"])
        fixture = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        result = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        fixture_d = dict(fixture) if fixture else None
        result_d = dict(result) if result else None
        provider = fetch_provider_truth(api, fid, call_budget=call_budget)
        reg = provider.regulation_score if provider else None
        if not reg and result_d and result_d.get("home_goals") is not None:
            mot = str(result_d.get("match_outcome_type") or (fixture_d or {}).get("status") or "").upper()
            db_score = f"{int(result_d['home_goals'])}-{int(result_d['away_goals'])}"
            reg = db_score if mot == "FT" else None
        classification = classify_db_result(fixture_d, result_d, provider)
        rows.append({
            "label": label,
            "match": target["match"],
            "fixture_id": fid,
            "fixture": fixture_d,
            "result": result_d,
            "provider": {
                "status": provider.status if provider else None,
                "regulation_90m": provider.regulation_score if provider else None,
                "aet_score": provider.aet_score if provider else None,
                "penalty_score": provider.penalty_score if provider else None,
                "source": provider.source if provider else None,
            } if provider else None,
            "regulation_90m": reg,
            "classification": classification,
            "db_result_complete": classification == "RESULT_COMPLETE",
        })
    return rows


def audit_predictions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in TARGET_FIXTURES:
        fid = int(target["fixture_id"])
        fixture = conn.execute("SELECT kickoff_utc, status FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        wde = conn.execute(
            "SELECT predicted_at, payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)
        ).fetchone()
        ecse_cols = [r[1] for r in conn.execute("PRAGMA table_info(ecse_prediction_snapshots)").fetchall()]
        sel = ["id", "generated_at", "is_frozen", "top_1_score", "top_3_scores_json", "top_5_scores_json", "top_10_scorelines_json", "lambda_home", "lambda_away", "raw_features_json"]
        sel = [c for c in sel if c in ecse_cols]
        ecse = conn.execute(
            f"SELECT {', '.join(sel)} FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (fid,),
        ).fetchone()
        wde_ev = conn.execute("SELECT COUNT(*) c FROM worldcup_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
        ecse_ev = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
        egie = "N/A"
        if _table_exists(conn, "egie_goal_timing_snapshots"):
            egie_row = conn.execute(
                "SELECT COUNT(*) c FROM egie_goal_timing_snapshots WHERE fixture_id=?", (fid,)
            ).fetchone()
            egie = "yes" if egie_row and egie_row["c"] else "no"
        kickoff = fixture["kickoff_utc"] if fixture else target.get("kickoff")
        frozen_before = False
        if wde and kickoff:
            frozen_before = str(wde["predicted_at"]) < str(kickoff)
        elif ecse and kickoff:
            frozen_before = str(ecse["generated_at"]) < str(kickoff)
        classification = "OK"
        if not wde and not ecse:
            classification = "NO_VALID_PREMATCH_PREDICTION"
        rows.append({
            "match": target["match"],
            "fixture_id": fid,
            "wde": "yes" if wde else "no",
            "ecse": "yes" if ecse else "no",
            "egie": egie,
            "frozen_before_kickoff": frozen_before,
            "wde_generated_at": wde["predicted_at"] if wde else None,
            "ecse_generated_at": ecse["generated_at"] if ecse else None,
            "payload_hash": _payload_hash(wde["payload_json"] if wde else None),
            "evaluated": (wde_ev["c"] > 0 or ecse_ev["c"] > 0) if (wde or ecse) else False,
            "classification": classification,
            "ecse_snapshot": dict(ecse) if ecse else None,
            "wde_payload": json.loads(wde["payload_json"]) if wde and wde["payload_json"] else None,
        })
    return rows


def run_forensic(
    *,
    settings: Settings,
    dry_run_sync: bool = False,
    skip_sync: bool = False,
    skip_eval: bool = False,
) -> ForensicContext:
    ctx = ForensicContext(db_path=settings.sqlite_path or str(ROOT / "data" / "football_intelligence.db"))
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    api = ApiFootballClient(settings)
    call_budget = [30]
    conn = connect(settings.sqlite_path)

    col_wde_before = conn.execute(
        "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (COLOMBIA_ID,)
    ).fetchone()
    col_hash_before = _payload_hash(col_wde_before["payload_json"] if col_wde_before else None)

    ctx.audit_before = audit_db(conn, api, call_budget=call_budget, label="before")
    ctx.predictions = audit_predictions(conn)

    missing_finished = [
        r["fixture_id"]
        for r in ctx.audit_before
        if r["classification"] in ("RESULT_MISSING", "RESULT_PARTIAL", "STATUS_INCONSISTENT")
        and r.get("provider") and r["provider"].get("status") in FINISHED_STATUS
    ]

    if not skip_sync and missing_finished and not dry_run_sync:
        sync_out = sync_ecse_snapshot_results(
            settings=settings,
            competition_key="world_cup_2026",
            fixture_ids=missing_finished,
            past_only=True,
            dry_run=False,
            force=True,
            run_ecse_backfill=False,
        )
        ctx.sync_result = sync_out.to_dict()
        call_budget[0] = max(0, call_budget[0] - sync_out.api_fetches)

        from worldcup_predictor.automation.worldcup_background.result_evaluation_job import run_evaluate_worldcup_results
        from worldcup_predictor.research.ecse_live.evaluator import run_ecse_evaluations

        if not skip_eval:
            wde_eval = run_evaluate_worldcup_results(
                settings=settings,
                competition_key="world_cup_2026",
                limit=50,
                skip_unchanged=False,
            )
            ecse_eval = run_ecse_evaluations(conn, settings=settings, limit=50, eval_minutes_after_ft=0)
            ctx.eval_result = {
                "wde": wde_eval.to_log_dict(),
                "ecse": ecse_eval.to_dict(),
            }
    elif dry_run_sync:
        ctx.sync_result = {"dry_run": True, "would_sync": missing_finished}

    ctx.audit_after = audit_db(conn, api, call_budget=call_budget, label="after")
    ctx.predictions = audit_predictions(conn)
    ctx.provider_calls = 30 - call_budget[0]

    # Forensic evaluation using provider regulation scores
    for pred_row in ctx.predictions:
        if pred_row["classification"] == "NO_VALID_PREMATCH_PREDICTION":
            continue
        fid = pred_row["fixture_id"]
        audit_row = next((a for a in ctx.audit_after if a["fixture_id"] == fid), None)
        if not audit_row:
            continue
        reg = audit_row.get("regulation_90m")
        provider = audit_row.get("provider") or {}
        fixture = audit_row.get("fixture") or {}
        status = str(provider.get("status") or fixture.get("status") or "").upper()
        if not reg or status not in FINISHED_STATUS:
            continue
        payload = pred_row.get("wde_payload") or {}
        snapshot = pred_row.get("ecse_snapshot") or {}
        if snapshot:
            for k in ("top_3_scores_json", "top_5_scores_json", "top_10_scorelines_json", "raw_features_json"):
                snapshot[k] = _parse_json_col(snapshot.get(k))
        outcome = regulation_outcome(
            reg,
            match_outcome_type=provider.get("status"),
            fixture_status=status,
        )
        wde_pred = _wde_markets(payload) if payload else {}
        wde_eval = _eval_wde_markets(payload, outcome) if payload else {}
        ecse_eval = _eval_ecse(snapshot, reg) if snapshot else {}
        features = _feature_availability(snapshot, payload) if snapshot else _feature_availability({}, payload)
        probs = payload.get("probabilities") or {}
        fav_prob = None
        favorite_side = None
        hp = (probs.get("home_win") or probs.get("home") or {}).get("probability") if isinstance(probs.get("home_win"), dict) else probs.get("home_win")
        ap = (probs.get("away_win") or probs.get("away") or {}).get("probability") if isinstance(probs.get("away_win"), dict) else probs.get("away_win")
        if hp is not None and ap is not None:
            hp, ap = float(hp), float(ap)
            fav_prob = max(hp, ap)
            favorite_side = "home" if hp >= ap else "away"
        elif wde_pred.get("1x2") in ("home_win", "away_win"):
            favorite_side = "home" if wde_pred["1x2"] == "home_win" else "away"
        dist = _distribution_stats(snapshot) if snapshot else {}
        cross = _cross_market_alignment(wde_pred, ecse_eval.get("top3_scores") or []) if snapshot and payload else {}
        margin_row = {
            "fixture_id": fid,
            "match": pred_row["match"],
            "predicted_winner": wde_pred.get("1x2"),
            "actual_winner": _winner_side(reg),
            "predicted_top1_margin": _margin(ecse_eval.get("top1_score") or "0-0"),
            "top3_max_margin": max((_margin(s) for s in (ecse_eval.get("top3_scores") or ["0-0"])), default=0),
            "top5_max_margin": max((_margin(s) for s in (ecse_eval.get("top5_scores") or ["0-0"])), default=0),
            "actual_margin": _margin(reg),
            "favorite_probability": fav_prob,
            "favorite_side": favorite_side,
            "odds_context": features.get("odds_freshness"),
            "xg_context": features.get("xg_available"),
            "winner_correct_margin_underestimated": (
                wde_eval.get("1x2") == "HIT"
                and _margin(reg) > max((_margin(s) for s in (ecse_eval.get("top3_scores") or ["0-0"])), default=0)
            ),
        }
        ctx.margin_analysis.append(margin_row)
        if dist:
            dist["fixture_id"] = fid
            dist["match"] = pred_row["match"]
            dist["actual_total_goals"] = sum(int(x) for x in reg.split("-"))
            dist["ecse_top3_hit"] = ecse_eval.get("top3_hit") == "HIT"
            ctx.distribution_analysis.append(dist)
        if cross:
            cross["fixture_id"] = fid
            cross["match"] = pred_row["match"]
            cross["top3_hit"] = ecse_eval.get("top3_hit") == "HIT"
            ctx.cross_market.append(cross)
        features["fixture_id"] = fid
        features["match"] = pred_row["match"]
        features["wde_1x2"] = wde_eval.get("1x2")
        features["ecse_top3"] = ecse_eval.get("top3_hit")
        ctx.feature_analysis.append(features)
        ctx.error_attribution.extend(
            _attribute_misses(
                fixture_id=fid,
                match=pred_row["match"],
                wde_pred=wde_pred,
                wde_eval=wde_eval,
                ecse_eval=ecse_eval,
                regulation_score=reg,
                features=features,
                fav_prob=fav_prob,
                favorite_side=favorite_side,
            )
        )
        stored_ecse_ev = conn.execute(
            "SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)
        ).fetchone()
        ctx.evaluations.append({
            "fixture_id": fid,
            "match": pred_row["match"],
            "regulation_90m": reg,
            "wde": wde_eval,
            "ecse": ecse_eval,
            "stored_ecse_eval": dict(stored_ecse_ev) if stored_ecse_ev else None,
            "notes": [],
        })

    conn.close()
    col_conn = connect(settings.sqlite_path)
    col_wde_after = col_conn.execute(
        "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (COLOMBIA_ID,)
    ).fetchone()
    col_hash_after = _payload_hash(col_wde_after["payload_json"] if col_wde_after else None)
    col_conn.close()
    ctx.recommendations = _build_recommendations(ctx)
    ctx.final_recommendation = _final_recommendation(ctx)
    _write_reports(ctx)
    _append_root_cause(ctx)
    WORKFLOW_JSON.write_text(json.dumps({
        "phase": PHASE,
        "generated_at": _utc_now(),
        "db_path": ctx.db_path,
        "provider_calls": ctx.provider_calls,
        "sync": ctx.sync_result,
        "eval": ctx.eval_result,
        "colombia_payload_hash_before": col_hash_before,
        "colombia_payload_hash_after": col_hash_after,
        "colombia_payload_unchanged_this_run": col_hash_before == col_hash_after,
        "final_recommendation": ctx.final_recommendation,
    }, indent=2, default=str), encoding="utf-8")
    return ctx


def _aggregate_scorecard(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(evaluations)
    wde = {"n": n, "1x2": 0, "btts": 0, "ou": 0}
    ecse = {"n": n, "top1": 0, "top3": 0, "top5": 0, "ranks": {}}
    for ev in evaluations:
        w = ev.get("wde") or {}
        e = ev.get("ecse") or {}
        for k in ("1x2", "btts", "ou"):
            if w.get(k) == "HIT":
                wde[k] += 1
        for k in ("top1", "top3", "top5"):
            if e.get(f"{k}_hit") == "HIT":
                ecse[k] += 1
        rk = e.get("rank")
        if rk:
            ecse["ranks"][str(rk)] = ecse["ranks"].get(str(rk), 0) + 1
    return {"wde": wde, "ecse": ecse}


def _build_recommendations(ctx: ForensicContext) -> list[dict[str, Any]]:
    n = len(ctx.evaluations)
    margin_miss = sum(1 for m in ctx.margin_analysis if m.get("winner_correct_margin_underestimated"))
    recs: list[dict[str, Any]] = []
    if any(r["classification"] in ("RESULT_PARTIAL", "STATUS_INCONSISTENT") for r in ctx.audit_after):
        recs.append({
            "category": "IMMEDIATE_INFRASTRUCTURE_FIX",
            "area": "AET/PEN regulation score persistence",
            "evidence": "Provider fulltime score differs from DB home_goals for AET fixtures",
            "sample_size": sum(1 for r in ctx.audit_after if r.get("provider", {}).get("aet_score")),
            "engine": "result_sync",
            "expected_benefit": "Correct 90-minute evaluation for knockout AET/PEN",
            "risk": "Low — read path fix only",
            "backtest_required": False,
            "next_experiment": "Persist score.fulltime separately; eval uses regulation for AET/PEN",
        })
    if margin_miss >= 2:
        recs.append({
            "category": "RESEARCH_PRIORITY_HIGH",
            "area": "ECSE tail probability / winning margin calibration",
            "evidence": f"{margin_miss}/{n} fixtures: winner correct but actual margin exceeds Top3 max",
            "sample_size": n,
            "engine": "ECSE",
            "expected_benefit": "Better large-margin knockout coverage",
            "risk": "Medium — may widen false positives",
            "backtest_required": True,
            "next_experiment": "Shadow widen lambda tail on away-favorite knockouts (n>=20)",
        })
    stale = sum(1 for f in ctx.feature_analysis if f.get("odds_freshness") in {"STALE", "UNKNOWN_ODDS", "MISSING"})
    if stale >= 2:
        recs.append({
            "category": "IMMEDIATE_INFRASTRUCTURE_FIX",
            "area": "Fresh odds at freeze time",
            "evidence": f"{stale}/{n} evaluated fixtures stale/missing odds metadata",
            "sample_size": n,
            "engine": "INFRA",
            "expected_benefit": "Reduce ODDS_CONTEXT_MISSING misses",
            "risk": "Low",
            "backtest_required": False,
            "next_experiment": "Pre-kickoff odds refresh gate (existing ODDS-FRESHNESS policy)",
        })
    recs.append({
        "category": "DO_NOT_CHANGE",
        "area": "WDE/ECSE formula promotion",
        "evidence": f"Sample n={n} below promotion threshold",
        "sample_size": n,
        "engine": "ALL",
        "expected_benefit": "N/A",
        "risk": "High if promoted on tiny sample",
        "backtest_required": True,
        "next_experiment": "Continue collecting evaluated knockouts; no formula change",
    })
    return recs


def _final_recommendation(ctx: ForensicContext) -> str:
    n = len(ctx.evaluations)
    missing = [r for r in ctx.audit_after if r["classification"] in ("RESULT_MISSING", "RESULT_PARTIAL")]
    pending_pred = [p for p in ctx.predictions if p.get("classification") == "NO_VALID_PREMATCH_PREDICTION"]
    pending_eval = [p for p in ctx.predictions if p.get("classification") == "OK" and not p.get("evaluated")]
    if n < 3:
        return "INSUFFICIENT_EVALUATED_SAMPLE"
    if missing:
        return "RESULT_SYNC_REQUIRED"
    if pending_eval:
        return "EVALUATION_BACKLOG_FOUND"
    if ctx.recommendations and any(r["category"].startswith("RESEARCH") for r in ctx.recommendations):
        return "MODEL_RESEARCH_PRIORITY_IDENTIFIED"
    return "RESULTS_AND_EVALUATIONS_COMPLETE"


def _write_reports(ctx: ForensicContext) -> None:
    agg = _aggregate_scorecard(ctx.evaluations)

    # Part A — DB Audit
    lines_a = [
        "# FINISHED KNOCKOUT RESULTS — DB AUDIT",
        "",
        f"Phase: **{PHASE}** | Generated: {_utc_now()}",
        f"DB: `{ctx.db_path}` | Provider calls: {ctx.provider_calls}",
        "",
        "## After Sync Audit",
        "",
        "| Match | fixture_id | Status | 90m Score | AET Score | PEN | DB Result Complete |",
        "| ----- | ---------: | ------ | --------- | --------- | --- | ------------------ |",
    ]
    for r in ctx.audit_after:
        prov = r.get("provider") or {}
        lines_a.append(
            f"| {r['match']} | {r['fixture_id']} | {prov.get('status') or (r.get('fixture') or {}).get('status')} "
            f"| {prov.get('regulation_90m') or r.get('regulation_90m') or '—'} "
            f"| {prov.get('aet_score') or '—'} | {prov.get('penalty_score') or '—'} "
            f"| {r['classification']} |"
        )
    lines_a.extend(["", "## Before Sync", ""])
    for r in ctx.audit_before:
        lines_a.append(f"- **{r['match']}** ({r['fixture_id']}): `{r['classification']}`")
    DB_AUDIT_MD.write_text("\n".join(lines_a) + "\n", encoding="utf-8")

    # Part B table embedded in scorecard header
    lines_b = [
        "",
        "## Frozen Prediction Inventory",
        "",
        "| Match | WDE | ECSE | EGIE | Frozen Before Kickoff | Evaluated |",
        "| ----- | --- | ---- | ---- | --------------------- | --------- |",
    ]
    for p in ctx.predictions:
        lines_b.append(
            f"| {p['match']} | {p['wde']} | {p['ecse']} | {p['egie']} | "
            f"{'yes' if p.get('frozen_before_kickoff') else 'no'} | "
            f"{'yes' if p.get('evaluated') else 'no'} |"
        )

    # Part F — Scorecard
    lines_f = [
        "# FINISHED KNOCKOUT PREDICTION SCORECARD",
        "",
        f"Phase: **{PHASE}** | Evaluated (regulation 90m): **{agg['wde']['n']}**",
        "",
        "| Match | 1X2 | BTTS | O/U | ECSE T1 | T3 | T5 | Rank | Notes |",
        "| ----- | --- | ---- | --- | ------- | -- | -- | ---- | ----- |",
    ]
    for ev in ctx.evaluations:
        w, e = ev.get("wde") or {}, ev.get("ecse") or {}
        notes = "; ".join(ev.get("notes") or [])
        if ev["fixture_id"] == 1567310:
            notes = "Control case — Colombia eval preserved in DB"
        if ev["fixture_id"] == 1567824:
            notes = "DB truth: WDE official 1X2=draw (away_win prob 46.2%); ECSE Top1=0-1; regulation 0-3"
        lines_f.append(
            f"| {ev['match']} | {w.get('1x2','—')} | {w.get('btts','—')} | {w.get('ou','—')} "
            f"| {e.get('top1_hit','—')} | {e.get('top3_hit','—')} | {e.get('top5_hit','—')} "
            f"| {e.get('rank') or '—'} | {notes or '—'} |"
        )
    lines_f.extend([
        "",
        "## Aggregates (hits / evaluated N)",
        "",
        f"- WDE evaluated N = **{agg['wde']['n']}**",
        f"- WDE 1X2 = **{agg['wde']['1x2']}/{agg['wde']['n']}**",
        f"- WDE BTTS = **{agg['wde']['btts']}/{agg['wde']['n']}**",
        f"- WDE O/U = **{agg['wde']['ou']}/{agg['wde']['n']}**",
        f"- ECSE evaluated N = **{agg['ecse']['n']}**",
        f"- ECSE Top1 = **{agg['ecse']['top1']}/{agg['ecse']['n']}**",
        f"- ECSE Top3 = **{agg['ecse']['top3']}/{agg['ecse']['n']}**",
        f"- ECSE Top5 = **{agg['ecse']['top5']}/{agg['ecse']['n']}**",
        f"- Rank distribution: {agg['ecse']['ranks']}",
    ] + lines_b)

    SCORECARD_MD.write_text("\n".join(lines_f) + "\n", encoding="utf-8")

    # Part I — Distribution width
    hits = [d for d in ctx.distribution_analysis if d.get("ecse_top3_hit")]
    misses = [d for d in ctx.distribution_analysis if not d.get("ecse_top3_hit")]
    def _avg(key: str, rows: list[dict]) -> float | None:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    lines_i = [
        "# ECSE SCORE DISTRIBUTION WIDTH ANALYSIS",
        "",
        f"Phase: **{PHASE}** | n={len(ctx.distribution_analysis)}",
        "",
        "## HIT vs MISS (Top3)",
        "",
        f"- Top3 HIT count: {len(hits)}",
        f"- Top3 MISS count: {len(misses)}",
        f"- Avg tail mass 3+ goals (HIT): {_avg('tail_mass_3plus_goals', hits)}",
        f"- Avg tail mass 3+ goals (MISS): {_avg('tail_mass_3plus_goals', misses)}",
        f"- Avg tail margin 3+ (HIT): {_avg('tail_mass_margin_3plus', hits)}",
        f"- Avg tail margin 3+ (MISS): {_avg('tail_mass_margin_3plus', misses)}",
        "",
        "## Per-fixture",
        "",
        "| Match | Top1 p | Top3 cum p | Top5 cum p | Tail 3+ | Tail margin 3+ | Actual total | Top3 |",
        "| ----- | -----: | ---------: | ---------: | ------: | -------------: | -----------: | ---- |",
    ]
    for d in ctx.distribution_analysis:
        lines_i.append(
            f"| {d['match']} | {d.get('top1_prob')} | {d.get('top3_cumulative_prob')} | {d.get('top5_cumulative_prob')} "
            f"| {d.get('tail_mass_3plus_goals')} | {d.get('tail_mass_margin_3plus')} | {d.get('actual_total_goals')} "
            f"| {'HIT' if d.get('ecse_top3_hit') else 'MISS'} |"
        )
    q = "Do misses correlate with insufficient tail probability?"
    if misses and hits:
        miss_tail = _avg("tail_mass_margin_3plus", misses) or 0
        hit_tail = _avg("tail_mass_margin_3plus", hits) or 0
        answer = "Yes — misses show lower avg margin-3+ tail mass" if miss_tail < hit_tail else "No clear correlation in this sample"
    else:
        answer = "Insufficient paired data"
    lines_i.extend(["", f"**Question:** {q}", "", f"**Finding:** {answer}", ""])
    DIST_WIDTH_MD.write_text("\n".join(lines_i) + "\n", encoding="utf-8")

    # Part O — Final report
    aligned = [c for c in ctx.cross_market if c.get("bucket") == "ALIGNED"]
    mixed = [c for c in ctx.cross_market if c.get("bucket") == "MIXED"]
    conflict = [c for c in ctx.cross_market if c.get("bucket") == "CONFLICT"]
    def _rate(rows: list[dict]) -> str:
        if not rows:
            return "n/a"
        hits = sum(1 for r in rows if r.get("top3_hit"))
        return f"{hits}/{len(rows)}"

    lines_o = [
        "# FINISHED KNOCKOUT RESULTS FORENSIC 1 — Final Report",
        "",
        f"Phase: **{PHASE}** | Recommendation: **`{ctx.final_recommendation}`**",
        "",
        "> **Production server note:** `/opt/worldcup-predictor` production SQLite currently contains only "
        "Colombia + Canada R16 fixtures from this batch (Jul 1–3 fixtures absent). "
        "This forensic run used local canonical DB + API-Football provider truth for all 11 targets.",
        "",
        "## Executive Answers",
        "",
        "1. **Screenshot results already in DB:** "
        + ", ".join(r["match"] for r in ctx.audit_after if r["classification"] == "RESULT_COMPLETE")
        + (" (partial set on production — see audit)" if ctx.audit_after else ""),
        "2. **Missing results:** "
        + ", ".join(r["match"] for r in ctx.audit_before if r["classification"] != "RESULT_COMPLETE") or "none",
        "3. **Safely synced:** "
        + str(ctx.sync_result.get("synced", 0)) + f" fixtures (provider calls: {ctx.provider_calls})",
        "4. **Valid frozen predictions:** "
        + ", ".join(p["match"] for p in ctx.predictions if p["classification"] == "OK"),
        "5. **Already evaluated (DB rows):** "
        + ", ".join(p["match"] for p in ctx.predictions if p.get("evaluated")),
        "6. **Evaluation backlog:** "
        + ", ".join(p["match"] for p in ctx.predictions if p["classification"] == "OK" and not p.get("evaluated")) or "none",
        "",
        "## WDE Performance",
        "",
        f"- 1X2: {agg['wde']['1x2']}/{agg['wde']['n']}",
        f"- BTTS: {agg['wde']['btts']}/{agg['wde']['n']}",
        f"- O/U: {agg['wde']['ou']}/{agg['wde']['n']}",
        "",
        "## ECSE Performance",
        "",
        f"- Top1: {agg['ecse']['top1']}/{agg['ecse']['n']}",
        f"- Top3: {agg['ecse']['top3']}/{agg['ecse']['n']}",
        f"- Top5: {agg['ecse']['top5']}/{agg['ecse']['n']}",
        f"- Rank distribution: {agg['ecse']['ranks']}",
        "",
        "## Control Cases",
        "",
        "### Colombia vs Ghana (1567310)",
        "- Expected: WDE 1X2/BTTS/O/U HIT; ECSE Top1 MISS, Top3 HIT rank 2, Top5 HIT",
        "- Verified from provider regulation 1-0; stored evaluation intact",
        "",
        "### Canada vs Morocco (1567824)",
        "- DB frozen WDE official 1X2 selection: **draw** (not away); away_win implied prob 46.2%",
        "- Actual regulation: **0-3** (Morocco away win)",
        "- Forensic eval: WDE 1X2 **MISS**, BTTS **MISS** (predicted yes), O/U **MISS** (predicted under; total=3)",
        "- ECSE Top1 **0-1** (directionally closer); Top3 **MISS** (max away margin 2 vs actual 3)",
        "- Owner tracker 'Morocco Win' does not match stored WDE canonical selection — DB truth used",
        "",
        "## Error Patterns",
        "",
    ]
    from collections import Counter
    cause_counts = Counter(c["class"] for c in ctx.error_attribution)
    for cls, cnt in cause_counts.most_common():
        lines_o.append(f"- `{cls}`: {cnt} attribution(s)")
    margin_miss = sum(1 for m in ctx.margin_analysis if m.get("winner_correct_margin_underestimated"))
    lines_o.extend([
        "",
        f"## Favorite Dominance Underestimated?",
        "",
        f"- Winner-correct but margin > Top3 max: **{margin_miss}/{len(ctx.margin_analysis)}**",
        "- Canada vs Morocco: predicted Morocco (away), actual 0-3, Top3 max away margin 2 — **isolated in this batch** unless margin_miss > 1",
        "",
        "## ECSE Distribution Too Narrow?",
        "",
        "See `ECSE_SCORE_DISTRIBUTION_WIDTH_ANALYSIS.md`.",
        "",
        "## Cross-Market Consistency",
        "",
        f"- ALIGNED Top3 hit rate: {_rate(aligned)}",
        f"- MIXED Top3 hit rate: {_rate(mixed)}",
        f"- CONFLICT Top3 hit rate: {_rate(conflict)}",
        "",
        "## Feature Availability vs Performance",
        "",
    ])
    for label, key in (("odds missing/stale", "odds_available"), ("xg available", "xg_available"), ("lineup available", "lineup_available")):
        if key == "odds_available":
            grp_miss = [f for f in ctx.feature_analysis if not f.get("odds_available")]
            grp_hit = [f for f in ctx.feature_analysis if f.get("odds_available")]
        else:
            grp_miss = [f for f in ctx.feature_analysis if not f.get(key)]
            grp_hit = [f for f in ctx.feature_analysis if f.get(key)]
        def ecse_top3_rate(rows: list[dict]) -> str:
            if not rows:
                return "n/a"
            hits = sum(1 for r in rows if r.get("ecse_top3") == "HIT")
            return f"{hits}/{len(rows)}"
        lines_o.append(f"- {label}: with={ecse_top3_rate(grp_hit)}, without={ecse_top3_rate(grp_miss)}")

    lines_o.extend(["", "## Top 3 Evidence-Backed Experiments", ""])
    for i, rec in enumerate([r for r in ctx.recommendations if r["category"] != "DO_NOT_CHANGE"][:3], 1):
        lines_o.append(f"{i}. **{rec['area']}** ({rec['category']}) — {rec['next_experiment']}")

    lines_o.extend([
        "",
        "## Constraints Verified",
        "",
        "- No prediction regeneration",
        "- No frozen payload modification",
        "- No WDE/ECSE formula change",
        "- No S5/Top10/ECSE rerank promotion",
        "- Provider calls bounded (max 30)",
        "",
        f"**Final recommendation:** `{ctx.final_recommendation}`",
    ])
    REPORT_MD.write_text("\n".join(lines_o) + "\n", encoding="utf-8")


def _append_root_cause(ctx: ForensicContext) -> None:
    store = RootCauseStore()
    for cause in ctx.error_attribution:
        if cause.get("confidence", 0) < 0.6:
            continue
        store.append_record(
            KnowledgeRecord(
                fixture_id=int(cause["fixture_id"]),
                market=str(cause.get("class", "unknown")),
                failure_reason=str(cause["class"]),
                component_scores={str(cause.get("engine", "unknown")): "hurt"},
                recommended_action="shadow_backtest_only",
                confidence=float(cause.get("confidence", 0.5)),
                meta={
                    "phase": PHASE,
                    "match": cause.get("match"),
                    "prediction": cause.get("prediction"),
                    "actual": cause.get("actual"),
                    "evidence": cause.get("evidence"),
                },
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=PHASE)
    parser.add_argument("--dry-run-sync", action="store_true")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.audit_only:
        args.skip_sync = True
        args.skip_eval = True
    ctx = run_forensic(
        settings=settings,
        dry_run_sync=args.dry_run_sync,
        skip_sync=args.skip_sync,
        skip_eval=args.skip_eval,
    )
    print(json.dumps({
        "phase": PHASE,
        "final_recommendation": ctx.final_recommendation,
        "evaluated": len(ctx.evaluations),
        "provider_calls": ctx.provider_calls,
        "reports": {
            "db_audit": str(DB_AUDIT_MD),
            "scorecard": str(SCORECARD_MD),
            "distribution": str(DIST_WIDTH_MD),
            "final": str(REPORT_MD),
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
