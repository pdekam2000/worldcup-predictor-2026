"""Phase 7B Parts C/D/F — Prematch canonical prediction freeze."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.forward_evaluation.constants import EVAL_PENDING
from worldcup_predictor.forward_evaluation.context import entropy_from_scores, mass_from_scores
from worldcup_predictor.forward_evaluation.fixture_model import (
    competition_family,
    domain_type,
    display_status_for_tier,
    validation_note_for_tier,
)
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.research.ecse_live.prediction_builder import MODEL_VERSION as ECSE_MODEL_VERSION
from worldcup_predictor.research.ecse_live.store import get_snapshot

_FORBIDDEN_RESULT_KEYS = frozenset(
    {
        "actual_score",
        "actual_home_goals",
        "actual_away_goals",
        "actual_1x2",
        "actual_btts",
        "actual_ou25",
        "result_status",
        "finished_at",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _payload_hash(payload: dict[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k not in _FORBIDDEN_RESULT_KEYS}
    blob = json.dumps(clean, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _existing_frozen(eval_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        """
        SELECT * FROM frozen_predictions
        WHERE fixture_id = ?
        ORDER BY frozen_at DESC
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _should_reuse(existing: dict[str, Any], kickoff: datetime | None) -> bool:
    if not existing:
        return False
    frozen_at = _parse_dt(existing.get("frozen_at"))
    if kickoff and frozen_at and frozen_at > kickoff:
        return False
    return True


def _rank_rows(ecse_snap: dict[str, Any] | None, mcp_ecse: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if ecse_snap:
        for key in ("top_10_scorelines", "top_5_scores", "top_3_scores"):
            raw = ecse_snap.get(key)
            if isinstance(raw, list) and raw:
                for idx, item in enumerate(raw[:5], start=1):
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
                if len(rows) >= 5:
                    break
    if len(rows) < 5 and mcp_ecse:
        for item in (mcp_ecse.get("top_scores") or [])[:5]:
            rows.append(
                {
                    "rank": int(item.get("rank") or len(rows) + 1),
                    "score": item.get("score"),
                    "probability": item.get("probability"),
                }
            )
    dedup: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda r: int(r.get("rank") or 99)):
        score = str(row.get("score") or "")
        if not score or score in seen:
            continue
        seen.add(score)
        dedup.append(row)
    return dedup[:5]


def capture_canonical_prediction(
    *,
    prod_conn: sqlite3.Connection,
    fixture: dict[str, Any],
    tier: str,
) -> dict[str, Any]:
    fid = int(fixture["fixture_id"])
    refresh = tier != "B"
    mcp = mcp_runtime.run_fixture_prediction(fid, refresh_if_stale=refresh)
    ecse_snap = get_snapshot(prod_conn, fid)
    wde = mcp.get("wde") or {}
    btts = mcp.get("btts") or {}
    ou = mcp.get("over_under_2_5") or {}
    odds = mcp.get("odds") or {}
    quality = mcp.get("quality") or {}
    ranks = _rank_rows(ecse_snap, mcp.get("ecse"))
    top5_complete = len(ranks) >= 5

    lambda_home = ecse_snap.get("lambda_home") if ecse_snap else None
    lambda_away = ecse_snap.get("lambda_away") if ecse_snap else None
    total_lambda = None
    if lambda_home is not None and lambda_away is not None:
        total_lambda = round(float(lambda_home) + float(lambda_away), 6)

    entropy = entropy_from_scores(ranks) if ranks else None
    top3_mass = mass_from_scores(ranks, 3)
    top5_mass = mass_from_scores(ranks, 5)
    top10_rows = []
    if ecse_snap and isinstance(ecse_snap.get("top_10_scorelines"), list):
        top10_rows = ecse_snap["top_10_scorelines"]
    top10_mass = mass_from_scores(top10_rows, 10) if top10_rows else None

    generated_at = _utc_now()
    if ecse_snap and ecse_snap.get("generated_at"):
        generated_at = str(ecse_snap["generated_at"])

    freeze_payload = {
        "fixture_id": fid,
        "match_name": f"{fixture.get('home_team')} vs {fixture.get('away_team')}",
        "wde": wde,
        "btts": btts,
        "ou25": ou,
        "odds": odds,
        "quality": quality,
        "ranks": ranks,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "generated_at": generated_at,
    }
    phash = _payload_hash(freeze_payload)

    rank_map: dict[str, Any] = {}
    for i in range(1, 6):
        row = next((r for r in ranks if int(r.get("rank") or 0) == i), ranks[i - 1] if len(ranks) >= i else None)
        rank_map[f"rank_{i}_score"] = row.get("score") if row else None
        rank_map[f"rank_{i}_probability"] = row.get("probability") if row else None

    comp_key = str(fixture.get("competition_raw") or fixture.get("competition") or "")
    val_tier = str(tier)
    return {
        "fixture_id": fid,
        "match_name": freeze_payload["match_name"],
        "competition": fixture.get("competition"),
        "tier": tier,
        "validation_tier": val_tier,
        "display_status": display_status_for_tier(val_tier),
        "competition_family": competition_family(comp_key),
        "domain_type": domain_type(comp_key),
        "validation_note": validation_note_for_tier(val_tier),
        "kickoff": fixture.get("kickoff_utc") or fixture.get("kickoff"),
        "generated_at": generated_at,
        "frozen_at": _utc_now(),
        "prediction_mode": fixture.get("prediction_mode"),
        "odds_timestamp": odds.get("freshness"),
        "odds_home": odds.get("home") if "home" in odds else None,
        "odds_draw": odds.get("draw") if "draw" in odds else None,
        "odds_away": odds.get("away") if "away" in odds else None,
        "bookmaker_count": odds.get("bookmaker_count"),
        "odds_freshness": odds.get("freshness"),
        "wde_decision": wde.get("decision_pick") or wde.get("prediction"),
        "ft_marginal_direction": wde.get("probability_argmax"),
        "home_probability": wde.get("home_probability"),
        "draw_probability": wde.get("draw_probability"),
        "away_probability": wde.get("away_probability"),
        "wde_confidence": wde.get("confidence"),
        "effective_1x2": wde.get("effective_pick"),
        "btts_prediction": btts.get("prediction"),
        "btts_probability": btts.get("yes_probability") or btts.get("no_probability"),
        "ou25_prediction": ou.get("prediction"),
        "over_probability": ou.get("over_probability"),
        "under_probability": ou.get("under_probability"),
        "top3_mass": top3_mass,
        "top5_mass": top5_mass,
        "top10_mass": top10_mass,
        "entropy": entropy,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "total_lambda": total_lambda,
        "market_direction": wde.get("probability_argmax"),
        "consensus": quality.get("owner_label"),
        "data_quality": quality.get("status"),
        "warning_summary": ";".join(quality.get("warnings") or []),
        "wde_model_version": wde.get("model_version"),
        "ecse_model_version": (ecse_snap or {}).get("model_version") or ECSE_MODEL_VERSION,
        "ecse_top5_complete": 1 if top5_complete else 0,
        "ecse_top5_flag": None if top5_complete else "ECSE_TOP5_INCOMPLETE",
        "payload_hash": phash,
        "evaluation_status": EVAL_PENDING,
        "mcp_status": quality.get("status"),
        **rank_map,
        "rank_rows": ranks,
    }


def validate_prematch_integrity(frozen: dict[str, Any]) -> tuple[bool, str | None]:
    kickoff = _parse_dt(frozen.get("kickoff"))
    generated = _parse_dt(frozen.get("generated_at"))
    frozen_at = _parse_dt(frozen.get("frozen_at"))
    if kickoff and generated and generated >= kickoff:
        return False, "generated_at_not_before_kickoff"
    if kickoff and frozen_at and frozen_at > kickoff:
        return False, "frozen_at_after_kickoff"
    if frozen.get("mcp_status") not in ("OK", "PARTIAL"):
        return False, f"mcp_status_{frozen.get('mcp_status')}"
    if not frozen.get("wde_decision") and not frozen.get("home_probability"):
        return False, "wde_payload_missing"
    if not frozen.get("rank_1_score"):
        return False, "ecse_top1_missing"
    return True, None


def store_frozen_prediction(
    eval_conn: sqlite3.Connection,
    *,
    batch_id: str,
    frozen: dict[str, Any],
) -> dict[str, Any]:
    fid = int(frozen["fixture_id"])
    kickoff = _parse_dt(frozen.get("kickoff"))
    existing = _existing_frozen(eval_conn, fid)
    if _should_reuse(existing, kickoff):
        return {"stored": False, "reason": "existing_frozen", "prediction_id": existing["prediction_id"]}

    ok, reason = validate_prematch_integrity(frozen)
    if not ok:
        return {"stored": False, "reason": reason or "integrity_failed"}

    dup = eval_conn.execute(
        "SELECT prediction_id FROM frozen_predictions WHERE fixture_id=? AND payload_hash=?",
        (fid, frozen["payload_hash"]),
    ).fetchone()
    if dup:
        return {"stored": False, "reason": "duplicate_payload_hash", "prediction_id": dup["prediction_id"]}

    prediction_id = str(uuid.uuid4())
    eval_conn.execute(
        """
        INSERT INTO frozen_predictions (
            prediction_id, batch_id, fixture_id, match_name, competition, tier, kickoff,
            generated_at, frozen_at, prediction_mode, odds_timestamp, odds_home, odds_draw, odds_away,
            bookmaker_count, odds_freshness, wde_decision, ft_marginal_direction,
            home_probability, draw_probability, away_probability, wde_confidence, effective_1x2,
            btts_prediction, btts_probability, ou25_prediction, over_probability, under_probability,
            top3_mass, top5_mass, top10_mass, entropy, lambda_home, lambda_away, total_lambda,
            market_direction, consensus, data_quality, warning_summary, wde_model_version,
            ecse_model_version, ecse_top5_complete, payload_hash, evaluation_status,
            validation_tier, display_status, competition_family, domain_type, validation_note
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            prediction_id,
            batch_id,
            fid,
            frozen["match_name"],
            frozen.get("competition"),
            frozen.get("tier"),
            frozen.get("kickoff"),
            frozen.get("generated_at"),
            frozen.get("frozen_at"),
            frozen.get("prediction_mode"),
            frozen.get("odds_timestamp"),
            frozen.get("odds_home"),
            frozen.get("odds_draw"),
            frozen.get("odds_away"),
            frozen.get("bookmaker_count"),
            frozen.get("odds_freshness"),
            frozen.get("wde_decision"),
            frozen.get("ft_marginal_direction"),
            frozen.get("home_probability"),
            frozen.get("draw_probability"),
            frozen.get("away_probability"),
            frozen.get("wde_confidence"),
            frozen.get("effective_1x2"),
            frozen.get("btts_prediction"),
            frozen.get("btts_probability"),
            frozen.get("ou25_prediction"),
            frozen.get("over_probability"),
            frozen.get("under_probability"),
            frozen.get("top3_mass"),
            frozen.get("top5_mass"),
            frozen.get("top10_mass"),
            frozen.get("entropy"),
            frozen.get("lambda_home"),
            frozen.get("lambda_away"),
            frozen.get("total_lambda"),
            frozen.get("market_direction"),
            frozen.get("consensus"),
            frozen.get("data_quality"),
            frozen.get("warning_summary"),
            frozen.get("wde_model_version"),
            frozen.get("ecse_model_version"),
            int(frozen.get("ecse_top5_complete") or 0),
            frozen["payload_hash"],
            frozen.get("evaluation_status") or EVAL_PENDING,
            frozen.get("validation_tier") or frozen.get("tier"),
            frozen.get("display_status"),
            frozen.get("competition_family"),
            frozen.get("domain_type"),
            frozen.get("validation_note"),
        ),
    )
    for row in frozen.get("rank_rows") or []:
        eval_conn.execute(
            """
            INSERT OR REPLACE INTO exact_score_rankings (prediction_id, fixture_id, rank, score, probability)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                prediction_id,
                fid,
                int(row.get("rank") or 0),
                str(row.get("score") or ""),
                row.get("probability"),
            ),
        )
    eval_conn.commit()
    frozen["prediction_id"] = prediction_id
    return {"stored": True, "prediction_id": prediction_id, "payload_hash": frozen["payload_hash"]}
