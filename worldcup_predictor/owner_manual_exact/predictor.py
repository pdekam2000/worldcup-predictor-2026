"""Part B — Build exact score predictions for manual owner match list."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from joblib import load

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner_daily.report import _load_ecse, _load_wde, _owner_label, _top_scores_text
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR, DEFAULT_TIMEZONE, PHASE, REPORTS_DIR, with_safety_labels
from worldcup_predictor.owner_manual_exact.resolver import _date_tag, load_resolution_artifact, resolve_manual_match_list
from worldcup_predictor.owner_manual_exact.score_engine import markets_from_odds
from worldcup_predictor.owner_predict_eval.db_helpers import (
    has_ecse_oddalerts_shadow,
    has_ecse_production_snapshot,
    has_oddalerts_csv_policy_snapshot,
    latest_odds_snapshot,
    odds_source_label,
)
from worldcup_predictor.owner_predict_eval.predictions import _load_oddalerts_shadow
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date


def _shadow_model_status() -> dict[str, Any]:
    val_path = Path("artifacts/wde_shadow_training_validation.json")
    metrics_path = Path("artifacts/wde_shadow_training_metrics.json")
    if not metrics_path.exists():
        return {"available": False, "promoted": False, "label": "NOT_TRAINED"}
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    model_dir = Path(metrics.get("model_dir", ""))
    if not model_dir.exists() or not (model_dir / "shadow_1x2.joblib").exists():
        return {"available": False, "promoted": False, "label": "NOT_TRAINED"}
    rec = "UNKNOWN"
    if val_path.exists():
        rec = json.loads(val_path.read_text(encoding="utf-8")).get("final_recommendation", "UNKNOWN")
    promoted = rec in ("SHADOW_MODEL_BEATS_CURRENT_WDE",)
    return {
        "available": True,
        "promoted": promoted,
        "label": "SHADOW_ONLY",
        "recommendation": rec,
        "model_dir": str(model_dir),
        "model_type": metrics.get("model_type"),
    }


def _run_wde_shadow_markets(model_dir: Path, odds_markets: dict[str, Any]) -> dict[str, Any] | None:
    encoder_path = model_dir / "feature_encoder.joblib"
    if not encoder_path.exists():
        return None
    encoder = load(encoder_path)
    row = {
        "implied_prob_home": odds_markets["implied_prob_home"],
        "implied_prob_draw": odds_markets["implied_prob_draw"],
        "implied_prob_away": odds_markets["implied_prob_away"],
        "implied_prob_over_2_5": 0.5,
        "implied_prob_under_2_5": 0.5,
        "implied_prob_btts_yes": odds_markets["implied_prob_btts_yes"],
        "implied_prob_btts_no": round(1 - odds_markets["implied_prob_btts_yes"], 4),
        "expectedGoalsHome": None,
        "expectedGoalsAway": None,
        "cornerKicksHome": None,
        "cornerKicksAway": None,
        "league": "world_cup",
        "country": "International",
        "season_year": 2026,
        "date": "2026-07-01",
        "data_quality_flags": None,
    }
    df = pd.DataFrame([row])
    x, _ = encoder.transform(df)
    out: dict[str, Any] = {"label": "SHADOW_ONLY"}
    for market in ("1x2", "ou25", "btts"):
        path = model_dir / f"shadow_{market}.joblib"
        if not path.exists():
            continue
        clf = load(path)
        pred = clf.predict(x)[0]
        out[market] = str(pred)
        if hasattr(clf, "predict_proba"):
            proba = clf.predict_proba(x)[0]
            classes = list(clf.classes_)
            out[f"{market}_confidence"] = round(float(max(proba)), 4)
    return out


def _format_source_summary(
    *,
    source_summary: list[str],
    ecse: dict[str, Any] | None,
    exact_source: str,
    ecse_missing_reason: str | None,
) -> str:
    base = "+".join(source_summary)
    if ecse:
        layers = ecse.get("ecse_layers_used") or []
        completeness = ecse.get("ecse_completeness_score")
        layer_text = ",".join(layers) if layers else "odds"
        return f"{base} [ECSE production layers={layer_text} completeness={completeness}]"
    if ecse_missing_reason:
        return f"{base} [ECSE missing: {ecse_missing_reason}]"
    return base


def _fmt_ou(value: str | None) -> str:
    if not value:
        return "—"
    text = str(value).lower()
    if "over" in text:
        return "Over 2.5"
    if "under" in text:
        return "Under 2.5"
    return str(value)


def _normalize_1x2_display(value: str | None) -> str:
    if not value:
        return "—"
    mapping = {"home_win": "1", "draw": "X", "away_win": "2", "home": "1", "away": "2"}
    return mapping.get(str(value).lower(), str(value))


def _risk_badge(
    *,
    confidence: float,
    owner_label: str,
    resolution_status: str,
    odds_only: bool,
) -> str:
    if resolution_status == "MANUAL_ONLY" or odds_only:
        return "HIGH_RISK"
    if owner_label == "NO_BET":
        return "NO_BET"
    if confidence >= 70:
        return "LOW_RISK"
    if confidence >= 55:
        return "MEDIUM_RISK"
    return "HIGH_RISK"


def _format_top_scores(scores: list[dict[str, Any]], n: int) -> list[str]:
    return [str(s.get("scoreline") or "") for s in scores[:n] if s.get("scoreline")]


def _pick_production_source(
    *,
    ecse: dict[str, Any] | None,
    wde: dict[str, Any] | None,
) -> tuple[str, bool, bool, bool]:
    """Return (production_source, ecse_attached, wde_attached, fallback_used)."""
    if ecse and ecse.get("top_1_score"):
        return "ecse_production", True, wde is not None, False
    if wde and (wde.get("predicted_scoreline") or wde.get("predicted_1x2")):
        return "wde_production", False, True, False
    return "manual_fallback", ecse is not None, wde is not None, True


def _pick_exact_scores(
    *,
    ecse: dict[str, Any] | None,
    wde: dict[str, Any] | None,
    odds_scores: list[dict[str, Any]],
) -> tuple[str, list[str], list[str], str]:
    """Return top1, top3, top5, exact_score_source. Shadow is never used for exact scores."""
    if ecse and ecse.get("top_1_score"):
        top1 = str(ecse["top_1_score"])
        top3 = _format_top_scores(
            [{"scoreline": s} if not isinstance(s, dict) else s for s in (ecse.get("top_3_scores") or [])],
            3,
        )
        top5 = _format_top_scores(
            [{"scoreline": s} if not isinstance(s, dict) else s for s in (ecse.get("top_5_scores") or [])],
            5,
        )
        if len(top3) < 3 and odds_scores:
            for s in odds_scores:
                if s["scoreline"] not in top3:
                    top3.append(s["scoreline"])
                if len(top3) >= 3:
                    break
        if len(top5) < 5:
            for s in odds_scores:
                if s["scoreline"] not in top5:
                    top5.append(s["scoreline"])
                if len(top5) >= 5:
                    break
        return top1, top3[:3], top5[:5], "ecse_production"

    if wde and wde.get("predicted_scoreline"):
        top1 = str(wde["predicted_scoreline"]).replace(":", "-")
        top3 = [top1] + [s["scoreline"] for s in odds_scores if s["scoreline"] != top1][:2]
        top5 = top3 + [s["scoreline"] for s in odds_scores if s["scoreline"] not in top3][:2]
        return top1, top3[:3], top5[:5], "wde_production"

    top3 = _format_top_scores(odds_scores, 3)
    top5 = _format_top_scores(odds_scores, 5)
    top1 = top3[0] if top3 else "1-1"
    return top1, top3, top5, "bookmaker_odds_poisson"


def _best_tip(
    pick_1x2: str,
    pick_btts: str,
    pick_ou: str,
    top1: str,
    owner_label: str,
) -> str:
    if owner_label == "NO_BET":
        return "No bet — low edge"
    if owner_label == "STRONG_SIGNAL":
        return f"Endergebnis {top1} + {_normalize_1x2_display(pick_1x2)}"
    return f"{_normalize_1x2_display(pick_1x2)} / BTTS {pick_btts} / O-U {_fmt_ou(pick_ou)}"


def predict_manual_exact_scores(
    *,
    date_arg: str = "today",
    timezone: str = DEFAULT_TIMEZONE,
    settings: Settings | None = None,
    resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    process_date = resolve_process_date(date_arg, timezone)
    if resolution is None:
        resolution = resolve_manual_match_list(
            process_date=process_date, timezone=timezone, settings=settings, auto_import=True
        )

    conn = connect(settings.sqlite_path)
    shadow_status = _shadow_model_status()
    shadow_model_dir = Path(shadow_status["model_dir"]) if shadow_status.get("model_dir") else None

    predictions: list[dict[str, Any]] = []
    for row in resolution.get("matches") or []:
        res = row.get("resolution") or {}
        fid = res.get("fixture_id")
        odds_1x2 = row.get("odds_1x2") or {}
        btts_odds = row.get("btts_odds") or {}
        odds_markets = markets_from_odds(odds_1x2, btts_odds)

        wde = None
        ecse = None
        shadow_ecse = None
        competition_key = "world_cup_2026"
        odds_source = "screenshot"

        if fid:
            fx = conn.execute(
                "SELECT competition_key FROM fixtures WHERE fixture_id=? LIMIT 1",
                (int(fid),),
            ).fetchone()
            if fx:
                competition_key = str(fx["competition_key"])
            wde = _load_wde(int(fid), settings, competition_key)
            ecse = _load_ecse(conn, int(fid))
            shadow_ecse = _load_oddalerts_shadow(conn, int(fid))
            snap = latest_odds_snapshot(conn, int(fid))
            if snap:
                odds_source = odds_source_label(snap.get("payload"))
            elif has_oddalerts_csv_policy_snapshot(conn, int(fid)):
                odds_source = "oddalerts_csv_policy"

        wde_shadow = None
        if shadow_status.get("available") and shadow_model_dir:
            wde_shadow = _run_wde_shadow_markets(shadow_model_dir, odds_markets)

        production_source, ecse_attached, wde_attached, fallback_used = _pick_production_source(
            ecse=ecse, wde=wde
        )

        if production_source == "ecse_production":
            pick_1x2 = odds_markets["pick_1x2"]
            pick_btts = odds_markets["pick_btts"]
            pick_ou = odds_markets["pick_ou25"]
            if wde:
                pick_1x2 = wde.get("predicted_1x2") or pick_1x2
                pick_btts = wde.get("btts_pick") or pick_btts
                pick_ou = wde.get("predicted_over_under_2_5") or pick_ou
        elif production_source == "wde_production" and wde:
            pick_1x2 = wde.get("predicted_1x2") or odds_markets["pick_1x2"]
            pick_btts = wde.get("btts_pick") or odds_markets["pick_btts"]
            pick_ou = wde.get("predicted_over_under_2_5") or odds_markets["pick_ou25"]
        else:
            pick_1x2 = odds_markets["pick_1x2"]
            pick_btts = odds_markets["pick_btts"]
            pick_ou = odds_markets["pick_ou25"]

        top1, top3, top5, exact_source = _pick_exact_scores(
            ecse=ecse,
            wde=wde,
            odds_scores=odds_markets["top_scores"],
        )

        owner_label = _owner_label(wde, ecse) if (wde or ecse) else "MANUAL_ODDS_ONLY"
        conf = float((wde or {}).get("confidence_score") or (ecse or {}).get("confidence_score") or 0)
        if conf < 1 and odds_markets.get("implied_prob_home"):
            conf = max(odds_markets["implied_prob_home"], odds_markets["implied_prob_away"]) * 100

        resolution_status = res.get("resolution_status", "MANUAL_ONLY")
        has_production = production_source in ("ecse_production", "wde_production")
        odds_only = fallback_used and resolution_status == "RESOLVED"
        risk = _risk_badge(
            confidence=conf,
            owner_label=owner_label,
            resolution_status=resolution_status,
            odds_only=odds_only and resolution_status == "MANUAL_ONLY",
        )

        missing_reason = None
        if resolution_status != "RESOLVED":
            missing_reason = res.get("reject_reasons") or res.get("note") or "unresolved"
        elif fallback_used and not ecse_attached and not wde_attached:
            missing_reason = "no_production_attachment"

        ecse_layers = (ecse or {}).get("ecse_layers_used") or []
        ecse_completeness = (ecse or {}).get("ecse_completeness_score")
        ecse_missing_reason = None
        if not ecse_attached and fid:
            if exact_source == "bookmaker_odds_poisson":
                ecse_missing_reason = missing_reason or "no_ecse_snapshot:using_manual_odds_poisson_fallback"
            elif shadow_ecse:
                ecse_missing_reason = "no_production_ecse:shadow_only_available"
            else:
                ecse_missing_reason = missing_reason or "no_ecse_snapshot:insufficient_provider_data"

        source_summary = []
        if ecse_attached:
            source_summary.append("ECSE")
        if wde_attached:
            source_summary.append("WDE")
        if shadow_ecse:
            source_summary.append("OA-shadow")
        if exact_source:
            source_summary.append(exact_source.replace("_", "-"))
        if wde_shadow:
            source_summary.append("WDE-shadow(SHADOW_ONLY)")
        if not source_summary:
            source_summary.append("odds_poisson")

        audit = {
            "fixture_resolved": resolution_status == "RESOLVED",
            "resolution_status": resolution_status,
            "odds_source": odds_source if fid else "screenshot",
            "WDE_used": wde_attached,
            "ECSE_used": ecse_attached,
            "WDE_shadow_used": wde_shadow is not None,
            "WDE_shadow_label": shadow_status.get("label") if wde_shadow else None,
            "OddAlerts_used": shadow_ecse is not None or has_oddalerts_csv_policy_snapshot(conn, int(fid)) if fid else False,
            "exact_score_source": exact_source,
            "production_source": production_source,
            "manual_odds_only": odds_only,
            "pick_origin": production_source,
            "production_pick": has_production,
            "manual_fallback": fallback_used,
            "shadow_comparison_only": wde_shadow is not None,
            "ecse_attached": ecse_attached,
            "wde_attached": wde_attached,
            "fallback_used": fallback_used,
            "missing_reason": missing_reason,
            "ecse_layers_used": ecse_layers,
            "ecse_completeness_score": ecse_completeness,
            "ecse_missing_reason": ecse_missing_reason,
        }

        predictions.append(
            {
                "match_no": row["match_no"],
                "fixture_id": fid,
                "home_team": row.get("home_team_input"),
                "away_team": row.get("away_team_input"),
                "kickoff_label": (row.get("kickoff") or {}).get("kickoff_label"),
                "kickoff_local": (row.get("kickoff") or {}).get("kickoff_local"),
                "odds_1x2": odds_1x2,
                "btts_odds": btts_odds,
                "pick_1x2": pick_1x2,
                "pick_1x2_display": _normalize_1x2_display(pick_1x2),
                "pick_btts": pick_btts,
                "pick_ou25": pick_ou,
                "exact_top1": top1,
                "exact_top3": top3,
                "exact_top5": top5,
                "confidence": round(conf, 1),
                "risk_badge": risk,
                "best_tip": _best_tip(pick_1x2, pick_btts, pick_ou, top1, owner_label),
                "owner_label": owner_label,
                "wde": wde,
                "ecse_production": ecse,
                "ecse_oddalerts_shadow": shadow_ecse,
                "wde_shadow": wde_shadow,
                "wde_shadow_status": shadow_status if wde_shadow else None,
                "source_audit": audit,
                "source_summary": _format_source_summary(
                    source_summary=source_summary,
                    ecse=ecse,
                    exact_source=exact_source,
                    ecse_missing_reason=ecse_missing_reason,
                ),
            }
        )

    conn.close()

    out = with_safety_labels(
        {
            "phase": PHASE,
            "process_date": process_date.isoformat(),
            "timezone": timezone,
            "match_count": len(predictions),
            "resolved_count": sum(1 for p in predictions if p["source_audit"]["fixture_resolved"]),
            "manual_only_count": sum(1 for p in predictions if not p["source_audit"]["fixture_resolved"]),
            "engines": {
                "wde_production": sum(1 for p in predictions if p["source_audit"]["WDE_used"]),
                "ecse_production": sum(1 for p in predictions if p["source_audit"]["ECSE_used"]),
                "wde_shadow": sum(1 for p in predictions if p["source_audit"]["WDE_shadow_used"]),
                "oddalerts_shadow": sum(1 for p in predictions if p["source_audit"]["OddAlerts_used"]),
            },
            "wde_shadow_global_status": shadow_status,
            "predictions": predictions,
            "disclaimer": "Predictions only — not guaranteed results. Owner/internal use.",
        }
    )

    json_path = ARTIFACTS_DIR / f"manual_owner_exact_score_predictions_{_date_tag(process_date)}.json"
    md_path = REPORTS_DIR / f"manual_owner_exact_score_predictions_{_date_tag(process_date)}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_build_markdown_table(out), encoding="utf-8")
    out["json_path"] = str(json_path)
    out["md_path"] = str(md_path)
    return out


def _build_markdown_table(payload: dict[str, Any]) -> str:
    lines = [
        "# Endergebnis / نتیجه دقیق نهایی — Owner Manual Exact Scores",
        "",
        f"**Date:** {payload.get('process_date')} | **Matches:** {payload.get('match_count')}",
        "",
        "Owner/internal only. Not for public publish.",
        "",
        "| Match | fixture_id | Time | Production | Exact source | ECSE | WDE | Fallback | Top-1 | Source | ECSE Detail |",
        "| ----- | ---------- | ---- | ---------- | ------------ | ---- | --- | -------- | ----- | ------ | ----------- |",
    ]
    for p in payload.get("predictions") or []:
        audit = p.get("source_audit") or {}
        if audit.get("ecse_attached"):
            layers = ",".join(audit.get("ecse_layers_used") or [])
            ecse_detail = f"production layers={layers or 'odds'} score={audit.get('ecse_completeness_score')}"
        else:
            ecse_detail = str(audit.get("ecse_missing_reason") or audit.get("missing_reason") or "—")
        lines.append(
            f"| {p.get('home_team')} vs {p.get('away_team')} | {p.get('fixture_id')} | {p.get('kickoff_label')} | "
            f"{audit.get('production_source', '—')} | {audit.get('exact_score_source', '—')} | "
            f"{'yes' if audit.get('ecse_attached') else 'no'} | "
            f"{'yes' if audit.get('wde_attached') else 'no'} | "
            f"{'yes' if audit.get('fallback_used') else 'no'} | "
            f"{p.get('exact_top1')} | {p.get('source_summary')} | {ecse_detail} |"
        )
    lines.extend(
        [
            "",
            "## Disclaimer",
            "",
            payload.get("disclaimer", ""),
            "",
            "WDE shadow model is **SHADOW_ONLY** (not promoted to production).",
            "",
        ]
    )
    return "\n".join(lines)
