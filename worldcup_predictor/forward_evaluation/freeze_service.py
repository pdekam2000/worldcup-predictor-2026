"""Shared canonical forward-evaluation freeze service — WSP + ECSE only."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.forward_evaluation.constants import EVAL_PENDING
from worldcup_predictor.forward_evaluation.context import entropy_from_scores, mass_from_scores
from worldcup_predictor.forward_evaluation.fixture_model import (
    competition_family,
    display_status_for_tier,
    domain_type,
    prediction_mode_for_tier,
    validation_note_for_tier,
)
from worldcup_predictor.forward_evaluation.hashing import content_hash, source_payload_hash
from worldcup_predictor.forward_evaluation.probability_units import (
    FEATURE_SCHEMA_VERSION,
    PROBABILITY_UNIT_FRACTION,
    normalize_score_probability_rows,
    to_fraction,
    to_percent,
    top_mass,
)
from worldcup_predictor.forward_evaluation.repository import ForwardEvalRepository
from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.mcp_server.git_sha import resolve_current_git_sha
from worldcup_predictor.research.ecse_live.prediction_builder import MODEL_VERSION as ECSE_MODEL_VERSION
from worldcup_predictor.research.ecse_live.store import get_snapshot, get_snapshot_by_id

FREEZE_VERSION = "FORWARD-FREEZE-v2"

REJECT_CODES = frozenset(
    {
        "POST_KICKOFF_GENERATION",
        "FIXTURE_ID_MISMATCH",
        "KICKOFF_MISMATCH",
        "MISSING_WSP",
        "MISSING_ECSE",
        "WDE_PAYLOAD_MISSING",
        "ECSE_TOP5_MISSING",
        "INVALID_PREDICTION_SCOPE",
        "INVALID_PUBLIC_VISIBILITY",
        "SOURCE_PAYLOAD_CONFLICT",
        "HASH_MISMATCH",
        "SOURCE_ROW_NOT_CANONICAL",
        "POST_KICKOFF_CAPTURE",
    }
)

QUARANTINE_CODES = frozenset(
    {
        "MISSING_GENERATED_TIMESTAMP",
        "INVALID_ODDS_FRESHNESS_AT_GENERATION",
        "INVALID_DATA_QUALITY",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in (None,):
        try:
            dt = datetime.fromisoformat(text)
            break
        except ValueError:
            dt = None
    if dt is None:
        try:
            dt = datetime.strptime(text.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_fixture(prod_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = prod_conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season, league_id
        FROM fixtures
        WHERE fixture_id = ? AND (is_placeholder IS NULL OR is_placeholder = 0)
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _load_wsp(
    prod_conn: sqlite3.Connection,
    fixture_id: int,
    *,
    worldcup_stored_prediction_id: int | None,
) -> dict[str, Any] | None:
    if worldcup_stored_prediction_id is not None and int(worldcup_stored_prediction_id) != int(fixture_id):
        return None
    row = prod_conn.execute(
        """
        SELECT * FROM worldcup_stored_predictions
        WHERE fixture_id = ?
          AND (is_active IS NULL OR is_active = 1)
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _select_ecse(
    prod_conn: sqlite3.Connection,
    fixture_id: int,
    *,
    ecse_snapshot_id: int | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if ecse_snapshot_id is not None:
        snap = get_snapshot_by_id(prod_conn, int(ecse_snapshot_id))
        if not snap:
            return None, None
        if int(snap.get("fixture_id") or 0) != int(fixture_id):
            return snap, "FIXTURE_ID_MISMATCH"
        return snap, None
    snap = get_snapshot(prod_conn, int(fixture_id))
    return snap, None


def _parse_ecse_score_list(raw: Any) -> list[Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    return list(raw) if isinstance(raw, list) else []


def _score_items_to_rank_rows(raw: list[Any], *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(raw[:limit], start=1):
        if isinstance(item, dict):
            rows.append(
                {
                    "rank": int(item.get("rank") or idx),
                    "score": item.get("scoreline") or item.get("score"),
                    "probability": item.get("probability"),
                }
            )
        else:
            rows.append({"rank": idx, "score": str(item), "probability": None})
    return rows


def _ecse_rank_rows(ecse: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Top5 rank rows, backfilling probabilities from top10 when top5 omits them.

    Historical ECSE snapshots often store score order in ``top_5_scores`` with null
    probabilities while ``top_10_scorelines`` carries the canonical probabilities.
    Preferring incomplete top5 alone nulls ``exact_score_rankings.probability``,
    ``top5_mass``, and ``entropy`` at freeze time.
    """
    top5_raw: list[Any] = []
    for key in ("top_5_scores", "top_5_scores_json"):
        candidate = _parse_ecse_score_list(ecse.get(key))
        if candidate:
            top5_raw = candidate
            break
    top10_raw = _parse_ecse_score_list(ecse.get("top_10_scorelines"))

    top5_rows = _score_items_to_rank_rows(top5_raw, limit=5)
    top10_rows = _score_items_to_rank_rows(top10_raw, limit=10)

    prob_by_score: dict[str, Any] = {}
    for row in top10_rows:
        score = str(row.get("score") or "")
        if score and row.get("probability") is not None and score not in prob_by_score:
            prob_by_score[score] = row.get("probability")

    rows = list(top5_rows) if top5_rows else list(top10_rows[:5])
    for row in rows:
        if row.get("probability") is None:
            score = str(row.get("score") or "")
            if score in prob_by_score:
                row["probability"] = prob_by_score[score]

    n_with_prob = sum(1 for r in rows if r.get("probability") is not None)
    if n_with_prob < min(3, max(1, len(rows))) and top10_rows:
        # Incomplete probability coverage on top5 — use top10 order/probs.
        rows = list(top10_rows[:5])

    if len(rows) < 5 and top10_rows:
        seen_scores = {str(r.get("score") or "") for r in rows}
        for row in top10_rows:
            score = str(row.get("score") or "")
            if not score or score in seen_scores:
                continue
            rows.append(row)
            seen_scores.add(score)
            if len(rows) >= 5:
                break

    dedup: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda r: int(r.get("rank") or 99)):
        score = str(row.get("score") or "")
        if not score or score in seen:
            continue
        seen.add(score)
        dedup.append(row)
    return dedup[:5]


def _parse_wsp_payload(wsp_row: dict[str, Any]) -> dict[str, Any] | None:
    raw = wsp_row.get("payload_json")
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _infer_prediction_scope(
    wsp_row: dict[str, Any],
    ecse: dict[str, Any],
    source_context: dict[str, Any] | None,
) -> str:
    if source_context and source_context.get("prediction_scope"):
        return str(source_context["prediction_scope"])
    if wsp_row.get("prediction_scope"):
        return str(wsp_row["prediction_scope"])
    if ecse.get("prediction_scope"):
        return str(ecse["prediction_scope"])
    src = str(wsp_row.get("source") or ecse.get("prediction_source") or "")
    if "tier_b" in src.lower() or "owner_shadow" in src.lower():
        return "owner_shadow"
    if "gpt" in src.lower():
        return "gpt_actions"
    if "owner_daily" in src.lower():
        return "owner_daily"
    return "production"


def _extract_decision_meta(payload: dict[str, Any]) -> dict[str, Any]:
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    consensus = (
        payload.get("consensus")
        or quality.get("owner_label")
        or quality.get("consensus")
        or payload.get("owner_label")
    )
    conflicts = payload.get("conflicts") or payload.get("conflict_flags") or quality.get("conflicts") or []
    if isinstance(conflicts, dict):
        conflict_count = len(conflicts)
    elif isinstance(conflicts, list):
        conflict_count = len(conflicts)
    else:
        try:
            conflict_count = int(conflicts)
        except (TypeError, ValueError):
            conflict_count = 0
    no_bet = payload.get("no_bet")
    if no_bet is None:
        no_bet = quality.get("no_bet")
    if isinstance(no_bet, str):
        no_bet = no_bet.strip().lower() in {"1", "true", "yes"}
    elif no_bet is not None:
        no_bet = bool(no_bet)
    return {
        "consensus": consensus,
        "conflict_count": conflict_count,
        "no_bet": no_bet,
    }


def _odds_age_minutes(fetched_at: Any, generated_at: Any) -> float | None:
    a = _parse_dt(fetched_at)
    b = _parse_dt(generated_at)
    if not a or not b:
        return None
    return round(abs((b - a).total_seconds()) / 60.0, 3)


def _extract_odds_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    freshness = payload.get("odds_freshness") or payload.get("freshness_metadata") or {}
    canonical = freshness.get("canonical_odds_snapshot") or payload.get("canonical_odds_snapshot") or {}
    if not isinstance(freshness, dict):
        freshness = {}
    if not isinstance(canonical, dict):
        canonical = {}
    return {
        "odds_home": canonical.get("odds_home") or payload.get("odds_home"),
        "odds_draw": canonical.get("odds_draw") or payload.get("odds_draw"),
        "odds_away": canonical.get("odds_away") or payload.get("odds_away"),
        "bookmaker_count": canonical.get("bookmaker_count") or freshness.get("bookmaker_count"),
        "odds_fetched_at_utc": canonical.get("fetched_at_utc") or freshness.get("odds_snapshot_at"),
        "odds_freshness_status": freshness.get("odds_freshness_class")
        or freshness.get("freshness_class")
        or freshness.get("status"),
        "odds_snapshot_id": canonical.get("snapshot_id"),
        "provider": canonical.get("provider"),
    }


def _execution_status(block: dict[str, Any] | None, *, required: bool = False) -> str:
    if not block:
        return "UNAVAILABLE" if required else "OK"
    if block.get("status") == "UNAVAILABLE" or block.get("unavailable"):
        return "UNAVAILABLE"
    return "OK"


def _result(
    *,
    status: str,
    fixture_id: int,
    reason_code: str | None = None,
    warnings: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "fixture_id": int(fixture_id),
        "reused": False,
        "created": False,
        "quarantined": status == "quarantined",
        "conflict_detected": status == "conflict",
        "reason_code": reason_code,
        "warnings": warnings or [],
    }
    out.update(extra)
    return out


def create_or_reuse_freeze(
    fixture_id: int,
    *,
    prod_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection,
    worldcup_stored_prediction_id: int | None = None,
    ecse_snapshot_id: int | None = None,
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or reuse an immutable prematch freeze from canonical WSP + ECSE rows."""
    from worldcup_predictor.research.canonical_ephemeral.write_guard import block_canonical_write

    # Ephemeral research must never enter freeze capture (create or reuse path that writes).
    block_canonical_write(
        table="frozen_predictions",
        operation="INSERT",
        detail="create_or_reuse_freeze",
    )
    source_context = source_context or {}
    allow_post_kickoff_capture = bool(source_context.get("allow_post_kickoff_capture"))
    repo = ForwardEvalRepository(eval_conn)
    fid = int(fixture_id)

    fixture = _load_fixture(prod_conn, fid)
    if not fixture:
        return _result(status="rejected", fixture_id=fid, reason_code="SOURCE_ROW_NOT_CANONICAL")

    wsp = _load_wsp(prod_conn, fid, worldcup_stored_prediction_id=worldcup_stored_prediction_id)
    if not wsp:
        return _result(status="rejected", fixture_id=fid, reason_code="MISSING_WSP")

    if worldcup_stored_prediction_id is not None and int(worldcup_stored_prediction_id) != int(wsp["fixture_id"]):
        return _result(status="rejected", fixture_id=fid, reason_code="FIXTURE_ID_MISMATCH")

    ecse, ecse_mismatch = _select_ecse(prod_conn, fid, ecse_snapshot_id=ecse_snapshot_id)
    if ecse_mismatch:
        return _result(status="rejected", fixture_id=fid, reason_code=ecse_mismatch)
    if not ecse:
        return _result(status="rejected", fixture_id=fid, reason_code="MISSING_ECSE")

    kickoff = _parse_dt(fixture.get("kickoff_utc") or wsp.get("kickoff_utc") or ecse.get("kickoff_utc"))
    wsp_generated = _parse_dt(wsp.get("predicted_at"))
    ecse_generated = _parse_dt(ecse.get("generated_at"))
    generated_at = ecse_generated or wsp_generated

    if kickoff and wsp.get("kickoff_utc"):
        wsp_kick = _parse_dt(wsp.get("kickoff_utc"))
        if wsp_kick and kickoff != wsp_kick:
            return _result(status="rejected", fixture_id=fid, reason_code="KICKOFF_MISMATCH")

    if kickoff and ecse.get("kickoff_utc"):
        ecse_kick = _parse_dt(ecse.get("kickoff_utc"))
        if ecse_kick and kickoff != ecse_kick:
            return _result(status="rejected", fixture_id=fid, reason_code="KICKOFF_MISMATCH")

    now = _parse_dt(_utc_now())
    if kickoff and now and now >= kickoff and not allow_post_kickoff_capture:
        return _result(status="rejected", fixture_id=fid, reason_code="POST_KICKOFF_CAPTURE")

    warnings: list[str] = []
    quarantine_reasons: list[str] = []

    if not generated_at:
        quarantine_reasons.append("MISSING_GENERATED_TIMESTAMP")
    else:
        if kickoff and generated_at >= kickoff:
            return _result(status="rejected", fixture_id=fid, reason_code="POST_KICKOFF_GENERATION")
        if wsp_generated and kickoff and wsp_generated >= kickoff:
            return _result(status="rejected", fixture_id=fid, reason_code="POST_KICKOFF_GENERATION")
        if ecse_generated and kickoff and ecse_generated >= kickoff:
            return _result(status="rejected", fixture_id=fid, reason_code="POST_KICKOFF_GENERATION")

    payload = _parse_wsp_payload(wsp)
    if not payload:
        return _result(status="rejected", fixture_id=fid, reason_code="WDE_PAYLOAD_MISSING")

    sem = extract_wde_semantics(payload)
    if not sem.get("decision_pick") and not sem.get("home_prob"):
        return _result(status="rejected", fixture_id=fid, reason_code="WDE_PAYLOAD_MISSING")

    ranks = normalize_score_probability_rows(_ecse_rank_rows(ecse))
    if len(ranks) < 5:
        return _result(status="rejected", fixture_id=fid, reason_code="ECSE_TOP5_MISSING")

    comp_key = normalize_competition_key(
        str(fixture.get("competition_key") or wsp.get("competition_key") or "")
    ) or str(fixture.get("competition_key") or "")
    tier = fixture_tier(comp_key) or source_context.get("validation_tier") or "A"
    prediction_scope = _infer_prediction_scope(wsp, ecse, source_context)
    valid_scopes = {"production", "owner_daily", "owner_shadow", "gpt_actions"}
    if prediction_scope not in valid_scopes:
        return _result(status="rejected", fixture_id=fid, reason_code="INVALID_PREDICTION_SCOPE")

    public_visible = tier == "A" and prediction_scope != "owner_shadow"
    if source_context.get("public_visible") is not None:
        public_visible = bool(source_context["public_visible"])
    if tier == "B" or prediction_scope == "owner_shadow":
        public_visible = False
    if tier == "B" and source_context.get("public_visible") is True:
        return _result(status="rejected", fixture_id=fid, reason_code="INVALID_PUBLIC_VISIBILITY")

    if int(wsp.get("is_quarantined") or 0) == 1:
        quarantine_reasons.append("INVALID_DATA_QUALITY")

    odds_evidence = _extract_odds_evidence(payload)
    decision_meta = _extract_decision_meta(payload)
    freshness_status = str(odds_evidence.get("odds_freshness_status") or "").upper()
    if freshness_status in {"ODDS_STALE", "DATA_QUALITY_BLOCKED", "ODDS_MISSING"}:
        quarantine_reasons.append("INVALID_ODDS_FRESHNESS_AT_GENERATION")

    data_quality = payload.get("data_quality") or payload.get("quality_status") or payload.get("quality")
    if isinstance(data_quality, dict):
        data_quality = data_quality.get("status")
    if str(data_quality or "").upper() in {"BLOCKED", "DATA_QUALITY_BLOCKED"}:
        quarantine_reasons.append("INVALID_DATA_QUALITY")

    btts_block = sem.get("btts") if isinstance(sem.get("btts"), dict) else {}
    ou_block = sem.get("ou25") if isinstance(sem.get("ou25"), dict) else {}

    src_hash = source_payload_hash(
        fixture_id=fid,
        wsp_predicted_at=wsp.get("predicted_at"),
        wsp_payload=payload,
        ecse_snapshot_id=int(ecse.get("id") or 0) or None,
        ecse_generated_at=ecse.get("generated_at"),
        ecse_top5=ranks,
    )

    git_sha = resolve_current_git_sha().get("current_git_sha")

    raw_top10 = ecse.get("top_10_scorelines") or []
    if isinstance(raw_top10, str):
        try:
            raw_top10 = json.loads(raw_top10)
        except json.JSONDecodeError:
            raw_top10 = []
    top10_rows = normalize_score_probability_rows(
        [
            {
                "rank": int(item.get("rank") or idx),
                "score": item.get("scoreline") or item.get("score"),
                "probability": item.get("probability"),
            }
            if isinstance(item, dict)
            else {"rank": idx, "score": str(item), "probability": None}
            for idx, item in enumerate(list(raw_top10)[:10], start=1)
        ]
    )

    entropy = entropy_from_scores(ranks)
    top3_mass = top_mass(ranks, 3) or mass_from_scores(ranks, 3)
    top5_mass = top_mass(ranks, 5) or mass_from_scores(ranks, 5)
    top10_mass = top_mass(top10_rows, 10) if top10_rows else mass_from_scores(top10_rows, 10)

    lambda_home = ecse.get("lambda_home")
    lambda_away = ecse.get("lambda_away")
    total_lambda = None
    if lambda_home is not None and lambda_away is not None:
        total_lambda = round(float(lambda_home) + float(lambda_away), 6)

    generated_at_str = (
        generated_at.strftime("%Y-%m-%dT%H:%M:%S+00:00") if generated_at else wsp.get("predicted_at")
    )
    odds_fetched = odds_evidence.get("odds_fetched_at_utc")
    last_prematch = generated_at_str
    for candidate in (generated_at_str, odds_fetched):
        dt = _parse_dt(candidate)
        if dt and (not last_prematch or (_parse_dt(last_prematch) and dt < _parse_dt(last_prematch))):
            last_prematch = candidate

    home_frac = to_fraction(sem.get("home_prob"), field="home_probability")
    draw_frac = to_fraction(sem.get("draw_prob"), field="draw_probability")
    away_frac = to_fraction(sem.get("away_prob"), field="away_probability")
    home_pct = to_percent(sem.get("home_prob"), field="home_probability")
    draw_pct = to_percent(sem.get("draw_prob"), field="draw_probability")
    away_pct = to_percent(sem.get("away_prob"), field="away_probability")

    wde_payload = {
        "decision_pick": sem.get("decision_pick"),
        "effective_pick": sem.get("effective_pick"),
        "probability_argmax": sem.get("probability_argmax"),
        "home_probability": home_frac,
        "draw_probability": draw_frac,
        "away_probability": away_frac,
        "home_probability_pct": home_pct,
        "draw_probability_pct": draw_pct,
        "away_probability_pct": away_pct,
        "probability_unit": PROBABILITY_UNIT_FRACTION,
        "confidence": sem.get("confidence"),
        "decision_source": sem.get("decision_source"),
        "model_version": sem.get("model_version"),
        "execution_status": "OK",
    }
    btts_payload = dict(btts_block)
    ou_payload = dict(ou_block)
    ecse_payload = {
        "top1": ranks[0] if ranks else None,
        "top5": ranks,
        "top10": top10_rows[:10] if top10_rows else [],
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "model_version": ecse.get("model_version") or ECSE_MODEL_VERSION,
    }

    rank_map: dict[str, Any] = {}
    for i in range(1, 6):
        row = next((r for r in ranks if int(r.get("rank") or 0) == i), ranks[i - 1] if len(ranks) >= i else None)
        rank_map[f"rank_{i}_score"] = row.get("score") if row else None
        rank_map[f"rank_{i}_probability"] = row.get("probability") if row else None

    envelope: dict[str, Any] = {
        "fixture_id": fid,
        "provider_fixture_id": fid,
        "match_name": f"{fixture.get('home_team')} vs {fixture.get('away_team')}",
        "competition": comp_key,
        "league_id": fixture.get("league_id"),
        "season": str(fixture.get("season")) if fixture.get("season") is not None else None,
        "home_team_name": fixture.get("home_team"),
        "away_team_name": fixture.get("away_team"),
        "tier": tier,
        "validation_tier": tier,
        "display_status": display_status_for_tier(str(tier)),
        "competition_family": competition_family(comp_key),
        "domain_type": domain_type(comp_key),
        "validation_note": validation_note_for_tier(str(tier)),
        "prediction_mode": prediction_mode_for_tier(str(tier)),
        "prediction_scope": prediction_scope,
        "public_visible": 1 if public_visible else 0,
        "kickoff": kickoff.strftime("%Y-%m-%dT%H:%M:%S+00:00") if kickoff else fixture.get("kickoff_utc"),
        "generated_at": generated_at_str,
        "worldcup_stored_prediction_id": int(wsp["fixture_id"]),
        "ecse_snapshot_id": int(ecse.get("id") or 0),
        "source_job_id": source_context.get("source_job_id"),
        "odds_snapshot_id": odds_evidence.get("odds_snapshot_id"),
        "source_commit_sha": git_sha,
        "source_payload_hash": src_hash,
        "odds_fetched_at_utc": odds_fetched,
        "last_valid_prematch_time_utc": last_prematch,
        "prediction_engine_version": FREEZE_VERSION,
        "wde_model_version": sem.get("model_version"),
        "ecse_model_version": ecse.get("model_version") or ECSE_MODEL_VERSION,
        "btts_model_version": btts_block.get("model_version"),
        "ou_model_version": ou_block.get("model_version"),
        "data_quality": str(data_quality) if data_quality else None,
        "odds_freshness_status": odds_evidence.get("odds_freshness_status"),
        "odds_timestamp": odds_fetched,
        "odds_home": odds_evidence.get("odds_home"),
        "odds_draw": odds_evidence.get("odds_draw"),
        "odds_away": odds_evidence.get("odds_away"),
        "bookmaker_count": odds_evidence.get("bookmaker_count"),
        "odds_freshness": odds_evidence.get("odds_freshness_status"),
        "odds_provider": odds_evidence.get("provider"),
        "odds_age_minutes": _odds_age_minutes(odds_fetched, generated_at_str),
        "wde_decision": sem.get("decision_pick"),
        "ft_marginal_direction": sem.get("probability_argmax"),
        "home_probability": home_frac,
        "draw_probability": draw_frac,
        "away_probability": away_frac,
        "home_probability_pct": home_pct,
        "draw_probability_pct": draw_pct,
        "away_probability_pct": away_pct,
        "probability_unit": PROBABILITY_UNIT_FRACTION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "wde_confidence": sem.get("confidence"),
        "effective_1x2": sem.get("effective_pick"),
        "market_direction": sem.get("probability_argmax"),
        "btts_prediction": btts_block.get("prediction") or btts_block.get("selection"),
        "btts_probability": to_fraction(
            btts_block.get("yes_probability") or btts_block.get("no_probability"),
            field="btts_probability",
        ),
        "ou25_prediction": ou_block.get("prediction") or ou_block.get("selection"),
        "over_probability": to_fraction(ou_block.get("over_probability"), field="over_probability"),
        "under_probability": to_fraction(ou_block.get("under_probability"), field="under_probability"),
        "top3_mass": top3_mass,
        "top5_mass": top5_mass,
        "top10_mass": top10_mass,
        "entropy": entropy,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "total_lambda": total_lambda,
        "consensus": decision_meta.get("consensus"),
        "no_bet": 1 if decision_meta.get("no_bet") is True else (0 if decision_meta.get("no_bet") is False else None),
        "conflict_count": decision_meta.get("conflict_count"),
        "wde_execution_status": _execution_status(wde_payload, required=True),
        "btts_execution_status": _execution_status(btts_block),
        "ou_execution_status": _execution_status(ou_block),
        "ecse_top5_complete": 1,
        "wde_payload_json": json.dumps(wde_payload, default=str),
        "btts_payload_json": json.dumps(btts_payload, default=str),
        "ou_payload_json": json.dumps(ou_payload, default=str),
        "ecse_payload_json": json.dumps(ecse_payload, default=str),
        "immutable": 1,
        "freeze_version": FREEZE_VERSION,
        "freeze_status": "QUARANTINED" if quarantine_reasons else "ACTIVE",
        "evaluation_status": EVAL_PENDING,
        "rank_rows": ranks,
        **rank_map,
    }

    complete_payload = {
        "identity": {
            "fixture_id": fid,
            "prediction_scope": prediction_scope,
            "validation_tier": tier,
            "public_visible": public_visible,
        },
        "wde": wde_payload,
        "btts": btts_payload,
        "ou25": ou_payload,
        "ecse": ecse_payload,
        "evidence": odds_evidence,
        "decision_meta": decision_meta,
        "probability_unit": PROBABILITY_UNIT_FRACTION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "no_bet": decision_meta.get("no_bet"),
        "consensus": decision_meta.get("consensus"),
        "conflict_count": decision_meta.get("conflict_count"),
        "source": {
            "worldcup_stored_prediction_id": int(wsp["fixture_id"]),
            "ecse_snapshot_id": int(ecse.get("id") or 0),
            "source_payload_hash": src_hash,
        },
    }
    envelope["complete_payload_json"] = json.dumps(complete_payload, default=str)

    c_hash = content_hash({**envelope, **complete_payload})
    envelope["content_hash"] = c_hash
    envelope["payload_hash"] = c_hash

    existing = repo.fetch_by_fixture_and_hash(fid, c_hash)
    if existing:
        return _result(
            status="reused",
            fixture_id=fid,
            reused=True,
            freeze_id=existing["prediction_id"],
            content_hash=c_hash,
            source_payload_hash=src_hash,
            source_prediction_id=int(wsp["fixture_id"]),
            source_ecse_snapshot_id=int(ecse.get("id") or 0),
            warnings=warnings,
        )

    conflict = repo.detect_source_conflict(
        fid,
        worldcup_stored_prediction_id=int(wsp["fixture_id"]),
        ecse_snapshot_id=int(ecse.get("id") or 0),
        source_payload_hash=src_hash,
        content_hash=c_hash,
    )
    if conflict:
        repo.mark_quarantined(
            fid,
            "SOURCE_PAYLOAD_CONFLICT",
            prediction_scope=prediction_scope,
            detail={"existing_freeze_id": conflict.get("prediction_id")},
        )
        return _result(
            status="conflict",
            fixture_id=fid,
            conflict_detected=True,
            reason_code="SOURCE_PAYLOAD_CONFLICT",
            freeze_id=conflict.get("prediction_id"),
            content_hash=c_hash,
            source_payload_hash=src_hash,
        )

    if quarantine_reasons:
        for reason in quarantine_reasons:
            repo.mark_quarantined(
                fid,
                reason,
                prediction_scope=prediction_scope,
                detail={"source_payload_hash": src_hash},
            )
        envelope["quarantine_reason"] = ";".join(quarantine_reasons)
        envelope["freeze_status"] = "QUARANTINED"
        warnings.extend(quarantine_reasons)

    envelope["frozen_at"] = _utc_now()
    freeze_id = repo.insert_freeze(envelope, rank_rows=ranks)

    return _result(
        status="quarantined" if quarantine_reasons else "created",
        fixture_id=fid,
        created=not bool(quarantine_reasons),
        quarantined=bool(quarantine_reasons),
        freeze_id=freeze_id,
        content_hash=c_hash,
        source_payload_hash=src_hash,
        source_prediction_id=int(wsp["fixture_id"]),
        source_ecse_snapshot_id=int(ecse.get("id") or 0),
        reason_code=quarantine_reasons[0] if quarantine_reasons else None,
        warnings=warnings,
    )
