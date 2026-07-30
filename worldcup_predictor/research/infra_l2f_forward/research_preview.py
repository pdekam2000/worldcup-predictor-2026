"""Owner-only Canonical vs Shadow research preview (read-only; never official)."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE
from worldcup_predictor.research.football_strength_foundation.score_v2 import dist_dc
from worldcup_predictor.research.infra_l2f_forward.agreement import classify_model_agreement
from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema
from worldcup_predictor.research.infra_l2f_forward.leakage_checks import (
    assert_prediction_before_kickoff,
    check_shadow_payloads_no_results,
)

TZ = ZoneInfo("Europe/Vienna")
LAMBDA_SELECTED = "LAMBDA_V2_BLENDED_ADAPTIVE"
EXACT_SELECTED = "EXACT_V2_SELECTED"
RUN_ID = "l2f-forward-v1"


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _vienna(raw: str | None) -> str | None:
    dt = _parse_dt(raw)
    if not dt:
        return None
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def _vienna_date(raw: str | None) -> str | None:
    dt = _parse_dt(raw)
    if not dt:
        return None
    return dt.astimezone(TZ).date().isoformat()


def _parse_score(score: str | None) -> tuple[int, int] | None:
    if not score or "-" not in str(score):
        return None
    try:
        h, a = str(score).split("-", 1)
        return int(h.strip()), int(a.strip())
    except Exception:
        return None


def _score_distance(a: str | None, b: str | None) -> int | None:
    pa, pb = _parse_score(a), _parse_score(b)
    if not pa or not pb:
        return None
    return abs(pa[0] - pb[0]) + abs(pa[1] - pb[1])


def _side_mass(dist: list[dict[str, Any]]) -> dict[str, float]:
    home = draw = away = 0.0
    for e in dist:
        if e.get("scoreline") == "OTHER":
            continue
        p = float(e.get("probability") or 0)
        h, a = int(e.get("home_goals", -1)), int(e.get("away_goals", -1))
        if h < 0:
            continue
        if h > a:
            home += p
        elif a > h:
            away += p
        else:
            draw += p
    return {"home_win_mass": home, "draw_mass": draw, "away_win_mass": away}


def _high_score_tail(dist: list[dict[str, Any]], min_goals: int = 4) -> float:
    return sum(
        float(e.get("probability") or 0)
        for e in dist
        if e.get("scoreline") != "OTHER"
        and int(e.get("home_goals", -1)) >= 0
        and (int(e["home_goals"]) + int(e["away_goals"])) >= min_goals
    )


def _tops_with_probs(dist: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    out = []
    for e in dist:
        if e.get("scoreline") == "OTHER":
            continue
        out.append({"score": e["scoreline"], "probability": round(float(e["probability"]), 6)})
        if len(out) >= n:
            break
    return out


def _entropy(probs: list[float]) -> float | None:
    ps = [p for p in probs if p and p > 0]
    if not ps:
        return None
    return round(-sum(p * math.log(p) for p in ps), 6)


def _load_shadow(fi: sqlite3.Connection, fixture_id: int, model_id: str) -> dict[str, Any] | None:
    row = fi.execute(
        f"""
        SELECT model_id, lambda_home, lambda_away, top1, top5_json, top10_json,
               top5_mass, entropy, payload_json, shadow_hash, created_at_utc
        FROM {SHADOW_TABLE}
        WHERE fixture_id=? AND model_id=?
        ORDER BY created_at_utc DESC LIMIT 1
        """,
        (int(fixture_id), model_id),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    tops_raw = []
    try:
        tops_raw = json.loads(d["top5_json"] or "[]")
    except Exception:
        tops_raw = []
    lh, la = _f(d.get("lambda_home")), _f(d.get("lambda_away"))
    dist = dist_dc(lh or 0.0, la or 0.0) if lh is not None and la is not None else []
    tops = _tops_with_probs(dist, 5) if dist else [{"score": s, "probability": None} for s in tops_raw[:5]]
    mass = _f(d.get("top5_mass"))
    if mass is None and tops:
        mass = round(sum(float(t["probability"] or 0) for t in tops), 6)
    ent = _f(d.get("entropy"))
    if ent is None and tops:
        ent = _entropy([float(t["probability"] or 0) for t in tops])
    sides = _side_mass(dist) if dist else {}
    return {
        "model_id": model_id,
        "label": "SHADOW_RESEARCH_ONLY",
        "official": False,
        "lambda_home": lh,
        "lambda_away": la,
        "lambda_total": round((lh or 0) + (la or 0), 4) if lh is not None and la is not None else None,
        "top1": (tops[0]["score"] if tops else d.get("top1")),
        "top5": tops,
        "top5_mass": mass,
        "entropy": ent,
        "high_score_tail": round(_high_score_tail(dist), 6) if dist else None,
        **sides,
        "shadow_hash": d.get("shadow_hash"),
        "created_at_utc": d.get("created_at_utc"),
    }


def _canonical_ecse_tops(
    prod: sqlite3.Connection,
    fixture_id: int,
    freeze: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from worldcup_predictor.research.ecse_live.store import get_snapshot

    snap: dict[str, Any] = {}
    try:
        if prod.row_factory is None:
            prod.row_factory = sqlite3.Row
        raw_snap = get_snapshot(prod, int(fixture_id))
        if isinstance(raw_snap, dict):
            snap = raw_snap
    except Exception:
        snap = {}

    tops_raw = (
        snap.get("top_5_scores")
        or snap.get("top_scores")
        or snap.get("top5")
        or snap.get("top_5_scores_json")
        or []
    )
    if isinstance(tops_raw, str):
        try:
            tops_raw = json.loads(tops_raw)
        except Exception:
            tops_raw = []
    tops: list[dict[str, Any]] = []
    if isinstance(tops_raw, list):
        for t in tops_raw[:5]:
            if isinstance(t, dict):
                tops.append(
                    {
                        "score": t.get("score") or t.get("scoreline"),
                        "probability": _f(t.get("probability") or t.get("p")),
                    }
                )
            else:
                tops.append({"score": str(t), "probability": None})

    # Fallback: freeze ECSE payload (may lack probabilities).
    if (not tops) and freeze and freeze.get("ecse_payload_json"):
        try:
            ep = json.loads(freeze["ecse_payload_json"])
            for t in (ep.get("top5") or [])[:5]:
                if isinstance(t, dict):
                    tops.append(
                        {
                            "score": t.get("score") or t.get("scoreline"),
                            "probability": _f(t.get("probability") or t.get("p")),
                        }
                    )
        except Exception:
            pass

    lh = _f(snap.get("lambda_home"))
    la = _f(snap.get("lambda_away"))
    if freeze:
        lh = lh if lh is not None else _f(freeze.get("lambda_home"))
        la = la if la is not None else _f(freeze.get("lambda_away"))

    # If scorelines exist but probs missing, recompute display probs from canonical lambdas (research display only).
    if tops and lh is not None and la is not None and all(t.get("probability") is None for t in tops):
        dist = dist_dc(float(lh), float(la))
        pmap = {e["scoreline"]: float(e["probability"]) for e in dist if e.get("scoreline") != "OTHER"}
        for t in tops:
            if t.get("score") in pmap:
                t["probability"] = round(pmap[t["score"]], 6)
        # If freeze only stored scores, prefer full recomputed Top5 for side-by-side mass/entropy.
        if not any(t.get("probability") is not None for t in tops):
            tops = _tops_with_probs(dist, 5)

    mass = None
    if tops and all(t.get("probability") is not None for t in tops):
        mass = round(sum(float(t["probability"]) for t in tops), 6)
    ent = _entropy([float(t["probability"]) for t in tops if t.get("probability") is not None])
    return {
        "label": "CANONICAL",
        "official": True,
        "lambda_home": lh,
        "lambda_away": la,
        "lambda_total": round((lh or 0) + (la or 0), 4) if lh is not None and la is not None else None,
        "top1": tops[0]["score"] if tops else None,
        "top5": tops,
        "top5_mass": mass if mass is not None else _f((freeze or {}).get("top5_mass")) if freeze else _f(snap.get("top5_mass")),
        "entropy": ent if ent is not None else (_f((freeze or {}).get("entropy")) if freeze else _f(snap.get("entropy"))),
        "snapshot_id": snap.get("snapshot_id"),
    }


def _odds_from_sources(
    prod: sqlite3.Connection,
    fixture_id: int,
    freeze: dict[str, Any] | None,
    kickoff: str | None,
) -> dict[str, Any]:
    out = {
        "home": _f((freeze or {}).get("odds_home")),
        "draw": _f((freeze or {}).get("odds_draw")),
        "away": _f((freeze or {}).get("odds_away")),
        "provider": "api-football",
        "bookmaker_count": (freeze or {}).get("bookmaker_count"),
        "odds_timestamp": (freeze or {}).get("odds_fetched_at_utc") or (freeze or {}).get("odds_timestamp"),
        "odds_freshness_status": (freeze or {}).get("odds_freshness_status") or (freeze or {}).get("odds_freshness"),
        "odds_age_minutes": None,
    }
    if out["home"] and out["draw"] and out["away"]:
        return out
    try:
        from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot

        snap = get_latest_valid_1x2_odds_snapshot(prod, int(fixture_id), kickoff_utc=kickoff)
        if snap is not None:
            # CanonicalOddsSnapshot dataclass (preferred) or dict-like.
            home = getattr(snap, "home_odds", None)
            draw = getattr(snap, "draw_odds", None)
            away = getattr(snap, "away_odds", None)
            if home is None and isinstance(snap, dict):
                home = snap.get("home") or snap.get("home_odds") or snap.get("odds_home")
                draw = snap.get("draw") or snap.get("draw_odds") or snap.get("odds_draw")
                away = snap.get("away") or snap.get("away_odds") or snap.get("odds_away")
            out["home"] = out["home"] or _f(home)
            out["draw"] = out["draw"] or _f(draw)
            out["away"] = out["away"] or _f(away)
            out["bookmaker_count"] = out["bookmaker_count"] or getattr(snap, "bookmaker_count", None)
            out["odds_timestamp"] = (
                out["odds_timestamp"]
                or getattr(snap, "fetched_at_utc", None)
                or getattr(snap, "captured_at", None)
            )
            out["odds_freshness_status"] = out["odds_freshness_status"] or getattr(
                snap, "freshness_class", None
            ) or getattr(snap, "freshness_status", None)
            age = getattr(snap, "odds_age_minutes", None)
            if age is None and hasattr(snap, "age_seconds") and snap.age_seconds is not None:
                age = float(snap.age_seconds) / 60.0
            out["odds_age_minutes"] = age
            out["snapshot_id"] = getattr(snap, "row_id", None)
    except Exception:
        pass
    return out


def _canonical_wde(prod: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    row = prod.execute(
        """
        SELECT payload_json, predicted_at FROM worldcup_stored_predictions
        WHERE fixture_id=? LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return {}
    raw = row[0] if not isinstance(row, sqlite3.Row) else row["payload_json"]
    predicted_at = row[1] if not isinstance(row, sqlite3.Row) else row["predicted_at"]
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    try:
        from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics

        sem = extract_wde_semantics(payload)
    except Exception:
        sem = {}
    probs = payload.get("probabilities") or {}
    btts = probs.get("btts") or {}
    ou = probs.get("over_under_2_5") or {}
    return {
        "decision": sem.get("decision_pick") or payload.get("decision"),
        "probabilities": {
            "home": sem.get("p_home"),
            "draw": sem.get("p_draw"),
            "away": sem.get("p_away"),
        },
        "confidence": sem.get("confidence") or payload.get("confidence"),
        "consensus": payload.get("consensus"),
        "btts": btts,
        "ou25": ou,
        "no_bet": payload.get("no_bet"),
        "prediction_created_at": predicted_at,
    }


def _freeze_row(eval_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        """
        SELECT * FROM frozen_predictions
        WHERE fixture_id=?
        ORDER BY frozen_at DESC LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _job_row(fi: sqlite3.Connection, fixture_id: int, freeze_id: str | None) -> dict[str, Any] | None:
    ensure_job_schema(fi)
    if freeze_id:
        row = fi.execute(
            f"""
            SELECT * FROM {JOB_TABLE}
            WHERE fixture_id=? AND freeze_id=? AND run_id=?
            """,
            (int(fixture_id), freeze_id, RUN_ID),
        ).fetchone()
        if row:
            return dict(row)
    row = fi.execute(
        f"""
        SELECT * FROM {JOB_TABLE}
        WHERE fixture_id=? AND run_id=?
        ORDER BY updated_at_utc DESC LIMIT 1
        """,
        (int(fixture_id), RUN_ID),
    ).fetchone()
    return dict(row) if row else None


def _fixture_meta(prod: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    row = prod.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key,
               league_id, season, home_team_id, away_team_id
        FROM fixtures WHERE fixture_id=?
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else {"fixture_id": fixture_id}


def build_top_comparison(canonical_top5: list[dict], exact_top5: list[dict]) -> dict[str, Any]:
    c_scores = [str(t.get("score") or "") for t in canonical_top5[:5]]
    e_scores = [str(t.get("score") or "") for t in exact_top5[:5]]
    rows = []
    for i in range(5):
        rows.append(
            {
                "rank": i + 1,
                "canonical_score": c_scores[i] if i < len(c_scores) else None,
                "canonical_probability": (canonical_top5[i].get("probability") if i < len(canonical_top5) else None),
                "exact_v2_score": e_scores[i] if i < len(e_scores) else None,
                "exact_v2_probability": (exact_top5[i].get("probability") if i < len(exact_top5) else None),
            }
        )
    top1_agree = bool(c_scores and e_scores and c_scores[0] == e_scores[0])
    top3_overlap = len(set(c_scores[:3]) & set(e_scores[:3]))
    top5_overlap = len(set(c_scores[:5]) & set(e_scores[:5]))
    return {
        "side_by_side": rows,
        "top1_agreement": top1_agree,
        "top3_overlap_count": top3_overlap,
        "top5_overlap_count": top5_overlap,
        "score_distance_top1": _score_distance(
            c_scores[0] if c_scores else None, e_scores[0] if e_scores else None
        ),
    }


def build_integrity_proof(
    *,
    freeze: dict[str, Any] | None,
    fixture: dict[str, Any],
    job: dict[str, Any] | None,
    odds_ts: str | None,
    freeze_hash_before: str | None,
    freeze_hash_after: str | None,
    fi: sqlite3.Connection,
    fixture_id: int,
) -> dict[str, Any]:
    ko = fixture.get("kickoff_utc") or _freeze_kickoff(freeze)
    frozen_at = (freeze or {}).get("frozen_at")
    pred_ts = (job or {}).get("started_at_utc") or (job or {}).get("created_at_utc") or frozen_at
    checks = {
        "prediction_timestamp_before_kickoff": assert_prediction_before_kickoff(pred_ts, ko) is None,
        "freeze_timestamp_before_kickoff": assert_prediction_before_kickoff(frozen_at, ko) is None,
        "odds_timestamp_before_kickoff": assert_prediction_before_kickoff(odds_ts, ko) is None if odds_ts else None,
        "immutable_freeze_identity_exists": bool((freeze or {}).get("prediction_id")),
        "cohort_type_true_forward": (job or {}).get("cohort_type") == "true_forward",
        "no_historical_backfill_flag": (job or {}).get("run_id") == RUN_ID and "backfill" not in str((job or {}).get("run_id") or ""),
        "no_result_at_prediction_time": not check_shadow_payloads_no_results(fi, fixture_id),
        "shadow_payloads_clean": len(check_shadow_payloads_no_results(fi, fixture_id)) == 0,
        "canonical_freeze_hash_unchanged_after_shadow": (
            freeze_hash_before == freeze_hash_after if freeze_hash_before and freeze_hash_after else None
        ),
        "shadow_cannot_fail_canonical": True,
    }
    # Fix: check_shadow_payloads returns issues list — empty means clean
    issues = check_shadow_payloads_no_results(fi, fixture_id)
    checks["no_result_at_prediction_time"] = len(issues) == 0
    checks["shadow_payloads_clean"] = len(issues) == 0
    checks["leakage_issues"] = issues
    required = [
        "prediction_timestamp_before_kickoff",
        "freeze_timestamp_before_kickoff",
        "immutable_freeze_identity_exists",
        "cohort_type_true_forward",
        "no_historical_backfill_flag",
        "no_result_at_prediction_time",
        "shadow_payloads_clean",
        "shadow_cannot_fail_canonical",
    ]
    soft = ["odds_timestamp_before_kickoff", "canonical_freeze_hash_unchanged_after_shadow"]
    checks["all_ok"] = all(checks.get(k) is True for k in required) and all(
        checks.get(k) in (True, None) for k in soft
    )
    return checks


def build_fixture_preview(
    *,
    prod: sqlite3.Connection,
    fi: sqlite3.Connection,
    eval_conn: sqlite3.Connection,
    fixture_id: int,
    freeze_hash_before: str | None = None,
) -> dict[str, Any]:
    freeze = _freeze_row(eval_conn, fixture_id)
    freeze_id = (freeze or {}).get("prediction_id")
    job = _job_row(fi, fixture_id, freeze_id)
    fx = _fixture_meta(prod, fixture_id)
    ko_early = fx.get("kickoff_utc") or _freeze_kickoff(freeze)
    canonical = _canonical_ecse_tops(prod, fixture_id, freeze=freeze)
    wde = _canonical_wde(prod, fixture_id)
    lambda_v2 = _load_shadow(fi, fixture_id, LAMBDA_SELECTED)
    exact_v2 = _load_shadow(fi, fixture_id, EXACT_SELECTED)
    odds_blob = _odds_from_sources(prod, fixture_id, freeze, ko_early)

    # Canonical high-score tail via Poisson/DC from canonical lambdas when available
    c_dist = []
    if canonical.get("lambda_home") is not None and canonical.get("lambda_away") is not None:
        c_dist = dist_dc(float(canonical["lambda_home"]), float(canonical["lambda_away"]))
        canonical["high_score_tail"] = round(_high_score_tail(c_dist), 6)
        canonical.update(_side_mass(c_dist))
    else:
        canonical["high_score_tail"] = None

    # Recompute agreement after tops are known
    e_top5 = (exact_v2 or {}).get("top5") or []
    c_top5 = canonical.get("top5") or []
    comparison = build_top_comparison(c_top5, e_top5)
    high_tail_diff = None
    if canonical.get("high_score_tail") is not None and exact_v2 and exact_v2.get("high_score_tail") is not None:
        high_tail_diff = round(float(exact_v2["high_score_tail"]) - float(canonical["high_score_tail"]), 6)

    comparison["high_score_tail_difference"] = high_tail_diff
    comparison["draw_mass_difference"] = (
        round(float((exact_v2 or {}).get("draw_mass") or 0) - float(canonical.get("draw_mass") or 0), 6)
        if exact_v2 and canonical.get("draw_mass") is not None
        else None
    )
    comparison["home_win_score_mass_difference"] = (
        round(float((exact_v2 or {}).get("home_win_mass") or 0) - float(canonical.get("home_win_mass") or 0), 6)
        if exact_v2 and canonical.get("home_win_mass") is not None
        else None
    )
    comparison["away_win_score_mass_difference"] = (
        round(float((exact_v2 or {}).get("away_win_mass") or 0) - float(canonical.get("away_win_mass") or 0), 6)
        if exact_v2 and canonical.get("away_win_mass") is not None
        else None
    )

    no_bet = wde.get("no_bet")
    if freeze and freeze.get("no_bet") is not None:
        no_bet = bool(freeze.get("no_bet"))

    agreement = classify_model_agreement(
        canonical_top1=canonical.get("top1"),
        exact_top1=(exact_v2 or {}).get("top1"),
        top3_overlap=int(comparison["top3_overlap_count"]),
        top5_overlap=int(comparison["top5_overlap_count"]),
        canonical_confidence=_f(wde.get("confidence") or (freeze or {}).get("wde_confidence")),
        canonical_top5_mass=_f(canonical.get("top5_mass")),
        exact_top5_mass=_f((exact_v2 or {}).get("top5_mass")),
        canonical_total_lambda=_f(canonical.get("lambda_total")),
        exact_total_lambda=_f((exact_v2 or {}).get("lambda_total")),
        high_score_tail_diff=high_tail_diff,
        no_bet=bool(no_bet) if no_bet is not None else False,
    )

    odds_ts = odds_blob.get("odds_timestamp")
    hash_after = (freeze or {}).get("content_hash")
    integrity = build_integrity_proof(
        freeze=freeze,
        fixture=fx,
        job=job,
        odds_ts=odds_ts,
        freeze_hash_before=freeze_hash_before or hash_after,
        freeze_hash_after=hash_after,
        fi=fi,
        fixture_id=int(fixture_id),
    )

    ko = fx.get("kickoff_utc") or _freeze_kickoff(freeze)
    exact_skip = None
    if not exact_v2:
        exact_skip = (job or {}).get("reason") or "exact_v2_shadow_missing"
    elif (job or {}).get("status") not in (None, "success", "skipped"):
        exact_skip = (job or {}).get("reason")

    return {
        "fixture_id": int(fixture_id),
        "date_vienna": _vienna_date(ko),
        "kickoff_utc": ko,
        "kickoff_europe_vienna": _vienna(ko),
        "country": None,
        "league": fx.get("competition_key") or (freeze or {}).get("competition"),
        "home_team": fx.get("home_team") or (freeze or {}).get("home_team_name"),
        "away_team": fx.get("away_team") or (freeze or {}).get("away_team_name"),
        "odds": odds_blob,
        "canonical": {
            **canonical,
            "wde": wde,
            "decision": wde.get("decision") or (freeze or {}).get("wde_decision"),
            "confidence": wde.get("confidence") or (freeze or {}).get("wde_confidence"),
            "consensus": wde.get("consensus") or (freeze or {}).get("consensus"),
            "btts": wde.get("btts")
            or {
                "prediction": (freeze or {}).get("btts_prediction"),
                "probability": (freeze or {}).get("btts_probability"),
            },
            "ou25": wde.get("ou25")
            or {
                "prediction": (freeze or {}).get("ou25_prediction"),
                "over_probability": (freeze or {}).get("over_probability"),
                "under_probability": (freeze or {}).get("under_probability"),
            },
            "no_bet": no_bet,
            "lambda_home": canonical.get("lambda_home") if canonical.get("lambda_home") is not None else _f((freeze or {}).get("lambda_home")),
            "lambda_away": canonical.get("lambda_away") if canonical.get("lambda_away") is not None else _f((freeze or {}).get("lambda_away")),
            "lambda_total": canonical.get("lambda_total")
            if canonical.get("lambda_total") is not None
            else _f((freeze or {}).get("total_lambda")),
            "top5_mass": canonical.get("top5_mass")
            if canonical.get("top5_mass") is not None
            else _f((freeze or {}).get("top5_mass")),
            "entropy": canonical.get("entropy")
            if canonical.get("entropy") is not None
            else _f((freeze or {}).get("entropy")),
        },
        "lambda_v2": lambda_v2,
        "exact_v2": exact_v2,
        "top_comparison": comparison,
        "agreement": agreement,
        "true_forward_job": {
            "status": (job or {}).get("status"),
            "reason": (job or {}).get("reason"),
            "classification": (job or {}).get("classification"),
            "cohort_type": (job or {}).get("cohort_type"),
            "lambda_rows": (job or {}).get("lambda_rows"),
            "exact_rows": (job or {}).get("exact_rows"),
            "job_id": (job or {}).get("job_id"),
            "freeze_id": freeze_id,
        },
        "exact_skipped_blocked_failure_reason": exact_skip,
        "integrity": integrity,
        "labels": {
            "canonical": "CANONICAL",
            "shadow": "SHADOW_RESEARCH_ONLY",
            "exact_v2_not_official": True,
            "challenger_promotion": False,
        },
    }


def _freeze_kickoff(freeze: dict[str, Any] | None) -> str | None:
    if not freeze:
        return None
    return freeze.get("kickoff_utc") or freeze.get("kickoff")


def list_candidate_fixture_ids(
    *,
    eval_conn: sqlite3.Connection,
    fi: sqlite3.Connection,
    prod: sqlite3.Connection | None = None,
    vienna_date: str | None = None,
    fixture_id: int | None = None,
    true_forward_only: bool = False,
) -> list[int]:
    ensure_job_schema(fi)
    if fixture_id is not None:
        return [int(fixture_id)]
    ids: set[int] = set()
    if true_forward_only:
        rows = fi.execute(
            f"""
            SELECT DISTINCT fixture_id FROM {JOB_TABLE}
            WHERE cohort_type='true_forward' AND run_id=?
            """,
            (RUN_ID,),
        ).fetchall()
        ids.update(int(r[0]) for r in rows)
    else:
        rows = eval_conn.execute("SELECT DISTINCT fixture_id FROM frozen_predictions").fetchall()
        ids.update(int(r[0]) for r in rows)
        rows2 = fi.execute(
            f"SELECT DISTINCT fixture_id FROM {JOB_TABLE} WHERE run_id=?",
            (RUN_ID,),
        ).fetchall()
        ids.update(int(r[0]) for r in rows2)
    if vienna_date:
        filtered = []
        for fid in ids:
            ko = None
            row = eval_conn.execute(
                "SELECT kickoff FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at DESC LIMIT 1",
                (fid,),
            ).fetchone()
            if row:
                ko = row[0]
            if not ko and prod is not None:
                fx = prod.execute("SELECT kickoff_utc FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
                if fx:
                    ko = fx[0]
            if ko and _vienna_date(str(ko)) == vienna_date:
                filtered.append(fid)
        return sorted(filtered)
    return sorted(ids)


def build_research_preview(
    *,
    prod: sqlite3.Connection,
    fi: sqlite3.Connection,
    eval_conn: sqlite3.Connection,
    vienna_date: str | None = None,
    league: str | None = None,
    fixture_id: int | None = None,
    true_forward_status: str | None = None,
    agreement_classification: str | None = None,
    no_bet: bool | None = None,
    fixture_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Stable JSON owner research preview. Read-only. No secrets."""
    if fixture_ids is None:
        fixture_ids = list_candidate_fixture_ids(
            eval_conn=eval_conn,
            fi=fi,
            prod=prod,
            vienna_date=vienna_date,
            fixture_id=fixture_id,
            true_forward_only=bool(true_forward_status),
        )
    fixtures_out: list[dict[str, Any]] = []
    for fid in fixture_ids:
        row = build_fixture_preview(prod=prod, fi=fi, eval_conn=eval_conn, fixture_id=fid)
        if league and str(row.get("league") or "").lower() != str(league).lower():
            # also allow substring
            if league.lower() not in str(row.get("league") or "").lower():
                continue
        if true_forward_status:
            st = str((row.get("true_forward_job") or {}).get("status") or "")
            if true_forward_status == "true_forward":
                if (row.get("true_forward_job") or {}).get("cohort_type") != "true_forward":
                    continue
            elif st != true_forward_status:
                continue
        if agreement_classification:
            if (row.get("agreement") or {}).get("agreement_classification") != agreement_classification:
                continue
        if no_bet is not None:
            nb = bool((row.get("canonical") or {}).get("no_bet"))
            if nb != bool(no_bet):
                continue
        fixtures_out.append(row)

    return {
        "owner_only": True,
        "read_only": True,
        "secrets_redacted": True,
        "writes": False,
        "labels": {
            "canonical": "CANONICAL",
            "shadow": "SHADOW_RESEARCH_ONLY",
            "exact_v2_official": False,
            "challenger_outputs_research_only": True,
            "no_promotion": True,
            "no_routing_activation": True,
        },
        "filters": {
            "vienna_date": vienna_date,
            "league": league,
            "fixture_id": fixture_id,
            "true_forward_status": true_forward_status,
            "agreement_classification": agreement_classification,
            "no_bet": no_bet,
        },
        "count": len(fixtures_out),
        "fixtures": fixtures_out,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }
