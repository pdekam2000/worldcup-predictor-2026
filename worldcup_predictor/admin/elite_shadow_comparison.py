"""Phase 59C — Elite Shadow vs production prediction comparison (admin-only)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.admin.elite_shadow_preview import (
    DB_PATH,
    EliteShadowPreviewService,
    _eval_key,
    _evaluation_status,
    _fixture_lookup,
    _index_evaluations,
    _index_root_cause,
    load_jsonl,
    sanitize_payload,
)
from worldcup_predictor.config.settings import get_settings

STRONG_DISAGREEMENT_CONFIDENCE = 0.65
STRONG_DISAGREEMENT_TIERS = frozenset({"A", "B"})


def _norm_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return None
    if conf > 1.0:
        conf = conf / 100.0
    return round(conf, 4)


def _top_pick(prediction: Any) -> str | None:
    if prediction is None:
        return None
    if isinstance(prediction, dict) and prediction:
        try:
            return str(max(prediction.items(), key=lambda item: float(item[1] or 0))[0]).lower().strip()
        except (TypeError, ValueError):
            return None
    if isinstance(prediction, list):
        items = [str(x).lower().strip() for x in prediction if x is not None and str(x).strip()]
        return ",".join(sorted(items)) if items else None
    if isinstance(prediction, dict) and "range" in prediction:
        return str(prediction.get("range") or prediction.get("minute_estimate") or "").lower().strip() or None
    text = str(prediction).lower().strip()
    return text or None


def _normalize_pick(prediction: Any, market_id: str) -> str | None:
    if market_id == "goal_timing" and isinstance(prediction, dict):
        return _top_pick(
            {
                "range": prediction.get("range") or prediction.get("minute_range"),
                "minute": prediction.get("minute_estimate") or prediction.get("expected_minute"),
            }
        ) or _top_pick(prediction.get("range") or prediction.get("minute_estimate"))
    if market_id == "1x2":
        return _top_pick(prediction)
    return _top_pick(prediction)


def _load_production_payload(fixture_id: int) -> tuple[dict[str, Any] | None, str | None]:
    if DB_PATH.is_file():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT payload_json
                FROM worldcup_stored_predictions
                WHERE fixture_id = ?
                  AND (is_active IS NULL OR is_active = 1)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (int(fixture_id),),
            ).fetchone()
            if row and row["payload_json"]:
                payload = json.loads(row["payload_json"])
                if isinstance(payload, dict):
                    return payload, "worldcup_stored_predictions"
        except (sqlite3.Error, json.JSONDecodeError, TypeError):
            pass
        finally:
            conn.close()

    try:
        from worldcup_predictor.quota.prediction_cache import get_cached_prediction

        settings = get_settings()
        cached = get_cached_prediction(
            int(fixture_id),
            competition_key="world_cup_2026",
            season=2026,
            locale="en",
            settings=settings,
        )
        if isinstance(cached, dict):
            return cached, "prediction_cache"
    except Exception:
        pass
    return None, None


def _extract_production_market(payload: dict[str, Any] | None, market_id: str) -> dict[str, Any]:
    if not payload:
        return {
            "prediction": None,
            "confidence": None,
            "tier": None,
            "available": False,
            "source_field": None,
        }

    dm = payload.get("detailed_markets")
    if not isinstance(dm, dict):
        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            dm = snapshot.get("detailed_markets")
    dm = dm if isinstance(dm, dict) else {}

    if market_id == "1x2":
        mw = dm.get("match_winner") if isinstance(dm.get("match_winner"), dict) else {}
        selection = mw.get("selection") or payload.get("prediction")
        confidence = mw.get("confidence") if mw.get("confidence") is not None else payload.get("confidence")
        prediction = mw.get("probabilities") if isinstance(mw.get("probabilities"), dict) else selection
        return {
            "prediction": prediction if prediction is not None else selection,
            "confidence": _norm_confidence(confidence),
            "tier": payload.get("pick_tier"),
            "available": selection is not None or prediction is not None,
            "source_field": "detailed_markets.match_winner" if mw else "prediction",
        }

    fg = dm.get("first_goal") if isinstance(dm.get("first_goal"), dict) else {}
    gs = dm.get("goalscorer") if isinstance(dm.get("goalscorer"), dict) else {}

    if market_id in ("first_goal_team", "team_to_score_first"):
        team = fg.get("team")
        return {
            "prediction": team,
            "confidence": _norm_confidence(fg.get("confidence")),
            "tier": payload.get("pick_tier"),
            "available": bool(team),
            "source_field": "detailed_markets.first_goal.team",
        }

    if market_id == "goal_timing":
        timing = fg.get("minute_range") or fg.get("expected_minute")
        return {
            "prediction": timing,
            "confidence": _norm_confidence(fg.get("confidence")),
            "tier": payload.get("pick_tier"),
            "available": timing is not None,
            "source_field": "detailed_markets.first_goal.minute_range",
        }

    if market_id == "anytime_goalscorer":
        player = gs.get("player")
        return {
            "prediction": player,
            "confidence": _norm_confidence(gs.get("confidence")),
            "tier": payload.get("pick_tier"),
            "available": bool(player) and gs.get("available") is not False,
            "source_field": "detailed_markets.goalscorer.player",
        }

    if market_id == "first_goalscorer":
        player = fg.get("player") or gs.get("player")
        return {
            "prediction": player,
            "confidence": _norm_confidence(gs.get("confidence") or fg.get("confidence")),
            "tier": payload.get("pick_tier"),
            "available": bool(player),
            "source_field": "detailed_markets.first_goal.player",
        }

    return {
        "prediction": None,
        "confidence": None,
        "tier": None,
        "available": False,
        "source_field": None,
    }


def _shadow_market_view(pred: dict[str, Any]) -> dict[str, Any]:
    mp = pred.get("market_predictions") or {}
    return {
        "prediction": mp.get("prediction"),
        "confidence": _norm_confidence(mp.get("confidence")),
        "tier": mp.get("tier"),
        "component_contributions": pred.get("component_contributions") or [],
        "available": True,
        "is_shadow": pred.get("is_shadow", True),
        "is_user_visible": pred.get("is_user_visible", False),
    }


def _compare_row(
    *,
    fixture_id: int,
    market_id: str,
    shadow: dict[str, Any],
    production: dict[str, Any],
    production_source: str | None,
    eval_row: dict[str, Any] | None,
    root_cause: list[dict[str, Any]],
    fixture_meta: dict[str, Any],
) -> dict[str, Any]:
    from worldcup_predictor.admin.disagreement_quality_analysis import semantic_pick

    shadow_pick = _normalize_pick(shadow.get("prediction"), market_id)
    production_pick = _normalize_pick(production.get("prediction"), market_id)
    has_shadow = shadow.get("available", True) and shadow_pick is not None
    has_production = production.get("available") and production_pick is not None
    comparable = has_shadow and has_production
    disagreement = None
    semantic_shadow = semantic_pick(shadow_pick, fixture_meta) if shadow_pick else None
    semantic_production = semantic_pick(production_pick, fixture_meta) if production_pick else None
    if comparable:
        disagreement = semantic_shadow != semantic_production

    shadow_conf = shadow.get("confidence")
    strong_disagreement = bool(
        comparable
        and disagreement
        and (
            (shadow_conf is not None and shadow_conf >= STRONG_DISAGREEMENT_CONFIDENCE)
            or str(shadow.get("tier") or "").upper() in STRONG_DISAGREEMENT_TIERS
        )
    )

    return sanitize_payload(
        {
            "fixture_id": fixture_id,
            "market_id": market_id,
            "fixture": fixture_meta,
            "shadow": {
                **shadow,
                "normalized_pick": shadow_pick,
                "semantic_pick": semantic_shadow,
            },
            "production": {
                **production,
                "normalized_pick": production_pick,
                "semantic_pick": semantic_production,
                "source": production_source,
            },
            "has_shadow": has_shadow,
            "has_production": has_production,
            "comparable": comparable,
            "disagreement": disagreement,
            "strong_disagreement": strong_disagreement,
            "evaluation_status": _evaluation_status(eval_row),
            "evaluation": sanitize_payload(eval_row) if eval_row else None,
            "root_cause": sanitize_payload(root_cause) if root_cause else None,
            "is_shadow": True,
            "is_user_visible": False,
        }
    )


class EliteShadowComparisonService:
    """Read-only shadow vs production comparison for super_admin monitoring."""

    def __init__(self, *, preview: EliteShadowPreviewService | None = None) -> None:
        self._preview = preview or EliteShadowPreviewService()

    def _load_shadow_context(
        self,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], dict[int, dict[str, Any]]]:
        preds, pred_meta = load_jsonl(self._preview.predictions_path)
        evals, _ = load_jsonl(self._preview.evaluations_path)
        rc_rows, _ = load_jsonl(self._preview.root_cause_path)
        return preds, _index_evaluations(evals), _index_root_cause(rc_rows), _fixture_lookup()

    def build_comparison(
        self,
        *,
        market: str | None = None,
        tier: str | None = None,
        status: str | None = None,
        disagreement_only: bool = False,
        fixture_id: int | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        preds, eval_index, rc_index, fixtures = self._load_shadow_context()
        production_cache: dict[int, tuple[dict[str, Any] | None, str | None]] = {}
        rows: list[dict[str, Any]] = []

        for pred in preds:
            fid = int(pred.get("fixture_id") or 0)
            if fixture_id is not None and fid != int(fixture_id):
                continue
            market_id = str(pred.get("market_id") or "")
            if market and market != "all" and market_id != market:
                continue

            shadow = _shadow_market_view(pred)
            if tier and tier != "all" and str(shadow.get("tier") or "").upper() != tier.upper():
                continue

            key = _eval_key(fid, market_id)
            eval_row = eval_index.get(key)
            eval_status = _evaluation_status(eval_row)
            if status and status != "all":
                if status == "pending" and eval_status != "pending":
                    continue
                if status == "evaluated" and eval_status != "evaluated":
                    continue

            if fid not in production_cache:
                production_cache[fid] = _load_production_payload(fid)
            prod_payload, prod_source = production_cache[fid]
            production = _extract_production_market(prod_payload, market_id)

            fx = fixtures.get(fid, {})
            fixture_meta = {
                "home_team": fx.get("home_team"),
                "away_team": fx.get("away_team"),
                "kickoff_utc": pred.get("kickoff_time") or fx.get("kickoff_utc"),
                "competition_key": pred.get("competition_key") or fx.get("competition_key"),
                "match_status": fx.get("status"),
            }

            row = _compare_row(
                fixture_id=fid,
                market_id=market_id,
                shadow=shadow,
                production=production,
                production_source=prod_source,
                eval_row=eval_row,
                root_cause=rc_index.get(key, []),
                fixture_meta=fixture_meta,
            )
            if disagreement_only and not row.get("disagreement"):
                continue
            rows.append(row)

        rows.sort(key=lambda r: (int(r.get("fixture_id") or 0), str(r.get("market_id") or "")))
        summary = self._build_summary(rows)
        total = len(rows)
        page = rows[offset : offset + limit]

        return sanitize_payload(
            {
                "status": "ok",
                "total": total,
                "limit": limit,
                "offset": offset,
                "summary": summary,
                "rows": page,
                "shadow_only": True,
                "is_user_visible": False,
            }
        )

    def _build_summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        comparable = [r for r in rows if r.get("comparable")]
        disagreements = [r for r in comparable if r.get("disagreement")]
        same_pick = [r for r in comparable if not r.get("disagreement")]

        prod_confs = [r["production"]["confidence"] for r in comparable if r.get("production", {}).get("confidence") is not None]
        shadow_confs = [r["shadow"]["confidence"] for r in comparable if r.get("shadow", {}).get("confidence") is not None]

        market_counts: dict[str, int] = {}
        for row in disagreements:
            mid = str(row.get("market_id") or "")
            market_counts[mid] = market_counts.get(mid, 0) + 1

        markets_most_disagreement = [
            {"market_id": mid, "disagreement_count": count}
            for mid, count in sorted(market_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

        strong = [r for r in disagreements if r.get("strong_disagreement")]
        strong_sorted = sorted(
            strong,
            key=lambda r: float(r.get("shadow", {}).get("confidence") or 0),
            reverse=True,
        )[:15]

        missing_production = sum(1 for r in rows if r.get("has_shadow") and not r.get("has_production"))
        missing_shadow = sum(1 for r in rows if r.get("has_production") and not r.get("has_shadow"))

        return sanitize_payload(
            {
                "total_rows": len(rows),
                "total_comparable": len(comparable),
                "same_pick_count": len(same_pick),
                "disagreement_count": len(disagreements),
                "agreement_rate": round(len(same_pick) / len(comparable), 4) if comparable else None,
                "average_production_confidence": round(sum(prod_confs) / len(prod_confs), 4) if prod_confs else None,
                "average_shadow_confidence": round(sum(shadow_confs) / len(shadow_confs), 4) if shadow_confs else None,
                "markets_with_most_disagreement": markets_most_disagreement,
                "strong_disagreements": [
                    {
                        "fixture_id": r.get("fixture_id"),
                        "market_id": r.get("market_id"),
                        "match": f"{(r.get('fixture') or {}).get('home_team') or 'Home'} vs {(r.get('fixture') or {}).get('away_team') or 'Away'}",
                        "shadow_pick": (r.get("shadow") or {}).get("normalized_pick"),
                        "production_pick": (r.get("production") or {}).get("normalized_pick"),
                        "shadow_confidence": (r.get("shadow") or {}).get("confidence"),
                        "shadow_tier": (r.get("shadow") or {}).get("tier"),
                        "production_confidence": (r.get("production") or {}).get("confidence"),
                    }
                    for r in strong_sorted
                ],
                "missing_production_count": missing_production,
                "missing_shadow_count": missing_shadow,
            }
        )
