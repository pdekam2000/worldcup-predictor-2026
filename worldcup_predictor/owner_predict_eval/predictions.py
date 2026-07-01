"""Part B — Load today predictions with data-source audit (no generation)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner_daily.report import _load_ecse, _load_wde, _owner_label, _top_scores_text
from worldcup_predictor.owner_predict_eval.constants import ARTIFACTS_DIR, PHASE, REPORTS_DIR, with_safety_labels
from worldcup_predictor.owner_predict_eval.dates import date_tag
from worldcup_predictor.owner_predict_eval.db_helpers import (
    has_ecse_oddalerts_shadow,
    has_ecse_production_snapshot,
    latest_odds_snapshot,
    odds_source_label,
    table_exists,
)


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return val if isinstance(val, list) else []


def _load_oddalerts_shadow(conn, fixture_id: int) -> dict[str, Any] | None:
    if table_exists(conn, "ecse_oddalerts_shadow_predictions"):
        row = conn.execute(
            """
            SELECT top_1_score, top_3_scores_json, top_5_scores_json, top_10_scores_json,
                   confidence_score, confidence_tier, source_provider, shadow_run_id
            FROM ecse_oddalerts_shadow_predictions
            WHERE fixture_id=? ORDER BY id DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        if row:
            r = dict(row)
            return {
                "top_1_score": r.get("top_1_score"),
                "top_3_scores": _parse_json_list(r.get("top_3_scores_json")),
                "top_5_scores": _parse_json_list(r.get("top_5_scores_json")),
                "top_10_scores": _parse_json_list(r.get("top_10_scores_json")),
                "confidence_score": r.get("confidence_score"),
                "confidence_tier": r.get("confidence_tier"),
                "source_provider": r.get("source_provider"),
                "shadow_run_id": r.get("shadow_run_id"),
                "source": "shadow_predictions",
            }
    if table_exists(conn, "ecse_oddalerts_shadow_monitor"):
        row = conn.execute(
            """
            SELECT top_1_score, top_3_scores_json, top_5_scores_json, top_10_scores_json,
                   segment_score_v2, segment_badge_v2, source_provider, monitor_run_id
            FROM ecse_oddalerts_shadow_monitor
            WHERE fixture_id=? ORDER BY id DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        if row:
            r = dict(row)
            return {
                "top_1_score": r.get("top_1_score"),
                "top_3_scores": _parse_json_list(r.get("top_3_scores_json")),
                "top_5_scores": _parse_json_list(r.get("top_5_scores_json")),
                "top_10_scores": _parse_json_list(r.get("top_10_scores_json")),
                "confidence_score": r.get("segment_score_v2"),
                "confidence_tier": r.get("segment_badge_v2"),
                "source_provider": r.get("source_provider"),
                "shadow_run_id": r.get("monitor_run_id"),
                "source": "shadow_monitor",
            }
    return None


def _best_tip_summary(
    wde: dict[str, Any] | None,
    ecse: dict[str, Any] | None,
    shadow: dict[str, Any] | None,
    owner_label: str,
) -> dict[str, Any]:
    tip: dict[str, Any] = {"label": owner_label}
    if wde:
        tip["wde_1x2"] = wde.get("predicted_1x2")
        tip["wde_ou_25"] = wde.get("predicted_over_under_2_5")
        tip["wde_btts"] = wde.get("btts_pick")
    if ecse:
        tip["ecse_top1"] = ecse.get("top_1_score")
        tip["ecse_top3"] = _top_scores_text(ecse.get("top_3_scores"), 3)
    if shadow:
        tip["shadow_top1"] = shadow.get("top_1_score")
        tip["shadow_top3"] = _top_scores_text(shadow.get("top_3_scores"), 3)
    if wde and ecse:
        tip["engines_agree"] = owner_label in ("STRONG_SIGNAL", "MEDIUM_SIGNAL")
    return tip


def _data_source_audit(
    conn,
    fixture_id: int,
    *,
    has_wde: bool,
    has_ecse_prod: bool,
    has_shadow: bool,
) -> dict[str, Any]:
    snap = latest_odds_snapshot(conn, fixture_id)
    odds_src = odds_source_label((snap or {}).get("payload"))
    if odds_src == "unknown" and snap:
        odds_src = "provider"
    if not snap:
        odds_src = "none"

    ecse_src = "none"
    if has_ecse_prod:
        ecse_src = "production"
    elif has_shadow:
        ecse_src = "shadow"

    return {
        "WDE_SOURCE": "existing_model_not_retrained",
        "ODDS_SOURCE": odds_src,
        "ECSE_SOURCE": ecse_src,
        "HISTORICAL_CSV_USED_FOR_TRAINING": False,
    }


def _warnings(
    *,
    wde: dict[str, Any] | None,
    ecse: dict[str, Any] | None,
    shadow: dict[str, Any] | None,
    audit: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if wde is None:
        warnings.append("missing_wde_prediction")
    if ecse is None and shadow is None:
        warnings.append("missing_ecse_prediction")
    if audit.get("ODDS_SOURCE") == "none":
        warnings.append("missing_odds_snapshot")
    if audit.get("HISTORICAL_CSV_USED_FOR_TRAINING") is False:
        warnings.append("model_not_retrained_on_historical_csv")
    if wde and wde.get("no_bet_flag"):
        warnings.append("wde_no_bet_flag")
    return warnings


@dataclass
class TodayPredictionBuildResult:
    phase: str = PHASE
    target_date: str = ""
    fixture_count: int = 0
    predictions: list[dict[str, Any]] = field(default_factory=list)
    md_path: str = ""
    json_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "target_date": self.target_date,
                "fixture_count": self.fixture_count,
                "md_path": self.md_path,
                "json_path": self.json_path,
                "predictions": self.predictions,
            }
        )


def artifact_json_path(target: date) -> Path:
    return ARTIFACTS_DIR / f"owner_today_predictions_{date_tag(target)}.json"


def report_md_path(target: date) -> Path:
    return REPORTS_DIR / f"today_predictions_{date_tag(target)}.md"


def build_today_predictions(
    fixtures_payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> TodayPredictionBuildResult:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    target_date = str(fixtures_payload.get("target_date") or "")
    target = date.fromisoformat(target_date) if target_date else date.today()

    predictions: list[dict[str, Any]] = []
    for raw in fixtures_payload.get("fixtures") or []:
        fid = int(raw["fixture_id"])
        comp_key = str(raw.get("competition") or "")
        # competition field may be display name; try fixture row for key
        fx_row = conn.execute(
            "SELECT competition_key FROM fixtures WHERE fixture_id=? LIMIT 1",
            (fid,),
        ).fetchone()
        competition_key = str(fx_row["competition_key"]) if fx_row else comp_key

        wde = _load_wde(fid, settings, competition_key)
        ecse = _load_ecse(conn, fid)
        shadow = _load_oddalerts_shadow(conn, fid)
        has_prod = has_ecse_production_snapshot(conn, fid)
        has_shadow = has_ecse_oddalerts_shadow(conn, fid)
        audit = _data_source_audit(
            conn,
            fid,
            has_wde=wde is not None,
            has_ecse_prod=has_prod,
            has_shadow=has_shadow,
        )
        label = _owner_label(wde, ecse)
        conf = None
        tier = None
        if wde:
            conf = wde.get("confidence_score")
        if ecse:
            tier = ecse.get("prediction_source")
        if shadow:
            tier = shadow.get("confidence_tier") or tier

        predictions.append(
            {
                "fixture_id": fid,
                "home_team": raw.get("home_team"),
                "away_team": raw.get("away_team"),
                "competition": raw.get("competition"),
                "kickoff": raw.get("kickoff"),
                "status": raw.get("status"),
                "wde": wde,
                "ecse_production": ecse,
                "ecse_oddalerts_shadow": shadow,
                "best_tip": _best_tip_summary(wde, ecse, shadow, label),
                "data_source_audit": audit,
                "confidence": conf,
                "tier": tier,
                "owner_label": label,
                "warnings": _warnings(wde=wde, ecse=ecse, shadow=shadow, audit=audit),
            }
        )

    result = TodayPredictionBuildResult(
        target_date=target_date,
        fixture_count=len(predictions),
        predictions=predictions,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = artifact_json_path(target)
    md_path = report_md_path(target)

    json_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    result.json_path = str(json_path)
    result.md_path = str(md_path)

    lines = [
        f"# Owner Today Predictions — {target_date}",
        "",
        "Owner/internal only. Loaded from existing stores — no new model training or public publish.",
        "",
        f"Fixtures: **{len(predictions)}**",
        "",
        "| Fixture | WDE 1X2 | ECSE Top-1 | Shadow Top-1 | Odds | ECSE | Warnings |",
        "|---------|---------|------------|--------------|------|------|----------|",
    ]
    for p in predictions:
        audit = p.get("data_source_audit") or {}
        warns = ", ".join(p.get("warnings") or []) or "—"
        lines.append(
            f"| {p.get('home_team')} vs {p.get('away_team')} | "
            f"{(p.get('wde') or {}).get('predicted_1x2') or '—'} | "
            f"{(p.get('ecse_production') or {}).get('top_1_score') or '—'} | "
            f"{(p.get('ecse_oddalerts_shadow') or {}).get('top_1_score') or '—'} | "
            f"{audit.get('ODDS_SOURCE')} | {audit.get('ECSE_SOURCE')} | {warns} |"
        )
    lines.extend(["", "## Data source audit", ""])
    for p in predictions:
        lines.append(f"### {p.get('home_team')} vs {p.get('away_team')}")
        lines.append(f"- Audit: `{json.dumps(p.get('data_source_audit'), ensure_ascii=False)}`")
        lines.append(f"- Best tip: `{json.dumps(p.get('best_tip'), ensure_ascii=False)}`")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return result
