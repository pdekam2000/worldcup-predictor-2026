"""Part G — Owner daily control panel report from existing artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.owner_predict_eval.constants import (
    ARTIFACTS_DIR,
    PHASE,
    REPORTS_DIR,
    SAFETY_LABELS,
    with_safety_labels,
)
from worldcup_predictor.owner_predict_eval.dates import date_tag, resolve_process_date, yesterday_of
from worldcup_predictor.owner_predict_eval.predictions import artifact_json_path as predictions_artifact
from worldcup_predictor.owner_predict_eval.runner import daily_report_json_path
from worldcup_predictor.owner_predict_eval.yesterday_eval import artifact_json_path as yesterday_artifact


ActionRequired = str


def control_panel_md_path(target: date) -> Path:
    return REPORTS_DIR / f"OWNER_DAILY_CONTROL_PANEL_{date_tag(target)}.md"


def control_panel_json_path(target: date) -> Path:
    return ARTIFACTS_DIR / f"owner_daily_control_panel_{date_tag(target)}.json"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _fixture_label(home: str | None, away: str | None) -> str:
    return f"{home or '?'} vs {away or '?'}"


def _prediction_readiness(row: dict[str, Any]) -> str:
    wde = row.get("wde") is not None
    ecse = row.get("ecse_production") is not None
    if wde and ecse:
        return "ready"
    if wde or ecse:
        return "partial"
    return "missing"


def _today_fixture_rows(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in predictions:
        audit = p.get("data_source_audit") or {}
        best_tip = p.get("best_tip") or {}
        rows.append(
            {
                "fixture_id": p.get("fixture_id"),
                "kickoff": p.get("kickoff"),
                "home_team": p.get("home_team"),
                "away_team": p.get("away_team"),
                "prediction_readiness": _prediction_readiness(p),
                "wde_available": p.get("wde") is not None,
                "ecse_available": p.get("ecse_production") is not None,
                "odds_source": audit.get("ODDS_SOURCE"),
                "confidence": p.get("confidence"),
                "tier": p.get("tier"),
                "best_owner_note": best_tip.get("label") or p.get("owner_label") or "—",
            }
        )
    return rows


def _yesterday_evaluation_status(yesterday: dict[str, Any]) -> str:
    total = int(yesterday.get("fixture_count") or 0)
    evaluated = int(yesterday.get("evaluated_count") or 0)
    waiting = int(yesterday.get("waiting_result_count") or 0)
    if total == 0:
        return "no_fixtures"
    if evaluated == total:
        return f"complete_{evaluated}_of_{total}"
    if evaluated > 0:
        return f"partial_{evaluated}_of_{total}"
    if waiting > 0:
        return f"waiting_{waiting}_of_{total}"
    return "unknown"


def _safety_status(payload: dict[str, Any]) -> str:
    violations = [key for key, expected in SAFETY_LABELS.items() if payload.get(key) is not expected]
    if violations:
        return f"violation:{','.join(violations)}"
    return "all_constraints_ok"


def _hit_miss_summary(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, dict[str, int]] = {
        "wde_1x2": {"hits": 0, "misses": 0, "unknown": 0},
        "wde_btts": {"hits": 0, "misses": 0, "unknown": 0},
        "wde_over_under_2_5": {"hits": 0, "misses": 0, "unknown": 0},
        "ecse_top1": {"hits": 0, "misses": 0, "unknown": 0},
        "ecse_top3": {"hits": 0, "misses": 0, "unknown": 0},
    }

    def _tally(bucket: str, hit: bool | None) -> None:
        if hit is True:
            summary[bucket]["hits"] += 1
        elif hit is False:
            summary[bucket]["misses"] += 1
        else:
            summary[bucket]["unknown"] += 1

    for fx in fixtures:
        if fx.get("evaluation_status") != "EVALUATED":
            continue
        wde = fx.get("wde") or {}
        ecse = fx.get("ecse_production") or {}
        _tally("wde_1x2", (wde.get("one_x_two") or {}).get("hit"))
        _tally("wde_btts", (wde.get("btts") or {}).get("hit"))
        _tally("wde_over_under_2_5", (wde.get("over_under_2_5") or {}).get("hit"))
        _tally("ecse_top1", ecse.get("top1_hit"))
        _tally("ecse_top3", ecse.get("top3_hit"))

    return summary


def _yesterday_section(yesterday: dict[str, Any]) -> dict[str, Any]:
    fixtures = yesterday.get("fixtures") or []
    evaluated_rows = [f for f in fixtures if f.get("evaluation_status") == "EVALUATED"]
    missing_rows = [f for f in fixtures if f.get("evaluation_status") == "WAITING_RESULT"]

    evaluated_results = [
        {
            "fixture_id": f.get("fixture_id"),
            "fixture": _fixture_label(f.get("home_team"), f.get("away_team")),
            "final_score": f.get("final_score"),
        }
        for f in evaluated_rows
    ]
    missing_fixtures = [
        {
            "fixture_id": f.get("fixture_id"),
            "fixture": _fixture_label(f.get("home_team"), f.get("away_team")),
            "kickoff": f.get("kickoff"),
        }
        for f in missing_rows
    ]

    return {
        "total_fixtures": int(yesterday.get("fixture_count") or 0),
        "evaluated_count": int(yesterday.get("evaluated_count") or 0),
        "missing_count": int(yesterday.get("waiting_result_count") or 0),
        "evaluated_results": evaluated_results,
        "hit_miss_summary": _hit_miss_summary(fixtures),
        "missing_fixtures": missing_fixtures,
    }


def _odds_sources_today(predictions: list[dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    for p in predictions:
        src = (p.get("data_source_audit") or {}).get("ODDS_SOURCE")
        if src and src not in sources:
            sources.append(str(src))
    return sources


def _pick_best_tip_candidate(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    for p in predictions:
        wde = p.get("wde") or {}
        ecse = p.get("ecse_production") or {}
        best_tip = p.get("best_tip") or {}
        fixture = _fixture_label(p.get("home_team"), p.get("away_team"))
        fid = p.get("fixture_id")

        wde_conf = wde.get("confidence_score")
        if isinstance(wde_conf, (int, float)) and wde_conf > 0 and wde.get("predicted_1x2"):
            reasons: list[str] = []
            if best_tip.get("engines_agree"):
                reasons.append("wde_ecse_agree")
            if best_tip.get("label"):
                reasons.append(f"owner_label={best_tip.get('label')}")
            if wde.get("risk_level"):
                reasons.append(f"risk_level={wde.get('risk_level')}")
            candidates.append(
                {
                    "fixture_id": fid,
                    "fixture": fixture,
                    "market": "1x2",
                    "pick": wde.get("predicted_1x2"),
                    "confidence": wde_conf,
                    "tier": p.get("tier") or wde.get("risk_level"),
                    "confidence_source": "wde.confidence_score",
                    "reasons": reasons,
                    "sort_score": float(wde_conf),
                }
            )

        ecse_conf = ecse.get("confidence_score")
        if isinstance(ecse_conf, (int, float)) and ecse_conf > 0 and ecse.get("top_1_score"):
            candidates.append(
                {
                    "fixture_id": fid,
                    "fixture": fixture,
                    "market": "correct_score_top1",
                    "pick": ecse.get("top_1_score"),
                    "confidence": ecse_conf,
                    "tier": ecse.get("prediction_source") or p.get("tier"),
                    "confidence_source": "ecse_production.confidence_score",
                    "reasons": [f"ecse_source={ecse.get('prediction_source')}"],
                    "sort_score": float(ecse_conf),
                }
            )

    if not candidates:
        return {"status": "NO_BEST_TIP_AVAILABLE"}

    best = max(candidates, key=lambda c: c["sort_score"])
    return {
        "status": "AVAILABLE",
        "fixture_id": best["fixture_id"],
        "fixture": best["fixture"],
        "market": best["market"],
        "pick": best["pick"],
        "confidence": best["confidence"],
        "tier": best["tier"],
        "confidence_source": best["confidence_source"],
        "reasons": best["reasons"],
    }


def _derive_action_required(
    *,
    run: dict[str, Any],
    yesterday: dict[str, Any],
    today_predictions: list[dict[str, Any]],
    audit: dict[str, Any],
) -> ActionRequired:
    summary = run.get("owner_daily_summary") or {}
    today_count = int(summary.get("today_fixtures_count") or run.get("discovery", {}).get("fixture_count") or 0)
    today_status = str(summary.get("today_prediction_status") or "")
    missing_yesterday = int(yesterday.get("waiting_result_count") or 0)

    safety_violations = [key for key, expected in SAFETY_LABELS.items() if run.get(key) is not expected]
    audit_warnings = (
        audit.get("wde_retrained_with_historical_csv")
        or audit.get("historical_csv_promoted_from_staging")
        or audit.get("ecse_oddalerts_mode") == "production"
        or audit.get("oddalerts_csv_odds_snapshots_used")
    )
    if safety_violations or audit_warnings:
        return "DATA_AUDIT_WARNING"

    if today_count > 0:
        with_wde = sum(1 for p in today_predictions if p.get("wde"))
        if with_wde == 0 or today_status in ("missing_predictions", ""):
            return "TODAY_PREDICTIONS_MISSING"

    if missing_yesterday > 0:
        return "WAITING_FOR_RESULTS"

    return "NO_ACTION_REQUIRED"


def _data_usage_audit_section(audit: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "WDE_RETRAINED": bool(audit.get("wde_retrained_with_historical_csv")),
        "HISTORICAL_CSV_PROMOTED": bool(audit.get("historical_csv_promoted_from_staging")),
        "ODDALERTS_ECSE_PRODUCTION": audit.get("ecse_oddalerts_mode") == "production",
        "ODDALERTS_ECSE_SHADOW_ONLY": audit.get("ecse_oddalerts_mode") == "shadow"
        or audit.get("ODDALERTS_ECSE_SHADOW_ONLY") is True,
        "odds_sources_today": _odds_sources_today(predictions),
        "historical_csv_status": "promoted" if audit.get("historical_csv_promoted_from_staging") else "staged_only",
        "oddalerts_shadow_row_count": audit.get("oddalerts_shadow_row_count"),
        "ecse_oddalerts_mode": audit.get("ecse_oddalerts_mode"),
        "oddalerts_csv_snapshot_count": audit.get("oddalerts_csv_snapshot_count", 0),
    }


def _render_markdown(panel: dict[str, Any]) -> str:
    status = panel["owner_daily_status"]
    today_rows = panel["today_fixtures"]
    best_tip = panel["best_tip_candidate"]
    yesterday = panel["yesterday_evaluation"]
    audit = panel["data_usage_audit"]

    lines = [
        f"# Owner Daily Control Panel — {status['date']}",
        "",
        "Owner/internal only. Built from existing artifacts — no production logic changes.",
        "",
        "## A) Owner Daily Status",
        "",
        f"- **Date:** {status['date']}",
        f"- **Final recommendation:** `{status['final_recommendation']}`",
        f"- **Today prediction status:** `{status['today_prediction_status']}`",
        f"- **Yesterday evaluation status:** `{status['yesterday_evaluation_status']}`",
        f"- **Result refresh status:** `{status['result_refresh_status']}`",
        f"- **Safety status:** `{status['safety_status']}`",
        "",
        "## B) Today Fixtures",
        "",
    ]

    if not today_rows:
        lines.append("_No fixtures today._")
    else:
        lines.append(
            "| Fixture ID | Kickoff | Match | Readiness | WDE | ECSE | Odds | Confidence | Tier | Note |"
        )
        lines.append("|------------|---------|-------|-----------|-----|------|------|------------|------|------|")
        for r in today_rows:
            lines.append(
                f"| {r.get('fixture_id')} | {r.get('kickoff') or '—'} | "
                f"{r.get('home_team')} vs {r.get('away_team')} | {r.get('prediction_readiness')} | "
                f"{'yes' if r.get('wde_available') else 'no'} | "
                f"{'yes' if r.get('ecse_available') else 'no'} | "
                f"{r.get('odds_source') or '—'} | {r.get('confidence') or '—'} | "
                f"{r.get('tier') or '—'} | {r.get('best_owner_note')} |"
            )

    lines.extend(["", "## C) Best Tip Candidate", ""])
    if best_tip.get("status") == "NO_BEST_TIP_AVAILABLE":
        lines.append("**NO_BEST_TIP_AVAILABLE**")
    else:
        lines.extend(
            [
                f"- **Fixture:** {best_tip.get('fixture')} (id {best_tip.get('fixture_id')})",
                f"- **Market:** {best_tip.get('market')}",
                f"- **Pick:** `{best_tip.get('pick')}`",
                f"- **Confidence:** {best_tip.get('confidence')} (source: {best_tip.get('confidence_source')})",
                f"- **Tier:** {best_tip.get('tier') or '—'}",
                f"- **Reasons:** {', '.join(best_tip.get('reasons') or []) or '—'}",
            ]
        )

    lines.extend(
        [
            "",
            "## D) Yesterday Evaluation",
            "",
            f"- **Total fixtures:** {yesterday['total_fixtures']}",
            f"- **Evaluated:** {yesterday['evaluated_count']}",
            f"- **Missing:** {yesterday['missing_count']}",
            "",
            "### Evaluated results",
            "",
        ]
    )
    if yesterday["evaluated_results"]:
        for r in yesterday["evaluated_results"]:
            lines.append(f"- {r['fixture']}: **{r['final_score']}**")
    else:
        lines.append("_None evaluated yet._")

    lines.extend(["", "### Hit / miss summary", ""])
    for market, counts in yesterday["hit_miss_summary"].items():
        lines.append(f"- **{market}:** hits={counts['hits']} misses={counts['misses']} unknown={counts['unknown']}")

    lines.extend(["", "### Missing fixtures", ""])
    if yesterday["missing_fixtures"]:
        for r in yesterday["missing_fixtures"]:
            lines.append(f"- {r['fixture']} (kickoff {r.get('kickoff') or '—'})")
    else:
        lines.append("_None — all results available._")

    lines.extend(
        [
            "",
            "## E) Data Usage Audit",
            "",
            f"- **WDE_RETRAINED:** `{audit['WDE_RETRAINED']}`",
            f"- **HISTORICAL_CSV_PROMOTED:** `{audit['HISTORICAL_CSV_PROMOTED']}`",
            f"- **ODDALERTS_ECSE_PRODUCTION:** `{audit['ODDALERTS_ECSE_PRODUCTION']}`",
            f"- **ODDALERTS_ECSE_SHADOW_ONLY:** `{audit['ODDALERTS_ECSE_SHADOW_ONLY']}`",
            f"- **Odds sources today:** {', '.join(audit['odds_sources_today']) or '—'}",
            f"- **Historical CSV status:** `{audit['historical_csv_status']}`",
            f"- **ECSE OddAlerts mode:** `{audit.get('ecse_oddalerts_mode', '—')}`",
        ]
    )
    shadow_count = audit.get("oddalerts_shadow_row_count")
    if shadow_count is not None:
        lines.append(f"- **OddAlerts shadow row count:** {shadow_count}")
    else:
        lines.append("- **OddAlerts shadow row count:** _not in source artifacts_")

    lines.extend(
        [
            "",
            "## F) Action Required",
            "",
            f"**`{panel['action_required']}`**",
            "",
            "## Safety labels",
            "",
        ]
    )
    for key, value in SAFETY_LABELS.items():
        lines.append(f"- **{key}:** `{str(value).lower()}`")

    return "\n".join(lines)


@dataclass
class ControlPanelResult:
    phase: str = PHASE
    process_date: str = ""
    owner_daily_status: dict[str, Any] = field(default_factory=dict)
    today_fixtures: list[dict[str, Any]] = field(default_factory=list)
    best_tip_candidate: dict[str, Any] = field(default_factory=dict)
    yesterday_evaluation: dict[str, Any] = field(default_factory=dict)
    data_usage_audit: dict[str, Any] = field(default_factory=dict)
    action_required: ActionRequired = ""
    recommendation: str = ""
    md_path: str = ""
    json_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "process_date": self.process_date,
                "owner_daily_status": self.owner_daily_status,
                "today_fixtures": self.today_fixtures,
                "best_tip_candidate": self.best_tip_candidate,
                "yesterday_evaluation": self.yesterday_evaluation,
                "data_usage_audit": self.data_usage_audit,
                "action_required": self.action_required,
                "recommendation": self.recommendation,
                "md_path": self.md_path,
                "json_path": self.json_path,
            }
        )


def build_owner_daily_control_panel(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
) -> ControlPanelResult:
    process_date = resolve_process_date(date_arg, timezone)
    yesterday_date = yesterday_of(process_date)

    run_path = daily_report_json_path(process_date)
    run = _load_json(run_path)
    if not run:
        raise FileNotFoundError(f"Missing required artifact: {run_path}")

    pred_path = predictions_artifact(process_date)
    pred_payload = _load_json(pred_path) or {}
    predictions = pred_payload.get("predictions") or run.get("predictions", {}).get("predictions") or []

    yest_path = yesterday_artifact(yesterday_date)
    yesterday = _load_json(yest_path) or run.get("yesterday_evaluation") or {}
    audit = run.get("data_audit") or {}
    summary = run.get("owner_daily_summary") or {}

    recommendation = str(run.get("recommendation") or summary.get("final_recommendation") or "")
    today_fixtures = _today_fixture_rows(predictions)
    best_tip = _pick_best_tip_candidate(predictions)
    yesterday_section = _yesterday_section(yesterday)
    audit_section = _data_usage_audit_section(audit, predictions)
    action_required = _derive_action_required(
        run=run,
        yesterday=yesterday,
        today_predictions=predictions,
        audit=audit,
    )

    owner_daily_status = {
        "date": process_date.isoformat(),
        "final_recommendation": recommendation,
        "today_prediction_status": summary.get("today_prediction_status") or "unknown",
        "yesterday_evaluation_status": _yesterday_evaluation_status(yesterday),
        "result_refresh_status": yesterday.get("result_refresh_status") or "unknown",
        "safety_status": _safety_status(run),
    }

    result = ControlPanelResult(
        process_date=process_date.isoformat(),
        owner_daily_status=owner_daily_status,
        today_fixtures=today_fixtures,
        best_tip_candidate=best_tip,
        yesterday_evaluation=yesterday_section,
        data_usage_audit=audit_section,
        action_required=action_required,
        recommendation=recommendation,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = control_panel_md_path(process_date)
    json_path = control_panel_json_path(process_date)

    panel_dict = result.to_dict()
    json_path.write_text(json.dumps(panel_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_markdown(panel_dict), encoding="utf-8")

    result.md_path = str(md_path)
    result.json_path = str(json_path)
    return result
