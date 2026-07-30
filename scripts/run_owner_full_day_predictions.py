#!/usr/bin/env python3
"""Owner full-day prediction & freeze mode (Europe/Vienna).

Discovers ALL supported Tier A/B fixtures for the Vienna calendar day —
no arbitrary kickoff-hour filter. Predicts every still-prematch eligible
fixture (one job each), reuses immutable freezes when present, builds
multi-category rankings, and prepares next-day evaluation.

Does not modify WDE/ECSE/BTTS/O/U formulas or weaken quality gates.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.bridge import (
    ForwardEvalBridgeContext,
    maybe_capture_after_prediction_persistence,
)
from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.config import GptActionsConfig, load_gpt_actions_config
from worldcup_predictor.gpt_actions.delegation import _fixture_from_db, discover_today_matches
from worldcup_predictor.gpt_actions.job_status import build_job_status_fields
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS
from worldcup_predictor.gpt_actions.worker import enqueue_prediction_job
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction, refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.research.ecse_live.store import get_snapshot

TZ_NAME = "Europe/Vienna"


def _run_l2f_true_forward_shadow(
    *,
    prod_conn,
    fixture_id: int,
    freeze_meta: dict[str, Any],
    prediction_scope: str | None,
    settings,
) -> dict[str, Any]:
    """Non-blocking true-forward shadow after freeze. Never fails canonical."""
    try:
        from worldcup_predictor.research.infra_l2f_forward.forward_hook import (
            maybe_run_l2f_forward_shadow,
        )

        meta = dict(freeze_meta or {})
        # Hook accepts only created|reused capture_status.
        cs = str(meta.get("capture_status") or "")
        if cs in ("reused_existing", "reused"):
            meta["capture_status"] = "reused"
        elif meta.get("created"):
            meta["capture_status"] = "created"
        elif meta.get("reused"):
            meta["capture_status"] = "reused"
        if not meta.get("prediction_scope") and prediction_scope:
            meta["prediction_scope"] = prediction_scope
        return maybe_run_l2f_forward_shadow(
            conn=prod_conn,
            fixture_id=int(fixture_id),
            freeze_meta=meta,
            prediction_scope=prediction_scope or meta.get("prediction_scope"),
            settings=settings,
            backfill=False,
        )
    except Exception as exc:  # noqa: BLE001 — hard isolation
        return {
            "shadow_system": "l2f_forward",
            "canonical_unaffected": True,
            "status": "failed",
            "reason": f"hook_exception:{type(exc).__name__}",
            "cohort_type": "true_forward",
        }
TZ = ZoneInfo(TZ_NAME)
REPORT_DIR = ROOT / "reports" / "owner" / "daily"

STARTED = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "PEN"})
FINISHED = frozenset({"FT", "AET", "PEN"})
CANCELLED = frozenset({"CANC", "ABD", "PST", "SUSP", "INT", "AWD", "WO"})
FRIENDLY = frozenset({"friendlies", "friendly", "club_friendlies", "international_friendlies", "league_667"})
PREMATCH = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", ""})
FRESH_OK = frozenset({FreshnessStatus.FRESH_ODDS.value, "fresh", "ODDS_FRESH", "FRESH_ODDS"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _vienna(v: str | None) -> str:
    dt = _parse_dt(v)
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z") if dt else ""


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _git_sha(ref: str) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", ref], cwd=str(ROOT), text=True).strip()
    except Exception:
        return "UNKNOWN"


def _league_meta(comp: str | None) -> dict[str, Any]:
    canon = normalize_competition_key(comp) or str(comp or "unknown")
    try:
        c = get_competition(canon)
        return {"league": c.name, "league_country": c.country or "UNKNOWN", "competition_key": canon}
    except KeyError:
        meta = TIER_B_SHADOW_DOMAINS.get(canon) or {}
        return {
            "league": meta.get("name") or canon.replace("_", " ").title(),
            "league_country": str(meta.get("country") or "UNKNOWN"),
            "competition_key": canon,
        }


def _fresh_ok(v: Any) -> bool:
    if isinstance(v, dict):
        return any(
            _fresh_ok(v.get(k))
            for k in ("freshness_flag", "odds_freshness_status", "policy_status", "freshness_class")
        )
    t = str(v or "").strip()
    return t in FRESH_OK or ("fresh" in t.lower() and "stale" not in t.lower())


def _fav(h, d, a):
    vals = {"home_win": h, "draw": d, "away_win": a}
    if any(v is None or v <= 1 for v in vals.values()):
        return None
    return min(vals, key=lambda k: vals[k] or 99)


def _odds_blob(snap: Any) -> dict[str, Any]:
    if snap is None:
        return {"complete": False}
    d = snap.to_dict() if hasattr(snap, "to_dict") else dict(snap)
    h, dr, a = _f(d.get("home_odds")), _f(d.get("draw_odds")), _f(d.get("away_odds"))
    complete = all(v is not None and v > 1 for v in (h, dr, a))
    return {
        "snapshot_id": d.get("row_id"),
        "home": h,
        "draw": dr,
        "away": a,
        "bookmaker_count": d.get("bookmaker_count"),
        "provider": d.get("provider"),
        "captured_at": d.get("fetched_at_utc"),
        "odds_age_minutes": d.get("odds_age_minutes"),
        "allowed_ttl_seconds": d.get("allowed_ttl_seconds"),
        "freshness_status": d.get("freshness_class") or d.get("freshness_status"),
        "market_direction": _fav(h, dr, a) if complete else None,
        "complete": complete,
    }


def _top5(snap: dict | None) -> list[dict[str, Any]]:
    if not snap:
        return []
    top10 = snap.get("top_10_scorelines") or []
    prob_map = {
        str(r.get("scoreline") or r.get("score")): _f(r.get("probability"))
        for r in top10
        if isinstance(r, dict)
    }
    rows = []
    raw = snap.get("top_5_scores") or []
    for i, item in enumerate(raw[:5], start=1):
        if isinstance(item, str):
            rows.append({"rank": i, "score": item, "probability": prob_map.get(item)})
        elif isinstance(item, dict):
            sc = item.get("scoreline") or item.get("score")
            rows.append({"rank": i, "score": sc, "probability": _f(item.get("probability")) or prob_map.get(str(sc))})
    if len(rows) < 5 and top10:
        rows = []
        for i, item in enumerate(top10[:5], start=1):
            if isinstance(item, dict):
                sc = item.get("scoreline") or item.get("score")
                rows.append({"rank": i, "score": sc, "probability": _f(item.get("probability"))})
    return rows[:5]


def _mass(rows: list[dict], n: int) -> float | None:
    vals = []
    for r in rows[:n]:
        p = _f(r.get("probability"))
        if p is None:
            continue
        vals.append(p / 100.0 if p > 1 else p)
    return round(sum(vals), 6) if vals else None


def _entropy(rows: list[dict]) -> float | None:
    vals = []
    for r in rows:
        p = _f(r.get("probability"))
        if p is None:
            continue
        if p > 1:
            p /= 100.0
        if p > 0:
            vals.append(p)
    if not vals:
        return None
    s = sum(vals)
    vals = [v / s for v in vals]
    return round(-sum(v * math.log(v) for v in vals), 6)


def _cell(t: dict | None) -> str:
    if not t:
        return "—"
    p = _f(t.get("probability"))
    if p is None:
        return str(t.get("score"))
    pct = f"{p * 100:.1f}%" if p <= 1 else f"{p:.1f}%"
    return f"{t.get('score')} ({pct})"


def _conf_class(conf: float | None) -> str:
    if conf is None:
        return "VERY_LOW"
    c = conf / 100.0 if conf > 1.5 else conf
    if c >= 0.75:
        return "VERY_HIGH"
    if c >= 0.60:
        return "HIGH"
    if c >= 0.45:
        return "MEDIUM"
    if c >= 0.30:
        return "LOW"
    return "VERY_LOW"


def _consensus(wde: str | None, top1: str | None, market: str | None, ft: str | None) -> str:
    if not wde or not top1:
        return "INSUFFICIENT_DATA"
    if wde != top1:
        return "HIGH_CONFLICT"
    sides = [s for s in (wde, top1, market, ft) if s]
    if len(set(sides)) == 1 and len(sides) >= 3:
        return "HIGH_AGREEMENT"
    if market and wde != market:
        return "MIXED"
    if ft and wde != ft:
        return "MIXED"
    return "MODERATE_AGREEMENT"


def _dc(decision: str | None) -> str | None:
    if decision == "home_win":
        return "1X"
    if decision == "away_win":
        return "X2"
    if decision == "draw":
        return "NO_PREFERRED_DC_FOR_DRAW"
    return None


def _dnb(decision: str | None) -> str | None:
    if decision == "home_win":
        return "home"
    if decision == "away_win":
        return "away"
    if decision == "draw":
        return "NO_BET"
    return None


def _poll(job_id: str, store: JobStore, cfg: GptActionsConfig, deadline_s: int = 480) -> dict:
    final = None
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        rec = store.get(job_id)
        if not rec or not rec.get("job_id"):
            # Transient empty/partial read while worker rewrites the job file.
            time.sleep(1)
            continue
        fields = build_job_status_fields(rec, poll_after_seconds=cfg.poll_after_seconds)
        if fields.get("terminal"):
            final = {**rec, **fields}
            break
        time.sleep(max(1, int(fields.get("poll_after_seconds") or 3)))
    return {"final": final, "timed_out": final is None}


def _team_country(client: ApiFootballClient, team_id: int | None, cache: dict[int, str]) -> str:
    if not team_id:
        return "UNKNOWN"
    tid = int(team_id)
    if tid in cache:
        return cache[tid]
    try:
        result = client._safe_get("teams", {"id": tid}, placeholder_factory=lambda: [])
        if result.ok and result.data:
            country = str(((result.data[0] or {}).get("team") or {}).get("country") or "").strip()
            cache[tid] = country or "UNKNOWN"
            return cache[tid]
    except Exception:
        pass
    cache[tid] = "UNKNOWN"
    return "UNKNOWN"


def _extract(prod, fid: int) -> dict[str, Any]:
    stored = prod.execute(
        "SELECT payload_json, predicted_at, updated_at FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
        (fid,),
    ).fetchone()
    snap = get_snapshot(prod, fid)
    if not stored:
        return {"complete": False, "reason": "no_wsp"}
    try:
        payload = json.loads(stored["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return {"complete": False, "reason": "bad_payload"}
    sem = extract_wde_semantics(payload)
    probs = payload.get("probabilities") or {}
    btts = probs.get("btts") or {}
    ou = probs.get("over_under_2_5") or {}
    top5 = _top5(snap)
    sides = [scoreline_side(str(t.get("score") or "")) for t in top5 if t]
    top5_maj = Counter(sides).most_common(1)[0][0] if sides else None
    top1_side = scoreline_side(str((top5[0] or {}).get("score") or "")) if top5 else None
    dq = payload.get("data_quality") or payload.get("quality_status")
    if isinstance(dq, dict):
        dq = dq.get("status")
    conf = _f(sem.get("confidence") or payload.get("confidence"))
    return {
        "complete": bool(sem.get("decision_pick")) and bool(top5),
        "partial": bool(sem.get("decision_pick")) and not bool(top5),
        "predicted_at": stored["predicted_at"] or stored["updated_at"],
        "wde": {
            "decision": sem.get("decision_pick"),
            "ft_marginal": sem.get("probability_argmax"),
            "effective_1x2": sem.get("effective_pick"),
            "home_probability": sem.get("home_prob"),
            "draw_probability": sem.get("draw_prob"),
            "away_probability": sem.get("away_prob"),
            "confidence": conf,
            "confidence_class": _conf_class(conf),
            "execution_status": "OK",
            "quality_status": dq,
            "decision_source": sem.get("decision_source"),
            "model_version": sem.get("model_version"),
        },
        "btts": {
            "prediction": btts.get("selection"),
            "yes_probability": _f((btts.get("probabilities") or {}).get("yes")),
            "no_probability": _f((btts.get("probabilities") or {}).get("no")),
            "confidence": btts.get("confidence"),
            "execution_status": "OK" if btts else "UNAVAILABLE",
        },
        "ou25": {
            "preferred_side": ou.get("selection"),
            "over_probability": _f((ou.get("probabilities") or {}).get("over_2_5")),
            "under_probability": _f((ou.get("probabilities") or {}).get("under_2_5")),
            "confidence": ou.get("confidence"),
            "execution_status": "OK" if ou else "UNAVAILABLE",
        },
        "ecse": {
            "top1": top5[0] if len(top5) > 0 else None,
            "top2": top5[1] if len(top5) > 1 else None,
            "top3": top5[2] if len(top5) > 2 else None,
            "top4": top5[3] if len(top5) > 3 else None,
            "top5": top5[4] if len(top5) > 4 else None,
            "top1_probability": _f((top5[0] or {}).get("probability")) if top5 else None,
            "top3_mass": _mass(top5, 3),
            "top5_mass": _mass(top5, 5),
            "entropy": _entropy(top5),
            "lambda_home": snap.get("lambda_home") if snap else None,
            "lambda_away": snap.get("lambda_away") if snap else None,
            "total_lambda": (
                round(float(snap["lambda_home"]) + float(snap["lambda_away"]), 4)
                if snap and snap.get("lambda_home") is not None and snap.get("lambda_away") is not None
                else None
            ),
            "top1_side": top1_side,
            "top5_majority": top5_maj,
            "execution_status": "OK" if top5 else "MISSING",
            "model_version": snap.get("model_version") if snap else None,
            "snapshot_id": snap.get("id") if snap else None,
        },
        "data_quality": dq,
        "no_bet": bool(payload.get("no_bet")),
    }


def _main_risk(row: dict) -> str:
    cons = row.get("consensus")
    if cons == "HIGH_CONFLICT":
        return "model-conflict risk (WDE vs ECSE direction)"
    if cons == "MIXED":
        return "direction-reversal / market-model disagreement"
    ecse = row.get("ecse") or {}
    mass = _f(ecse.get("top5_mass")) or 0
    if mass < 0.40:
        return "diffuse Exact Score distribution (low Top5 mass)"
    if (row.get("wde") or {}).get("decision") == "draw" or ecse.get("top1_side") == "draw":
        return "draw risk"
    tot = _f(ecse.get("total_lambda")) or 0
    high = 0
    for k in ("top1", "top2", "top3", "top4", "top5"):
        t = ecse.get(k) or {}
        sc = str(t.get("score") or "")
        if "-" in sc:
            try:
                h, a = sc.split("-", 1)
                if int(h) + int(a) >= 4:
                    high += 1
            except ValueError:
                pass
    if tot >= 2.8 and high <= 1:
        return "high-score-tail risk"
    dq = str(row.get("data_quality") or "")
    if dq.upper() in {"LOW", "BLOCKED"} or (_f(dq) is not None and (_f(dq) or 100) < 60):
        return "low-data risk"
    return "residual exact-score variance"


def _dq_score(dq: Any) -> float:
    if isinstance(dq, (int, float)):
        return float(dq)
    m = {"HIGH": 90.0, "MEDIUM": 70.0, "LOW": 40.0, "OK": 80.0, "BLOCKED": 10.0}
    return float(m.get(str(dq or "").upper(), 50.0))


def _agree_score(cons: str | None) -> float:
    return {
        "HIGH_AGREEMENT": 3.0,
        "MODERATE_AGREEMENT": 2.0,
        "MIXED": 1.0,
        "HIGH_CONFLICT": 0.0,
        "INSUFFICIENT_DATA": 0.0,
    }.get(str(cons or ""), 0.0)


def _load_freeze(eval_conn, fid: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        """
        SELECT prediction_id, content_hash, source_payload_hash, frozen_at, freeze_status,
               prediction_scope, validation_tier, kickoff, odds_home, odds_draw, odds_away,
               bookmaker_count, odds_freshness, odds_freshness_status, immutable
        FROM frozen_predictions
        WHERE fixture_id=?
        ORDER BY frozen_at DESC
        LIMIT 1
        """,
        (fid,),
    ).fetchone()
    return dict(row) if row else None


def _build_rankings(predictions: list[dict]) -> dict[str, list[dict]]:
    complete = [p for p in predictions if p.get("prediction_complete")]

    def row_brief(p: dict, **extra: Any) -> dict:
        return {
            "fixture_id": p.get("fixture_id"),
            "match": f"{p.get('home_team')} vs {p.get('away_team')}",
            "league": p.get("league"),
            "kickoff_vienna": p.get("kickoff_vienna"),
            "wde": (p.get("wde") or {}).get("decision"),
            "confidence": (p.get("wde") or {}).get("confidence"),
            "consensus": p.get("consensus"),
            "data_quality": p.get("data_quality"),
            "top1": _cell((p.get("ecse") or {}).get("top1")),
            "top5_mass": (p.get("ecse") or {}).get("top5_mass"),
            "total_lambda": (p.get("ecse") or {}).get("total_lambda"),
            "btts": (p.get("btts") or {}).get("prediction"),
            "ou25": (p.get("ou25") or {}).get("preferred_side"),
            "no_bet": p.get("no_bet"),
            **extra,
        }

    end_result = sorted(
        [p for p in complete if not p.get("no_bet") and p.get("consensus") != "HIGH_CONFLICT"],
        key=lambda p: (
            -(_f((p.get("wde") or {}).get("confidence")) or 0),
            -_agree_score(p.get("consensus")),
            -_dq_score(p.get("data_quality")),
        ),
    )
    exact = sorted(
        [p for p in complete if (p.get("ecse") or {}).get("top1") and not p.get("no_bet")],
        key=lambda p: (
            -(_f((p.get("ecse") or {}).get("top5_mass")) or 0),
            (_f((p.get("ecse") or {}).get("entropy")) or 99),
            -_agree_score(p.get("consensus")),
            -(_f((p.get("wde") or {}).get("confidence")) or 0),
        ),
    )
    def _ou_side(p: dict) -> str:
        return str((p.get("ou25") or {}).get("preferred_side") or "").lower()

    under = sorted(
        [p for p in complete if _ou_side(p) in {"under_2_5", "under"}],
        key=lambda p: (
            (_f((p.get("ecse") or {}).get("total_lambda")) or 99),
            -(_f((p.get("ou25") or {}).get("under_probability")) or 0),
            -(_f((p.get("wde") or {}).get("confidence")) or 0),
        ),
    )
    over = sorted(
        [p for p in complete if _ou_side(p) in {"over_2_5", "over"}],
        key=lambda p: (
            -(_f((p.get("ecse") or {}).get("total_lambda")) or 0),
            -(_f((p.get("ou25") or {}).get("over_probability")) or 0),
            -(_f((p.get("wde") or {}).get("confidence")) or 0),
        ),
    )
    btts_yes = sorted(
        [p for p in complete if str((p.get("btts") or {}).get("prediction") or "").lower() in {"yes", "btts_yes"}],
        key=lambda p: (
            -(_f((p.get("btts") or {}).get("yes_probability")) or _f((p.get("btts") or {}).get("confidence")) or 0),
            -(_f((p.get("wde") or {}).get("confidence")) or 0),
        ),
    )
    safest = sorted(
        [p for p in complete if not p.get("no_bet")],
        key=lambda p: (
            -(_f((p.get("wde") or {}).get("confidence")) or 0),
            -_agree_score(p.get("consensus")),
            -_dq_score(p.get("data_quality")),
        ),
    )
    watch = [
        p
        for p in complete
        if (p.get("wde") or {}).get("confidence_class") == "MEDIUM"
        or p.get("consensus") in {"MIXED", "MODERATE_AGREEMENT", "HIGH_CONFLICT"}
    ]
    no_bet = [p for p in complete if p.get("no_bet")]

    return {
        "A_best_end_result_1x2": [row_brief(p, rank=i) for i, p in enumerate(end_result, 1)],
        "B_best_exact_score": [row_brief(p, rank=i) for i, p in enumerate(exact, 1)],
        "C_best_under": [row_brief(p, rank=i) for i, p in enumerate(under, 1)],
        "D_best_over": [row_brief(p, rank=i) for i, p in enumerate(over, 1)],
        "E_best_btts": [row_brief(p, rank=i) for i, p in enumerate(btts_yes, 1)],
        "F_safest_matches": [row_brief(p, rank=i) for i, p in enumerate(safest, 1)],
        "G_watchlist": [row_brief(p, rank=i) for i, p in enumerate(watch, 1)],
        "H_no_bet": [row_brief(p, rank=i) for i, p in enumerate(no_bet, 1)],
    }


def _assemble_prediction(
    meta: dict,
    pred: dict,
    odds: dict,
    *,
    source: str,
    eligibility: str,
    job_id: str | None,
    job_terminal: str | None,
    freeze_meta: dict,
    freeze_before_ko: bool,
) -> dict:
    wde = pred.get("wde") or {}
    ecse = pred.get("ecse") or {}
    cons = _consensus(
        wde.get("decision"),
        ecse.get("top1_side"),
        odds.get("market_direction"),
        wde.get("ft_marginal"),
    )
    out = {
        **meta,
        "eligibility": eligibility,
        "source": source,
        "odds": odds,
        "odds_freshness": odds.get("freshness_status"),
        "odds_age_minutes": odds.get("odds_age_minutes"),
        "wde": wde,
        "model_confidence_pct": wde.get("confidence"),
        "model_confidence_class": wde.get("confidence_class"),
        "btts": pred.get("btts"),
        "ou25": pred.get("ou25"),
        "double_chance": _dc(wde.get("decision")),
        "draw_no_bet": _dnb(wde.get("decision")),
        "ecse": ecse,
        "data_quality": pred.get("data_quality"),
        "no_bet": pred.get("no_bet"),
        "consensus": cons,
        "wde_ecse_agreement": wde.get("decision") == ecse.get("top1_side"),
        "wde_ft_agreement": wde.get("decision") == wde.get("ft_marginal"),
        "market_model_agreement": wde.get("decision") == odds.get("market_direction"),
        "job_id": job_id,
        "job_terminal": job_terminal,
        "prediction_complete": bool(pred.get("complete")),
        "prediction_partial": bool(pred.get("partial")) and not bool(pred.get("complete")),
        "freeze": freeze_meta,
        "freeze_before_kickoff": freeze_before_ko,
        "generated_at": pred.get("predicted_at"),
    }
    out["main_risk"] = _main_risk(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Owner full-day prediction & freeze mode")
    parser.add_argument("--date", default=None, help="Vienna calendar date YYYY-MM-DD (default: today Vienna)")
    args = parser.parse_args(argv)
    today = args.date or datetime.now(TZ).date().isoformat()

    art = ROOT / "artifacts" / "daily_pipeline" / today / "full_day"
    art.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    bootstrap_gpt_actions_runtime()
    settings = get_settings()
    client = ApiFootballClient(settings)
    now_utc = datetime.now(timezone.utc)
    now_vie = datetime.now(TZ)
    local_sha = _git_sha("HEAD")
    main_sha = _git_sha("origin/main")
    runtime = {
        "mode": "OWNER_FULL_DAY_PREDICTION",
        "current_utc": now_utc.isoformat(),
        "current_vienna": now_vie.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "target_date": today,
        "timezone": TZ_NAME,
        "kickoff_hour_filter": None,
        "scope": "owner",
        "local_commit": local_sha,
        "origin_main_commit": main_sha,
        "commit_mismatch": local_sha != main_sha,
        "canonical_pipeline_ready": bool(mcp_runtime.model_status().get("canonical_pipeline_ready")),
        "run_id": run_id,
        "policy": {
            "no_arbitrary_kickoff_hour_filter": True,
            "friendlies_excluded": True,
            "unsupported_excluded": True,
            "fresh_odds_required": True,
            "refresh_before_block": True,
            "reuse_immutable_freezes": True,
            "one_job_per_fixture": True,
        },
    }
    _write_json(art / "runtime.json", runtime)

    if not runtime["canonical_pipeline_ready"]:
        print("OWNER_FULL_DAY_DATA_BLOCKED")
        return 2

    discovery = discover_today_matches(target_date=today, timezone=TZ_NAME, scope="owner")
    all_matches = discovery.get("matches") or []
    team_country_cache: dict[int, str] = {}
    prod = connect(settings.sqlite_path)
    eval_conn = connect_eval_db()

    discovered_rows: list[dict] = []
    exclusions: list[dict] = []
    entering: list[dict] = []
    assemble_existing: list[dict] = []
    counters: Counter = Counter()

    try:
        for m in all_matches:
            fid = int(m["fixture_id"])
            comp_raw = m.get("competition_key") or m.get("competition")
            comp = normalize_competition_key(comp_raw) or str(comp_raw or "")
            lg = _league_meta(comp)
            status = str(m.get("status") or "NS").upper()
            ko = m.get("kickoff_utc") or m.get("kickoff")
            ko_dt = _parse_dt(ko)
            tier = m.get("validation_tier") or m.get("tier") or fixture_tier(comp)
            fx = prod.execute(
                "SELECT home_team_id, away_team_id, league_id, season, source FROM fixtures WHERE fixture_id=?",
                (fid,),
            ).fetchone()
            home_id = (fx["home_team_id"] if fx else None) or m.get("home_team_id")
            away_id = (fx["away_team_id"] if fx else None) or m.get("away_team_id")
            row = {
                "fixture_id": fid,
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_team_country": _team_country(client, home_id, team_country_cache),
                "away_team_country": _team_country(client, away_id, team_country_cache),
                "league": lg["league"],
                "competition": lg["competition_key"],
                "league_country": lg["league_country"],
                "kickoff_utc": ko,
                "kickoff_vienna": _vienna(ko),
                "fixture_status": status,
                "validation_tier": tier,
                "prediction_scope": "production" if tier == "A" else "owner_shadow",
                "provider_mapping": {
                    "provider": (fx["source"] if fx else None) or "api-football",
                    "league_id": fx["league_id"] if fx else None,
                    "season": fx["season"] if fx else m.get("season"),
                },
                "mapping_confidence": "HIGH" if home_id and away_id else "MEDIUM",
            }
            discovered_rows.append(row)
            counters["total_discovered"] += 1

            reason = None
            if comp in FRIENDLY or "friendly" in comp.lower():
                reason = "FRIENDLY"
                counters["friendlies_excluded"] += 1
            elif tier not in ("A", "B"):
                reason = "UNSUPPORTED"
                counters["unsupported_excluded"] += 1
            elif status in CANCELLED:
                reason = f"CANCELLED_OR_POSTPONED:{status}"
                counters["cancelled_excluded"] += 1
            elif status in FINISHED or status in STARTED or (ko_dt and ko_dt <= now_utc):
                # Already started/finished — may still assemble existing freeze
                existing_fr = _load_freeze(eval_conn, fid)
                pred_exists = prod.execute(
                    "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1", (fid,)
                ).fetchone()
                if existing_fr and pred_exists:
                    row["lifecycle"] = "POST_KICKOFF_HAS_FREEZE"
                    assemble_existing.append(row)
                    counters["assemble_existing_freeze"] += 1
                else:
                    reason = "BLOCKED_POST_KICKOFF_NO_FREEZE"
                    counters["post_kickoff_missed"] += 1
            elif status not in PREMATCH:
                reason = f"UNSUPPORTED_STATUS:{status}"
            else:
                existing_fr = _load_freeze(eval_conn, fid)
                pred_exists = prod.execute(
                    "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1", (fid,)
                ).fetchone()
                snap = get_snapshot(prod, fid)
                if existing_fr and pred_exists and snap:
                    row["lifecycle"] = "PREMATCH_REUSE_FREEZE"
                    assemble_existing.append(row)
                    counters["prematch_reuse_freeze"] += 1
                else:
                    row["lifecycle"] = "PREMATCH_NEEDS_PREDICTION"
                    entering.append(row)
                    counters["prematch_needs_prediction"] += 1

            if reason:
                exclusions.append({**row, "exclusion_reason": reason})
    finally:
        pass

    _write_json(
        art / "discovery.json",
        {
            "runtime": runtime,
            "discovery_audit": {
                k: discovery.get(k)
                for k in ("date", "timezone", "scope", "count", "tier_a_count", "tier_b_count", "broad_audit")
            },
            "counters": dict(counters),
            "all_discovered": discovered_rows,
            "entering_prediction": entering,
            "assemble_existing": assemble_existing,
            "exclusions": exclusions,
        },
    )

    job_dir = art / f"jobs_{run_id}"
    base_cfg = load_gpt_actions_config()
    cfg = GptActionsConfig(
        host=base_cfg.host,
        port=base_cfg.port,
        api_key=base_cfg.api_key,
        audit_log_path=str(art / "audit.jsonl"),
        job_store_dir=str(job_dir),
        max_jobs_retained=200,
        rate_limit_per_minute=base_cfg.rate_limit_per_minute,
        max_fixture_ids_per_job=base_cfg.max_fixture_ids_per_job,
        max_response_chars=base_cfg.max_response_chars,
        poll_after_seconds=base_cfg.poll_after_seconds,
    )
    store = JobStore(str(job_dir), max_retained=200)

    odds_rows: list[dict] = []
    jobs: list[dict] = []
    predictions: list[dict] = []
    freezes: list[dict] = []
    eval_manifest: list[dict] = []

    # --- Assemble existing freezes (no new jobs; no overwrite) ---
    for meta in assemble_existing:
        fid = int(meta["fixture_id"])
        pred = _extract(prod, fid)
        fr = _load_freeze(eval_conn, fid) or {}
        odds = _odds_blob(get_latest_valid_1x2_odds_snapshot(prod, fid, kickoff_utc=meta.get("kickoff_utc")))
        # Prefer frozen odds snapshot values when present
        if fr.get("odds_home"):
            odds = {
                **odds,
                "home": _f(fr.get("odds_home")),
                "draw": _f(fr.get("odds_draw")),
                "away": _f(fr.get("odds_away")),
                "bookmaker_count": fr.get("bookmaker_count") or odds.get("bookmaker_count"),
                "freshness_status": fr.get("odds_freshness_status") or fr.get("odds_freshness") or odds.get("freshness_status"),
                "complete": all(_f(fr.get(k)) and _f(fr.get(k)) > 1 for k in ("odds_home", "odds_draw", "odds_away")),
                "from_freeze": True,
            }
            odds["market_direction"] = _fav(odds.get("home"), odds.get("draw"), odds.get("away"))
        freeze_meta = {
            "capture_status": "reused_existing",
            "freeze_id": fr.get("prediction_id"),
            "content_hash": fr.get("content_hash"),
            "source_payload_hash": fr.get("source_payload_hash"),
            "frozen_at": fr.get("frozen_at"),
            "reused": True,
            "created": False,
            "immutable": bool(fr.get("immutable", True)),
        }
        ko_dt = _parse_dt(meta.get("kickoff_utc"))
        fr_dt = _parse_dt(str(fr.get("frozen_at") or ""))
        freeze_before = bool(ko_dt and fr_dt and fr_dt < ko_dt)
        shadow_meta = _run_l2f_true_forward_shadow(
            prod_conn=prod,
            fixture_id=fid,
            freeze_meta=freeze_meta,
            prediction_scope=str(meta.get("prediction_scope") or "owner_shadow"),
            settings=settings,
        )
        out = _assemble_prediction(
            meta,
            pred,
            odds,
            source=str(meta.get("lifecycle") or "assemble_existing"),
            eligibility="PREDICTION_ELIGIBLE" if pred.get("complete") else "MANUAL_REVIEW_REQUIRED",
            job_id=None,
            job_terminal="reused_existing",
            freeze_meta=freeze_meta,
            freeze_before_ko=freeze_before,
        )
        out["l2f_forward_shadow"] = shadow_meta
        predictions.append(out)
        freezes.append(
            {
                "fixture_id": fid,
                "match": f"{meta['home_team']} vs {meta['away_team']}",
                "freeze_status": "reused",
                "freeze_id": freeze_meta.get("freeze_id"),
                "freeze_timestamp": freeze_meta.get("frozen_at"),
                "freeze_hash": freeze_meta.get("content_hash"),
                "new_or_reused": "reused",
                "before_kickoff": freeze_before,
                "l2f_status": shadow_meta.get("status"),
                "l2f_cohort_type": shadow_meta.get("cohort_type"),
            }
        )
        if freeze_meta.get("freeze_id") and freeze_meta.get("content_hash"):
            eval_manifest.append(
                {
                    "fixture_id": fid,
                    "match": f"{meta['home_team']} vs {meta['away_team']}",
                    "kickoff_utc": meta.get("kickoff_utc"),
                    "kickoff_vienna": meta.get("kickoff_vienna"),
                    "prediction_scope": meta.get("prediction_scope"),
                    "validation_tier": meta.get("validation_tier"),
                    "freeze_id": freeze_meta.get("freeze_id"),
                    "freeze_hash": freeze_meta.get("content_hash"),
                    "evaluation_date": (date.fromisoformat(today) + timedelta(days=1)).isoformat(),
                    "policy": "immutable_prematch_freeze_only",
                    "do_not_regenerate_prediction": True,
                    "compare_fields": [
                        "confirmed_final_score",
                        "confirmed_regulation_1x2",
                        "actual_btts",
                        "actual_ou_2_5",
                        "wde_hit_miss",
                        "ft_marginal_hit_miss",
                        "btts_hit_miss",
                        "ou_hit_miss",
                        "ecse_top1_hit",
                        "ecse_top3_hit",
                        "ecse_top5_hit",
                        "actual_ecse_rank",
                    ],
                }
            )

    # --- Predict remaining prematch fixtures ---
    for meta in entering:
        fid = int(meta["fixture_id"])
        daily = _fixture_from_db(prod, fid) or DailyFixture(
            fixture_id=fid,
            provider_fixture_id=fid,
            competition_key=str(meta.get("competition") or ""),
            home_team=str(meta["home_team"]),
            away_team=str(meta["away_team"]),
            kickoff_utc=str(meta["kickoff_utc"]),
            status=str(meta["fixture_status"]),
            season=None,
        )
        forced = refresh_live_odds(daily, settings=settings)
        prod.close()
        prod = connect(settings.sqlite_path)
        gate = ensure_fresh_odds_before_prediction(
            prod,
            {"fixture_id": fid, "kickoff_utc": meta["kickoff_utc"], "status": meta["fixture_status"]},
            daily,
            settings=settings,
            refresh_if_needed=True,
        )
        odds = _odds_blob(get_latest_valid_1x2_odds_snapshot(prod, fid, kickoff_utc=meta["kickoff_utc"]))
        fresh = bool(gate.get("allowed")) and _fresh_ok(odds.get("freshness_status") or (gate.get("freshness") or {}))

        eligibility = "PREDICTION_ELIGIBLE"
        if not odds.get("complete"):
            eligibility = "BLOCKED_INCOMPLETE_ODDS" if odds.get("home") or odds.get("away") else "BLOCKED_MISSING_ODDS"
        elif not fresh:
            eligibility = "BLOCKED_STALE_ODDS"
        elif not mcp_runtime.model_status().get("canonical_pipeline_ready"):
            eligibility = "BLOCKED_WDE_DEPENDENCY"

        odds_rows.append(
            {
                **meta,
                "odds": odds,
                "refresh_attempted": True,
                "refresh_success": bool(forced.get("success")),
                "gate_allowed": gate.get("allowed"),
                "eligibility": eligibility,
            }
        )

        if eligibility != "PREDICTION_ELIGIBLE":
            predictions.append(
                {
                    **meta,
                    "eligibility": eligibility,
                    "source": "blocked_odds",
                    "odds": odds,
                    "prediction_complete": False,
                    "main_risk": eligibility,
                }
            )
            continue

        job_id = str(uuid.uuid4())
        record = {
            "job_id": job_id,
            "status": "queued",
            "run_id": run_id,
            "created_at": _utc_now(),
            "request": {
                "date": today,
                "timezone": TZ_NAME,
                "scope": "owner",
                "prediction_scope": meta["prediction_scope"],
                "fixture_ids": [fid],
                "refresh_if_stale": True,
                "include_all_predictions": True,
            },
        }
        store._path(job_id).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        enqueue_prediction_job(job_id, store=store, config=cfg)
        poll = _poll(job_id, store, cfg)
        final = poll.get("final") or store.get(job_id) or {}
        terminal = str(final.get("status") or ("timeout" if poll.get("timed_out") else "unknown"))
        jobs.append(
            {
                "fixture_id": fid,
                "job_id": job_id,
                "status": terminal,
                "timed_out": poll.get("timed_out"),
                "polled_same_job_id": True,
                "one_job_per_fixture": True,
                "prediction_scope": meta["prediction_scope"],
            }
        )

        prod.close()
        prod = connect(settings.sqlite_path)
        pred = _extract(prod, fid)
        freeze_meta: dict[str, Any] = {}
        freeze_before_ko = False
        try:
            snap_id = (pred.get("ecse") or {}).get("snapshot_id")
            snap_i = int(snap_id) if snap_id is not None else None
            bridge = maybe_capture_after_prediction_persistence(
                fid,
                prod_conn=prod,
                bridge_context=ForwardEvalBridgeContext(
                    prediction_scope=str(meta["prediction_scope"]),
                    validation_tier=str(meta.get("validation_tier")),
                    public_visible=False if meta.get("validation_tier") == "B" else True,
                    source_job_id=job_id,
                    bridge_origin="gpt_actions",
                    worldcup_stored_prediction_id=fid,
                    ecse_snapshot_id=snap_i,
                ),
                quality_status="OK" if pred.get("complete") else "PARTIAL",
                ecse_snapshot_id=snap_i,
            )
            freeze_meta = bridge.to_metadata_block() if hasattr(bridge, "to_metadata_block") else {}
            # Enrich timestamps for true-forward integrity (bridge block may omit frozen_at).
            fr_row = _load_freeze(eval_conn, fid) or {}
            if not freeze_meta.get("frozen_at"):
                freeze_meta["frozen_at"] = fr_row.get("frozen_at")
            if not freeze_meta.get("prediction_scope"):
                freeze_meta["prediction_scope"] = meta.get("prediction_scope")
            frozen_at = freeze_meta.get("frozen_at") or freeze_meta.get("captured_at") or _utc_now()
            ko_dt = _parse_dt(meta["kickoff_utc"])
            fr_dt = _parse_dt(str(frozen_at))
            freeze_before_ko = bool(ko_dt and fr_dt and fr_dt < ko_dt)
        except Exception as exc:
            freeze_meta = {"status": "capture_error", "error": str(exc)[:200]}
            freeze_before_ko = False

        shadow_meta = _run_l2f_true_forward_shadow(
            prod_conn=prod,
            fixture_id=fid,
            freeze_meta=freeze_meta,
            prediction_scope=str(meta.get("prediction_scope") or "owner_shadow"),
            settings=settings,
        )

        out = _assemble_prediction(
            meta,
            pred,
            odds,
            source="new_prediction_job",
            eligibility=eligibility,
            job_id=job_id,
            job_terminal=terminal,
            freeze_meta=freeze_meta,
            freeze_before_ko=freeze_before_ko,
        )
        out["refresh_status"] = "success" if forced.get("success") else "failed_or_cached"
        out["l2f_forward_shadow"] = shadow_meta
        predictions.append(out)
        freezes.append(
            {
                "fixture_id": fid,
                "match": f"{meta['home_team']} vs {meta['away_team']}",
                "freeze_status": freeze_meta.get("capture_status") or freeze_meta.get("status") or "unknown",
                "freeze_id": freeze_meta.get("freeze_id") or freeze_meta.get("prediction_id"),
                "freeze_timestamp": freeze_meta.get("frozen_at") or freeze_meta.get("captured_at"),
                "freeze_hash": freeze_meta.get("content_hash") or freeze_meta.get("source_payload_hash"),
                "new_or_reused": "reused" if freeze_meta.get("reused") else ("new" if freeze_meta.get("created") else "unknown"),
                "l2f_status": shadow_meta.get("status"),
                "l2f_cohort_type": shadow_meta.get("cohort_type"),
                "before_kickoff": freeze_before_ko,
            }
        )
        if (freeze_meta.get("freeze_id") or freeze_meta.get("prediction_id")) and (
            freeze_meta.get("content_hash") or freeze_meta.get("source_payload_hash")
        ):
            eval_manifest.append(
                {
                    "fixture_id": fid,
                    "match": f"{meta['home_team']} vs {meta['away_team']}",
                    "kickoff_utc": meta["kickoff_utc"],
                    "kickoff_vienna": meta["kickoff_vienna"],
                    "prediction_scope": meta["prediction_scope"],
                    "validation_tier": meta.get("validation_tier"),
                    "freeze_id": freeze_meta.get("freeze_id") or freeze_meta.get("prediction_id"),
                    "freeze_hash": freeze_meta.get("content_hash") or freeze_meta.get("source_payload_hash"),
                    "evaluation_date": (date.fromisoformat(today) + timedelta(days=1)).isoformat(),
                    "policy": "immutable_prematch_freeze_only",
                    "do_not_regenerate_prediction": True,
                }
            )

    rankings = _build_rankings(predictions)
    complete = [p for p in predictions if p.get("prediction_complete")]
    blocked = [p for p in predictions if not p.get("prediction_complete")] + exclusions

    # Sort complete by kickoff for report
    complete_sorted = sorted(complete, key=lambda p: str(p.get("kickoff_utc") or ""))

    _write_json(art / "odds_eligibility.json", {"fixtures": odds_rows})
    _write_json(art / "prediction_jobs.json", {"jobs": jobs})
    _write_json(art / "full_predictions.json", {"run_id": run_id, "predictions": predictions})
    _write_json(art / "rankings.json", rankings)
    _write_json(art / "freeze_manifest.json", {"freezes": freezes})
    _write_json(
        art / "evaluation_manifest.json",
        {
            "evaluation_date": (date.fromisoformat(today) + timedelta(days=1)).isoformat(),
            "source_date": today,
            "policy": "immutable_prematch_freeze_only",
            "do_not_regenerate": True,
            "fixtures": eval_manifest,
        },
    )

    # Rankings CSV (safest as primary table)
    with (art / "rankings_safest.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "fixture_id",
                "match",
                "league",
                "kickoff_vienna",
                "wde",
                "confidence",
                "consensus",
                "data_quality",
                "top1",
                "top5_mass",
                "total_lambda",
                "btts",
                "ou25",
                "no_bet",
            ],
        )
        w.writeheader()
        for r in rankings.get("F_safest_matches") or []:
            w.writerow(r)

    # Reports
    def _rank_section(title: str, rows: list[dict]) -> list[str]:
        lines = [f"### {title}", ""]
        if not rows:
            lines.append("_None_")
            lines.append("")
            return lines
        lines.append("| # | Kickoff | Match | League | WDE | Conf | Top1 | Notes |")
        lines.append("|---:|---|---|---|---|---:|---|---|")
        for r in rows[:25]:
            notes = []
            if r.get("btts"):
                notes.append(f"BTTS={r['btts']}")
            if r.get("ou25"):
                notes.append(f"OU={r['ou25']}")
            if r.get("top5_mass") is not None:
                notes.append(f"T5={r['top5_mass']}")
            lines.append(
                f"| {r.get('rank')} | {r.get('kickoff_vienna')} | {r.get('match')} | {r.get('league')} | "
                f"{r.get('wde')} | {r.get('confidence')} | {r.get('top1')} | {'; '.join(notes)} |"
            )
        lines.append("")
        return lines

    en = [
        f"# Full-Day Owner Report — {today} (Europe/Vienna)",
        "",
        f"**Mode:** OWNER_FULL_DAY_PREDICTION (no kickoff-hour filter)",
        f"**Vienna now:** {runtime['current_vienna']}",
        f"**Local / origin/main:** `{local_sha[:12]}` / `{main_sha[:12]}`",
        f"**Discovered supported:** {counters['total_discovered']} · "
        f"**Predicted complete:** {len(complete)} · "
        f"**New jobs:** {len(jobs)} · "
        f"**Reused freezes:** {counters.get('assemble_existing_freeze', 0) + counters.get('prematch_reuse_freeze', 0)} · "
        f"**Missed post-KO:** {counters.get('post_kickoff_missed', 0)}",
        "",
        "## Policy",
        "",
        "- Friendlies / unsupported / cancelled excluded",
        "- Fresh odds + refresh-before-block for new predictions",
        "- Immutable freeze reuse (never overwrite)",
        "- Multi-category rankings (not a 2–3 pick shortlist)",
        "",
        "## Multi-category rankings",
        "",
    ]
    en += _rank_section("A — Best End Result (1X2)", rankings["A_best_end_result_1x2"])
    en += _rank_section("B — Best Exact Score", rankings["B_best_exact_score"])
    en += _rank_section("C — Best Under", rankings["C_best_under"])
    en += _rank_section("D — Best Over", rankings["D_best_over"])
    en += _rank_section("E — Best BTTS", rankings["E_best_btts"])
    en += _rank_section("F — Safest Matches", rankings["F_safest_matches"])
    en += _rank_section("G — Watchlist", rankings["G_watchlist"])
    en += _rank_section("H — No Bet", rankings["H_no_bet"])

    en += ["## Every predicted fixture", ""]
    for p in complete_sorted:
        wde = p.get("wde") or {}
        ecse = p.get("ecse") or {}
        fr = p.get("freeze") or {}
        en += [
            f"### {p.get('home_team')} vs {p.get('away_team')}",
            f"- Fixture ID: `{p.get('fixture_id')}`",
            f"- League: {p.get('league')} ({p.get('league_country')})",
            f"- Teams: {p.get('home_team')} ({p.get('home_team_country')}) vs {p.get('away_team')} ({p.get('away_team_country')})",
            f"- Kickoff Vienna: {p.get('kickoff_vienna')}",
            f"- Tier / scope: {p.get('validation_tier')} / {p.get('prediction_scope')}",
            f"- Source: {p.get('source')}",
            f"- Odds H/D/A: {(p.get('odds') or {}).get('home')} / {(p.get('odds') or {}).get('draw')} / {(p.get('odds') or {}).get('away')}",
            f"- WDE Decision: **{wde.get('decision')}** · FT Marginal: {wde.get('ft_marginal')}",
            f"- H/D/A: {wde.get('home_probability')} / {wde.get('draw_probability')} / {wde.get('away_probability')}",
            f"- Model Confidence: **{wde.get('confidence')}%** ({wde.get('confidence_class')})",
            f"- BTTS: {(p.get('btts') or {}).get('prediction')} · O/U: {(p.get('ou25') or {}).get('preferred_side')}",
            f"- ECSE Top1–Top5: {_cell(ecse.get('top1'))} | {_cell(ecse.get('top2'))} | {_cell(ecse.get('top3'))} | {_cell(ecse.get('top4'))} | {_cell(ecse.get('top5'))}",
            f"- Top5 mass / entropy / λ: {ecse.get('top5_mass')} / {ecse.get('entropy')} / {ecse.get('total_lambda')}",
            f"- Consensus: **{p.get('consensus')}** · DQ: {p.get('data_quality')} · Risk: {p.get('main_risk')}",
            f"- Freeze: {fr.get('freeze_id') or fr.get('capture_status')} hash={fr.get('content_hash')} before_KO={p.get('freeze_before_kickoff')}",
            "",
        ]

    if exclusions:
        en += ["## Exclusions / missed", ""]
        for e in exclusions:
            en.append(
                f"- `{e.get('fixture_id')}` {e.get('home_team')} vs {e.get('away_team')} — {e.get('exclusion_reason')} ({e.get('kickoff_vienna')})"
            )
        en.append("")

    en += [
        f"Evaluation manifest: `artifacts/daily_pipeline/{today}/full_day/evaluation_manifest.json`",
        "",
        "```text",
        "OWNER_FULL_DAY_PREDICTION_MODE_READY",
        "```",
        "",
    ]

    fa = [
        f"# گزارش کامل روزانه مالک — {today} (وین)",
        "",
        f"**حالت:** پیش‌بینی تمام‌روز (بدون فیلتر ساعت دلخواه)",
        f"**زمان وین:** {runtime['current_vienna']}",
        f"**کشف‌شده:** {counters['total_discovered']} · **کامل:** {len(complete)} · **جاب جدید:** {len(jobs)} · "
        f"**فریز بازاستفاده:** {counters.get('assemble_existing_freeze', 0) + counters.get('prematch_reuse_freeze', 0)}",
        "",
        "## رتبه‌بندی چند‌دسته",
        "",
    ]
    for key, title in [
        ("A_best_end_result_1x2", "A — بهترین نتیجه نهایی"),
        ("B_best_exact_score", "B — بهترین Exact Score"),
        ("C_best_under", "C — بهترین Under"),
        ("D_best_over", "D — بهترین Over"),
        ("E_best_btts", "E — بهترین BTTS"),
        ("F_safest_matches", "F — امن‌ترین‌ها"),
        ("G_watchlist", "G — واچ‌لیست"),
        ("H_no_bet", "H — No Bet"),
    ]:
        fa += _rank_section(title, rankings[key])

    fa += ["## همه بازی‌های پیش‌بینی‌شده", ""]
    for p in complete_sorted:
        wde = p.get("wde") or {}
        ecse = p.get("ecse") or {}
        fa += [
            f"### {p.get('home_team')} vs {p.get('away_team')}",
            f"- شناسه: `{p.get('fixture_id')}` · لیگ: {p.get('league')} ({p.get('league_country')})",
            f"- کشورها: {p.get('home_team_country')} / {p.get('away_team_country')}",
            f"- kickoff وین: {p.get('kickoff_vienna')}",
            f"- WDE: **{wde.get('decision')}** · H/D/A: {wde.get('home_probability')}/{wde.get('draw_probability')}/{wde.get('away_probability')}",
            f"- اطمینان: **{wde.get('confidence')}%** ({wde.get('confidence_class')})",
            f"- BTTS: {(p.get('btts') or {}).get('prediction')} · O/U: {(p.get('ou25') or {}).get('preferred_side')}",
            f"- Top1–Top5: {_cell(ecse.get('top1'))} | {_cell(ecse.get('top2'))} | {_cell(ecse.get('top3'))} | {_cell(ecse.get('top4'))} | {_cell(ecse.get('top5'))}",
            f"- اجماع: {p.get('consensus')} · کیفیت: {p.get('data_quality')} · ریسک: {p.get('main_risk')}",
            f"- فریز: {(p.get('freeze') or {}).get('freeze_id')} · قبل از kickoff: {p.get('freeze_before_kickoff')}",
            "",
        ]

    if exclusions:
        fa += ["## حذف‌شده / از دست‌رفته", ""]
        for e in exclusions:
            fa.append(f"- `{e.get('fixture_id')}` {e.get('home_team')} vs {e.get('away_team')} — {e.get('exclusion_reason')}")
        fa.append("")

    fa += [
        "",
        "```text",
        "OWNER_FULL_DAY_PREDICTION_MODE_READY",
        "```",
        "",
    ]

    report_en = REPORT_DIR / f"{today}_FULL_DAY_OWNER_REPORT.md"
    report_fa = REPORT_DIR / f"{today}_FULL_DAY_OWNER_REPORT_FA.md"
    report_en.write_text("\n".join(en), encoding="utf-8")
    report_fa.write_text("\n".join(fa), encoding="utf-8")

    summary = {
        "final_status": "OWNER_FULL_DAY_PREDICTION_MODE_READY",
        "target_date": today,
        "counters": dict(counters),
        "complete_predictions": len(complete),
        "new_jobs": len(jobs),
        "freezes": len(freezes),
        "eval_manifest": len(eval_manifest),
        "missed_post_kickoff": counters.get("post_kickoff_missed", 0),
        "reports": [str(report_en.relative_to(ROOT)), str(report_fa.relative_to(ROOT))],
        "rankings_counts": {k: len(v) for k, v in rankings.items()},
    }
    _write_json(art / "run_summary.json", summary)

    prod.close()
    eval_conn.close()

    print("=" * 72)
    print("OWNER FULL-DAY PREDICTION & FREEZE")
    print("=" * 72)
    print(f"Vienna now: {runtime['current_vienna']}")
    print(f"Date: {today} · kickoff_hour_filter: NONE")
    print(f"Discovered supported: {counters['total_discovered']}")
    print(f"Prematch new jobs: {len(entering)} queued/attempted → jobs={len(jobs)}")
    print(f"Assembled existing freezes: {len(assemble_existing)}")
    print(f"Complete predictions in report: {len(complete)}")
    print(f"Missed post-KO (no freeze): {counters.get('post_kickoff_missed', 0)}")
    print("Rankings:")
    for k, v in rankings.items():
        print(f"  {k}: {len(v)}")
    print(f"Evaluation: artifacts/daily_pipeline/{today}/full_day/evaluation_manifest.json")
    print(f"Reports: {report_en} | {report_fa}")
    # Additive Challenger shadow hook — must never change canonical status/output.
    try:
        from worldcup_predictor.challenger.prediction_store import ensure_challenger_schema
        from worldcup_predictor.challenger.tsbp.forward_hook import run_tsbp_shadow_batch_safe
        from worldcup_predictor.challenger.tsbp.registration import register_tsbp_and_pause_gbgm

        ch_conn = connect(settings.sqlite_path)
        ensure_challenger_schema(ch_conn)
        try:
            register_tsbp_and_pause_gbgm()
        except Exception:
            pass
        tsbp_metas = []
        for p in complete:
            fid = int(p.get("fixture_id") or 0)
            if not fid:
                continue
            tsbp_metas.append(
                {
                    "fixture_id": fid,
                    "prediction_scope": p.get("prediction_scope") or "owner_full_day",
                    "validation_tier": p.get("validation_tier"),
                    "freeze_id": p.get("freeze_id"),
                    "linked_canonical_freeze_id": str(p.get("freeze_id") or ""),
                    "canonical_summary": {
                        "freeze_hash": p.get("freeze_hash"),
                        "wde_decision": p.get("wde_decision") or p.get("decision_1x2"),
                        "btts": p.get("btts"),
                        "ou25": p.get("ou25") or p.get("over_under_2_5"),
                        "ecse_top1": p.get("ecse_top1"),
                        "ecse_top5": p.get("ecse_top5") or p.get("top5"),
                        "hda": p.get("hda"),
                        "feature_cutoff": p.get("kickoff_utc"),
                        "prediction_time": p.get("kickoff_utc"),
                        "odds_timestamp": (p.get("odds") or {}).get("fetched_at_utc") if isinstance(p.get("odds"), dict) else None,
                        "require_strict_snapshot_parity": False,
                    },
                }
            )
        tsbp_out = run_tsbp_shadow_batch_safe(ch_conn, tsbp_metas)
        summary["challenger_shadow_hook"] = "tsbp_non_blocking"
        summary["tsbp_shadow"] = {
            "model_id": "TSBP-1",
            "n_attempted": tsbp_out.get("n"),
            "failures": tsbp_out.get("failures"),
            "domain_rejects": tsbp_out.get("domain_rejects"),
            "forward_active": tsbp_out.get("forward_active"),
            "reason": tsbp_out.get("reason"),
            "canonical_status_unchanged": True,
        }
        _write_json(art / "tsbp_shadow_batch.json", {k: v for k, v in tsbp_out.items() if k != "results"})
        ch_conn.close()
    except Exception as exc:
        summary["challenger_shadow_hook"] = f"skipped:{type(exc).__name__}"
        summary["tsbp_shadow"] = {"error": type(exc).__name__, "canonical_unaffected": True}
    _write_json(art / "run_summary.json", summary)
    print("OWNER_FULL_DAY_PREDICTION_MODE_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
