"""Internal facade: canonical WDE/ECSE without canonical persistence."""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import math

from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload
from worldcup_predictor.config.provider_readiness import stamp_provider_readiness
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.wde_runtime import (
    attach_wde_execution_diagnostics,
    classify_wde_exception,
    prepare_daily_fixture_for_wde,
)
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_metadata import (
    build_fixture_freshness_metadata,
    stamp_payload_odds_freshness,
)
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.owner.euro_b_fixture_selector import odds_readiness_audit
from worldcup_predictor.owner_daily.constants import GENERATED_BY, PHASE
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.predictions import _to_selection
from worldcup_predictor.research.canonical_ephemeral.constants import EXECUTION_MODE
from worldcup_predictor.research.canonical_ephemeral.types import (
    EphemeralCanonicalPrediction,
    ResearchContext,
)
from worldcup_predictor.research.canonical_ephemeral.write_guard import (
    EphemeralWriteBlocked,
    ephemeral_write_guard,
    get_write_attempts,
)
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_timing_experiment.hashing import as_float, as_prob, content_hash


def _mass(rows: list[dict[str, Any]], n: int) -> float | None:
    vals = []
    for r in rows[:n]:
        p = as_prob(r.get("probability"))
        if p is not None:
            vals.append(p)
    return round(sum(vals), 6) if vals else None


def _entropy(rows: list[dict[str, Any]]) -> float | None:
    vals = []
    for r in rows:
        p = as_prob(r.get("probability"))
        if p is not None and p > 0:
            vals.append(p)
    if not vals:
        return None
    s = sum(vals)
    vals = [v / s for v in vals]
    return round(-sum(v * math.log(v) for v in vals), 6)


def _odds_blob(snap: Any) -> dict[str, Any]:
    if snap is None:
        return {}
    d = snap.to_dict() if hasattr(snap, "to_dict") else dict(snap)
    home = as_float(d.get("home_odds") or d.get("home"))
    draw = as_float(d.get("draw_odds") or d.get("draw"))
    away = as_float(d.get("away_odds") or d.get("away"))
    blob = {
        "home": home,
        "draw": draw,
        "away": away,
        "bookmaker_count": d.get("bookmaker_count"),
        "fetched_at": d.get("fetched_at_utc") or d.get("captured_at") or d.get("fetched_at"),
        "odds_age_minutes": d.get("odds_age_minutes") or d.get("age_minutes"),
        "freshness_status": d.get("freshness_class") or d.get("freshness_status"),
        "provider": d.get("provider") or d.get("source"),
        "policy_status": d.get("policy_status"),
        "snapshot_id": d.get("row_id") or d.get("snapshot_id"),
    }
    blob["content_hash"] = content_hash(
        {"home": home, "draw": draw, "away": away, "fetched_at": blob.get("fetched_at")}
    )
    return blob


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm_side(v: Any) -> str:
    s = str(v or "").lower().strip()
    if s in {"1", "home", "home_win", "h"}:
        return "home_win"
    if s in {"x", "draw", "d"}:
        return "draw"
    if s in {"2", "away", "away_win", "a"}:
        return "away_win"
    return s


def _fav(h: Any, d: Any, a: Any) -> str | None:
    vals = {"home_win": as_float(h), "draw": as_float(d), "away_win": as_float(a)}
    present = {k: v for k, v in vals.items() if v is not None and v > 1}
    if len(present) < 2:
        return None
    return min(present, key=present.get)  # type: ignore[arg-type]


def _consensus(wde: str | None, top1_side: str | None, market: str | None, ft: str | None) -> str:
    if not wde:
        return "INSUFFICIENT_DATA"
    if wde and top1_side and wde != top1_side:
        return "HIGH_CONFLICT"
    if wde and ft and wde != ft:
        return "HIGH_CONFLICT"
    sides = [s for s in (wde, top1_side, market, ft) if s]
    if market and wde != market and top1_side and wde == top1_side:
        return "MIXED"
    if len(set(sides)) == 1 and len(sides) >= 2:
        return "HIGH_AGREEMENT"
    if wde == top1_side:
        return "MODERATE_AGREEMENT"
    if len(set(sides)) >= 3:
        return "HIGH_CONFLICT"
    return "MIXED"


def _top5_from_ecse_prediction(prediction: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract Top1–Top5 with probabilities.

    Prefer ``top_10_scorelines`` (dicts with probabilities). When ``top_5_scores``
    is a list of bare strings, enrich probabilities from ``top_10_scorelines``
    by scoreline label so mass/entropy are available at prediction time.
    Does not change ECSE model math — only persistence/extraction.
    """
    if not prediction:
        return []

    prob_by_score: dict[str, float] = {}
    ordered_from_10: list[dict[str, Any]] = []
    for item in prediction.get("top_10_scorelines") or []:
        if not isinstance(item, dict):
            continue
        score = item.get("scoreline") or item.get("score")
        if not score:
            continue
        p = as_float(item.get("probability"))
        if p is not None:
            prob_by_score[str(score)] = p
        ordered_from_10.append(
            {
                "rank": len(ordered_from_10) + 1,
                "score": str(score),
                "probability": p,
            }
        )

    # If top_10 already supplies five scored rows with probabilities, use them.
    if len(ordered_from_10) >= 5 and all(r.get("probability") is not None for r in ordered_from_10[:5]):
        return [
            {"rank": i, "score": r["score"], "probability": r["probability"]}
            for i, r in enumerate(ordered_from_10[:5], start=1)
        ]

    rows: list[dict[str, Any]] = []
    for i, item in enumerate((prediction.get("top_5_scores") or [])[:5], start=1):
        if isinstance(item, dict):
            score = item.get("scoreline") or item.get("score")
            p = as_float(item.get("probability"))
            if p is None and score is not None:
                p = prob_by_score.get(str(score))
            if score:
                rows.append({"rank": i, "score": str(score), "probability": p})
        elif isinstance(item, str) and item:
            rows.append(
                {
                    "rank": i,
                    "score": item,
                    "probability": prob_by_score.get(item),
                }
            )

    if len(rows) < 5:
        for r in ordered_from_10:
            if len(rows) >= 5:
                break
            if all(str(x.get("score")) != str(r.get("score")) for x in rows):
                rows.append(
                    {
                        "rank": len(rows) + 1,
                        "score": r["score"],
                        "probability": r.get("probability"),
                    }
                )

    # Final fill: if still missing probs but top_10 ordered list is complete, prefer it.
    if (
        (not rows or any(r.get("probability") is None for r in rows[:5]))
        and len(ordered_from_10) >= 5
        and all(r.get("probability") is not None for r in ordered_from_10[:5])
    ):
        return [
            {"rank": i, "score": r["score"], "probability": r["probability"]}
            for i, r in enumerate(ordered_from_10[:5], start=1)
        ]

    return [
        {"rank": i, "score": r.get("score"), "probability": r.get("probability")}
        for i, r in enumerate(rows[:5], start=1)
    ]


def _no_bet_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    audit = payload.get("confidence_audit") or payload.get("audit") or {}
    if isinstance(audit, dict) and "confidence_audit" in audit:
        audit = audit.get("confidence_audit") or audit
    # Prefer post-enrichment reason-based fields; also read audit_trace.confidence.
    audit_trace = payload.get("audit_trace") if isinstance(payload.get("audit_trace"), dict) else {}
    conf_trace = audit_trace.get("confidence") if isinstance(audit_trace.get("confidence"), dict) else {}
    reasons = (
        payload.get("no_bet_reasons")
        or (audit.get("no_bet_reasons") if isinstance(audit, dict) else None)
        or conf_trace.get("no_bet_reasons")
        or (payload.get("trace") or {}).get("no_bet_reasons")
        or []
    )
    rule_id = (
        payload.get("no_bet_rule_id")
        or (audit.get("no_bet_rule_id") if isinstance(audit, dict) else None)
        or payload.get("rule_id")
    )
    trigger = (
        payload.get("no_bet_trigger")
        or (audit.get("no_bet_trigger") if isinstance(audit, dict) else None)
        or payload.get("no_bet_flag")
    )
    pick_tier = payload.get("pick_tier") or (audit.get("pick_tier") if isinstance(audit, dict) else None)
    source = None
    if "no_bet" in payload:
        source = "payload.no_bet"
    elif isinstance(audit, dict) and "no_bet" in audit:
        source = "confidence_audit.no_bet"
    quality = {
        "data_quality": payload.get("data_quality") or payload.get("data_quality_score"),
        "confidence": payload.get("confidence") or payload.get("confidence_score"),
        "caution_reasons": payload.get("caution_reasons") or (audit.get("caution_reasons") if isinstance(audit, dict) else None),
        "audit_keys": sorted(audit.keys())[:40] if isinstance(audit, dict) else [],
    }
    out = {
        "no_bet_source": source,
        "no_bet_rule_id": rule_id,
        "no_bet_trigger": trigger,
        "no_bet_reasons": reasons if isinstance(reasons, list) else [reasons] if reasons else [],
        "pick_tier_source": "payload.pick_tier" if payload.get("pick_tier") else (
            "confidence_audit.pick_tier" if isinstance(audit, dict) and audit.get("pick_tier") else None
        ),
        "quality_gate_summary": quality,
    }
    if not out["no_bet_reasons"] and not rule_id and not trigger:
        out["no_bet_reason_status"] = "NOT_EXPOSED_BY_CANONICAL_PAYLOAD"
    else:
        out["no_bet_reason_status"] = "EXPOSED"
    # Additive reason-based recompute fields (new scans / active mode only).
    for key in (
        "no_bet_recomputed",
        "no_bet_decision_stage",
        "no_bet_reason_details",
        "no_bet_cleared_reasons",
        "no_bet_retained_reasons",
        "baseline_no_bet",
        "final_no_bet",
        "shadow_final_no_bet",
    ):
        if key in payload and payload.get(key) is not None:
            out[key] = payload.get(key)
        elif conf_trace.get(key) is not None:
            out[key] = conf_trace.get(key)
    return out


def _daily_from_row(row: dict[str, Any]) -> DailyFixture:
    return DailyFixture(
        fixture_id=int(row["fixture_id"]),
        provider_fixture_id=int(row["fixture_id"]),
        competition_key=str(row.get("competition_key") or ""),
        home_team=str(row.get("home_team") or ""),
        away_team=str(row.get("away_team") or ""),
        kickoff_utc=str(row.get("kickoff_utc") or ""),
        status=str(row.get("status") or "NS"),
        season=int(row["season"]) if row.get("season") is not None else None,
    )


def run_ephemeral_canonical_prediction(
    fixture_id: int,
    *,
    scope: str,
    odds_snapshot: Any | None,
    research_context: ResearchContext,
    settings: Settings | None = None,
    prod_conn: Any | None = None,
) -> EphemeralCanonicalPrediction:
    """Run canonical WDE+ECSE formulas without any canonical persistence.

    Callable only from internal research code. Not exposed via public API or GPT Actions.
    """
    if research_context.caller not in {
        "ecse_timing_experiment",
        "canonical_ephemeral_test",
        "research_internal",
        "forward_aligned_scan",
    }:
        raise PermissionError(
            f"CANONICAL_RESEARCH_EPHEMERAL refused: caller={research_context.caller!r} not authorized"
        )

    bootstrap_gpt_actions_runtime()
    settings = settings or get_settings()
    own_conn = prod_conn is None
    conn = prod_conn or connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    warnings: list[str] = []

    try:
        with ephemeral_write_guard():
            row = conn.execute(
                """
                SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season
                FROM fixtures WHERE fixture_id=? AND is_placeholder=0 LIMIT 1
                """,
                (int(fixture_id),),
            ).fetchone()
            if not row:
                return EphemeralCanonicalPrediction(
                    fixture_id=int(fixture_id),
                    execution_mode=EXECUTION_MODE,
                    complete=False,
                    odds={},
                    wde={},
                    btts={},
                    ou25={},
                    ecse={},
                    consensus=None,
                    no_bet=None,
                    no_bet_diagnostics={"no_bet_reason_status": "NOT_EXPOSED_BY_CANONICAL_PAYLOAD"},
                    pick_tier=None,
                    model_version=None,
                    model_config_hash=None,
                    odds_content_hash=None,
                    research_output_hash=None,
                    warnings=["fixture_not_found"],
                    quality_status="FAILED",
                )

            fx = dict(row)
            daily = _daily_from_row(fx)
            daily = prepare_daily_fixture_for_wde(daily, repo=repo, settings=settings)
            sel = _to_selection(daily)
            fid = int(sel.provider_fixture_id)
            comp_key = normalize_competition_key(sel.competition_key) or sel.competition_key
            tier = fixture_tier(comp_key)

            odds = _odds_blob(odds_snapshot) if odds_snapshot is not None else _odds_blob(
                get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=sel.kickoff_utc)
            )
            if not all(odds.get(k) and float(odds.get(k) or 0) > 1 for k in ("home", "draw", "away")):
                return EphemeralCanonicalPrediction(
                    fixture_id=fid,
                    execution_mode=EXECUTION_MODE,
                    complete=False,
                    odds=odds,
                    wde={},
                    btts={},
                    ou25={},
                    ecse={},
                    consensus=None,
                    no_bet=None,
                    no_bet_diagnostics={"no_bet_reason_status": "NOT_EXPOSED_BY_CANONICAL_PAYLOAD"},
                    pick_tier=None,
                    model_version=None,
                    model_config_hash=None,
                    odds_content_hash=odds.get("content_hash"),
                    research_output_hash=None,
                    warnings=["incomplete_odds"],
                    quality_status="BLOCKED",
                )

            freshness = build_fixture_freshness_metadata(
                conn,
                fixture_id=fid,
                kickoff_utc=sel.kickoff_utc,
                round_name=None,
                status=sel.status,
                prediction_generated_at=_utc_now_iso(),
            )

            # --- WDE (in-memory only) ---
            try:
                pipeline = PredictPipeline(settings, competition_key=comp_key, locale="en")
                result = pipeline.run(fixture_id=fid, record_history=False)
            except Exception as exc:
                code, stage = classify_wde_exception(exc)
                warnings.append(f"wde_error:{code}:{stage}")
                return EphemeralCanonicalPrediction(
                    fixture_id=fid,
                    execution_mode=EXECUTION_MODE,
                    complete=False,
                    odds=odds,
                    wde={},
                    btts={},
                    ou25={},
                    ecse={},
                    consensus=None,
                    no_bet=None,
                    no_bet_diagnostics={"no_bet_reason_status": "NOT_EXPOSED_BY_CANONICAL_PAYLOAD"},
                    pick_tier=None,
                    model_version=None,
                    model_config_hash=None,
                    odds_content_hash=odds.get("content_hash"),
                    research_output_hash=None,
                    warnings=warnings,
                    quality_status="FAILED",
                    canonical_writes_attempted=len(get_write_attempts()),
                )

            if not result.success:
                warnings.append("wde_pipeline_unsuccessful")
                return EphemeralCanonicalPrediction(
                    fixture_id=fid,
                    execution_mode=EXECUTION_MODE,
                    complete=False,
                    odds=odds,
                    wde={},
                    btts={},
                    ou25={},
                    ecse={},
                    consensus=None,
                    no_bet=None,
                    no_bet_diagnostics={"no_bet_reason_status": "NOT_EXPOSED_BY_CANONICAL_PAYLOAD"},
                    pick_tier=None,
                    model_version=None,
                    model_config_hash=None,
                    odds_content_hash=odds.get("content_hash"),
                    research_output_hash=None,
                    warnings=warnings,
                    quality_status="FAILED",
                    canonical_writes_attempted=len(get_write_attempts()),
                )

            from worldcup_predictor.api.prediction_metadata import stamp_prediction_engine_metadata

            payload = build_api_payload(
                result,
                intelligence_report=result.intelligence_report,
                specialist_report=result.specialist_report,
            )
            payload = stamp_prediction_engine_metadata(
                payload, prediction=result.prediction, generated_by=GENERATED_BY
            )
            payload = stamp_provider_readiness(payload, settings=settings)
            payload["owner_only"] = True
            payload["competition_key"] = comp_key
            payload["research_execution_mode"] = EXECUTION_MODE
            payload["research_only"] = True
            payload["canonical"] = False
            payload["final_decision_authority"] = False
            payload["data_source_trace"] = {
                "phase": PHASE,
                "provider_fixture_id": fid,
                "execution_mode": EXECUTION_MODE,
                "research_context": research_context.to_dict(),
                "validation_tier": tier,
                "scope": scope,
            }
            payload = stamp_payload_odds_freshness(payload, freshness)

            # Intentionally DO NOT call repo.upsert_worldcup_stored_prediction

            # --- ECSE (in-memory only) ---
            audit = odds_readiness_audit(conn, sel)
            if not audit.get("lambda_inputs_available"):
                warnings.append("ecse_missing_lambda_inputs")
                ecse_prediction = None
            else:
                fx_row = {
                    "fixture_id": fid,
                    "competition_key": comp_key,
                    "home_team": sel.home_team,
                    "away_team": sel.away_team,
                    "kickoff_utc": sel.kickoff_utc,
                    "status": sel.status,
                }
                try:
                    ecse_prediction = build_ecse_live_prediction(conn, fid, fx_row)
                except Exception as exc:
                    warnings.append(f"ecse_error:{type(exc).__name__}")
                    ecse_prediction = None
                if ecse_prediction:
                    ecse_prediction["prediction_source"] = f"{GENERATED_BY}|{EXECUTION_MODE}"
                    raw = ecse_prediction.get("raw_features") or {}
                    if isinstance(raw, dict):
                        raw["owner_only"] = True
                        raw["research_only"] = True
                        raw["execution_mode"] = EXECUTION_MODE
                        raw["odds_freshness"] = freshness
                        ecse_prediction["raw_features"] = raw
                # Intentionally DO NOT call insert_snapshot

            # Defense: prove write entry points raise under guard if invoked
            # (no invocation here — counts stay zero)

            sem = extract_wde_semantics(payload)
            probs = payload.get("probabilities") or {}
            btts = probs.get("btts") or {}
            ou = probs.get("over_under_2_5") or {}
            top5 = _top5_from_ecse_prediction(ecse_prediction)
            wde = _norm_side(sem.get("decision_pick"))
            ft = _norm_side(sem.get("probability_argmax"))
            top1 = top5[0] if top5 else {}
            top1_side = _norm_side(scoreline_side(str(top1.get("score") or "")))
            market = _fav(odds.get("home"), odds.get("draw"), odds.get("away"))
            cons = _consensus(wde, top1_side, market, ft)
            nobet_diag = _no_bet_diagnostics(payload)
            no_bet = bool(payload.get("no_bet")) if "no_bet" in payload else None

            ecse_block = {
                "top1": top5[0] if len(top5) > 0 else None,
                "top2": top5[1] if len(top5) > 1 else None,
                "top3": top5[2] if len(top5) > 2 else None,
                "top4": top5[3] if len(top5) > 3 else None,
                "top5": top5[4] if len(top5) > 4 else None,
                "scores": [str(t.get("score")) for t in top5 if t.get("score")],
                "top1_probability": as_prob((top5[0] or {}).get("probability")) if top5 else None,
                "top3_mass": _mass(top5, 3),
                "top5_mass": _mass(top5, 5),
                "entropy": _entropy(top5),
                "lambda_home": (ecse_prediction or {}).get("lambda_home"),
                "lambda_away": (ecse_prediction or {}).get("lambda_away"),
                "model_version": (ecse_prediction or {}).get("model_version"),
            }
            wde_block = {
                "decision": sem.get("decision_pick"),
                "ft_marginal": sem.get("probability_argmax"),
                "home_probability": sem.get("home_prob"),
                "draw_probability": sem.get("draw_prob"),
                "away_probability": sem.get("away_prob"),
                "confidence": sem.get("confidence") or payload.get("confidence"),
            }
            model_config_hash = content_hash(
                {
                    "execution_mode": EXECUTION_MODE,
                    "wde_model": payload.get("model_version") or payload.get("pipeline_version"),
                    "ecse_model": ecse_block.get("model_version"),
                    "phase": PHASE,
                }
            )
            research_hash = content_hash(
                {
                    "wde": wde_block,
                    "ecse_scores": ecse_block.get("scores"),
                    "odds": {"home": odds.get("home"), "draw": odds.get("draw"), "away": odds.get("away")},
                    "execution_mode": EXECUTION_MODE,
                }
            )
            attempts = get_write_attempts()
            complete = bool(top5) and bool(sem.get("decision_pick"))
            return EphemeralCanonicalPrediction(
                fixture_id=fid,
                execution_mode=EXECUTION_MODE,
                complete=complete,
                odds=odds,
                wde=wde_block,
                btts={
                    "prediction": btts.get("selection") or (sem.get("btts") or {}).get("prediction"),
                    "yes_probability": as_float((btts.get("probabilities") or {}).get("yes")),
                    "no_probability": as_float((btts.get("probabilities") or {}).get("no")),
                },
                ou25={
                    "preferred_side": ou.get("selection") or (sem.get("ou25") or {}).get("prediction"),
                    "over_probability": as_float((ou.get("probabilities") or {}).get("over_2_5")),
                    "under_probability": as_float((ou.get("probabilities") or {}).get("under_2_5")),
                },
                ecse=ecse_block,
                consensus=cons,
                no_bet=no_bet,
                no_bet_diagnostics=nobet_diag,
                pick_tier=payload.get("pick_tier") or nobet_diag.get("pick_tier_source"),
                model_version=str(payload.get("model_version") or payload.get("pipeline_version") or ""),
                model_config_hash=model_config_hash,
                odds_content_hash=odds.get("content_hash"),
                research_output_hash=research_hash,
                warnings=warnings,
                quality_status="OK" if complete else "PARTIAL",
                canonical_writes_attempted=len(attempts),
                canonical_writes_completed=0,
                freeze_created=False,
                freeze_updated=False,
                wsp_written=False,
                ecse_canonical_written=False,
                research_only=True,
                canonical=False,
                final_decision_authority=False,
                raw_wde_payload=payload,
                raw_ecse_prediction=ecse_prediction,
            )
    except EphemeralWriteBlocked:
        raise
    finally:
        if own_conn:
            try:
                conn.close()
            except Exception:
                pass


def ephemeral_prediction_to_timing_payload(
    pred: EphemeralCanonicalPrediction,
    *,
    identity: dict[str, Any],
    integrity: dict[str, Any],
) -> dict[str, Any]:
    """Map ephemeral result into timing-experiment snapshot payload shape."""
    d = pred.to_dict()
    nobet = d.get("no_bet_diagnostics") or {}
    raw = pred.raw_wde_payload if isinstance(getattr(pred, "raw_wde_payload", None), dict) else {}
    out = {
        "complete": pred.complete,
        "execution_mode": EXECUTION_MODE,
        "odds": pred.odds,
        "wde": pred.wde,
        "btts": pred.btts,
        "ou25": pred.ou25,
        "ecse": pred.ecse,
        "consensus": pred.consensus,
        "no_bet": pred.no_bet,
        "no_bet_reason": nobet.get("no_bet_reasons"),
        "no_bet_diagnostics": nobet,
        "pick_tier": pred.pick_tier,
        "model_version": pred.model_version,
        "model_config_hash": pred.model_config_hash,
        "research_output_hash": pred.research_output_hash,
        "canonical_writes_attempted": pred.canonical_writes_attempted,
        "canonical_writes_completed": pred.canonical_writes_completed,
        "freeze_created": False,
        "freeze_updated": False,
        "wsp_written": False,
        "ecse_canonical_written": False,
        "research_only": True,
        "canonical": False,
        "final_decision_authority": False,
        "freeze_capture": False,
        "identity": identity,
        "integrity": integrity,
        "warnings": pred.warnings,
        "quality_status": pred.quality_status,
    }
    for key in (
        "no_bet_recomputed",
        "no_bet_decision_stage",
        "no_bet_reasons",
        "no_bet_reason_details",
        "no_bet_cleared_reasons",
        "no_bet_retained_reasons",
        "baseline_no_bet",
        "final_no_bet",
    ):
        val = raw.get(key)
        if val is None:
            val = nobet.get(key)
        if val is not None:
            out[key] = val
    if "no_bet_reasons" not in out and nobet.get("no_bet_reasons"):
        out["no_bet_reasons"] = nobet.get("no_bet_reasons")
    return out
