"""Owner-only post-match evaluation for knockout WDE/ECSE/manual predictions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.accuracy.evaluator import actual_1x2, actual_over_under
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import append_jsonl_rows
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR, PHASE, REPORTS_DIR
from worldcup_predictor.owner_manual_exact.resolver import _date_tag
from worldcup_predictor.owner_manual_exact.score_engine import markets_from_odds
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date
from worldcup_predictor.owner_predict_eval.db_helpers import load_fixture_result
from worldcup_predictor.owner_predict_eval.yesterday_eval import _is_finished_status

logger = logging.getLogger(__name__)

EVAL_PHASE = "OWNER-KNOCKOUT-PREDICTION-EVAL"
EVAL_JSONL_DIR = Path("data") / "evaluation"

CONFIDENCE_BANDS: list[tuple[str, float | None, float | None]] = [
    ("80+", 80.0, None),
    ("70-79", 70.0, 79.99),
    ("60-69", 60.0, 69.99),
    ("50-59", 50.0, 59.99),
    ("below_50", None, 49.99),
]

SAFETY_LABELS: dict[str, bool] = {
    "PUBLIC_PUBLISH": False,
    "WDE_RETRAINED": False,
    "EGIE_RETRAINED": False,
    "HISTORICAL_CSV_PROMOTED": False,
    "FRONTEND_PUBLISH": False,
    "PUBLIC_ARCHIVE_PUBLISH": False,
    "OWNER_ONLY": True,
    "ODDALERTS_ECSE_PRODUCTION": False,
    "ODDALERTS_ECSE_SHADOW_ONLY": True,
}


def with_safety_labels(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, **SAFETY_LABELS}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _normalize_scoreline(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).replace(":", "-").strip()


def _parse_scoreline(scoreline: str) -> tuple[int, int] | None:
    text = _normalize_scoreline(scoreline)
    if not text or "-" not in text:
        return None
    parts = text.split("-", 1)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _scorelines_from_rows(rows: list[Any]) -> list[str]:
    out: list[str] = []
    for item in rows:
        if isinstance(item, dict):
            sl = item.get("scoreline") or item.get("label")
            if sl:
                out.append(_normalize_scoreline(str(sl)) or str(sl))
        elif item:
            out.append(_normalize_scoreline(str(item)) or str(item))
    return out


def _eval_topn(actual: str, top1: str | None, top3: list[str]) -> dict[str, Any]:
    top1_n = _normalize_scoreline(top1)
    top3_n = [_normalize_scoreline(s) or s for s in top3]
    return {
        "exact_top1_hit": top1_n == actual,
        "exact_top3_hit": actual in top3_n,
    }


def _eval_market_picks(
    *,
    pick_1x2: str | None,
    pick_btts: str | None,
    pick_ou25: str | None,
    hg: int,
    ag: int,
) -> dict[str, Any]:
    actual_x2 = actual_1x2(hg, ag)
    actual_ou = actual_over_under(hg, ag)
    actual_btts = "yes" if hg > 0 and ag > 0 else "no"
    return {
        "one_x_two_hit": pick_1x2 == actual_x2 if pick_1x2 else None,
        "btts_hit": pick_btts == actual_btts if pick_btts else None,
        "over_under_2_5_hit": pick_ou25 == actual_ou if pick_ou25 else None,
        "actual_1x2": actual_x2,
        "actual_btts": actual_btts,
        "actual_over_under_2_5": actual_ou,
    }


def _confidence_band(confidence: float) -> str:
    for label, lo, hi in CONFIDENCE_BANDS:
        if lo is not None and hi is not None and lo <= confidence <= hi:
            return label
        if lo is not None and hi is None and confidence >= lo:
            return label
        if lo is None and hi is not None and confidence <= hi:
            return label
    return "below_50"


def _fixture_status(conn, fixture_id: int) -> str:
    row = conn.execute(
        "SELECT status FROM fixtures WHERE fixture_id=? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return str(row["status"] if row else "").upper()


def _load_predictions_artifact(process_date: date) -> dict[str, Any]:
    path = ARTIFACTS_DIR / f"manual_owner_exact_score_predictions_{_date_tag(process_date)}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing predictions artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _manual_poisson_pick(pred: dict[str, Any]) -> dict[str, Any]:
    odds_1x2 = pred.get("odds_1x2") or {}
    btts_odds = pred.get("btts_odds") or {}
    markets = markets_from_odds(odds_1x2, btts_odds)
    top_scores = markets.get("top_scores") or []
    top1 = top_scores[0]["scoreline"] if top_scores else None
    top3 = [s["scoreline"] for s in top_scores[:3]]
    return {
        "model": "manual_poisson",
        "exact_top1": top1,
        "exact_top3": top3,
        "pick_1x2": markets.get("pick_1x2"),
        "pick_btts": markets.get("pick_btts"),
        "pick_ou25": markets.get("pick_ou25"),
        "present": True,
    }


def _wde_shadow_pick(pred: dict[str, Any]) -> dict[str, Any]:
    shadow = pred.get("wde_shadow") or {}
    if not shadow:
        return {"model": "wde_shadow", "present": False, "label": "SHADOW_ONLY"}
    return {
        "model": "wde_shadow",
        "present": True,
        "label": shadow.get("label") or "SHADOW_ONLY",
        "pick_1x2": shadow.get("1x2"),
        "pick_btts": shadow.get("btts"),
        "pick_ou25": shadow.get("ou25"),
        "exact_top1": None,
        "exact_top3": [],
        "1x2_confidence": shadow.get("1x2_confidence"),
        "btts_confidence": shadow.get("btts_confidence"),
        "ou25_confidence": shadow.get("ou25_confidence"),
    }


def _wde_production_pick(pred: dict[str, Any]) -> dict[str, Any]:
    wde = pred.get("wde") or {}
    scoreline = _normalize_scoreline(wde.get("predicted_scoreline"))
    top3: list[str] = []
    if scoreline:
        top3 = [scoreline]
    return {
        "model": "wde_production",
        "present": bool(wde),
        "exact_top1": scoreline,
        "exact_top3": top3,
        "pick_1x2": wde.get("predicted_1x2"),
        "pick_btts": wde.get("btts_pick"),
        "pick_ou25": wde.get("predicted_over_under_2_5"),
        "confidence": wde.get("confidence_score"),
    }


def _ecse_production_pick(pred: dict[str, Any]) -> dict[str, Any]:
    ecse = pred.get("ecse_production") or {}
    top1 = _normalize_scoreline(ecse.get("top_1_score"))
    top3 = _scorelines_from_rows(ecse.get("top_3_scores") or [])
    picks: dict[str, Any] = {}
    if top1:
        parsed = _parse_scoreline(top1)
        if parsed:
            hg, ag = parsed
            picks = {
                "pick_1x2": actual_1x2(hg, ag),
                "pick_btts": "yes" if hg > 0 and ag > 0 else "no",
                "pick_ou25": actual_over_under(hg, ag),
            }
    return {
        "model": "ecse_production",
        "present": bool(ecse),
        "exact_top1": top1,
        "exact_top3": top3,
        "confidence": ecse.get("confidence_score"),
        **picks,
    }


def _evaluate_model_pick(model: dict[str, Any], actual_score: str, hg: int, ag: int) -> dict[str, Any]:
    if not model.get("present"):
        return {"status": "NO_PREDICTION", "model": model.get("model")}
    exact = {}
    if model.get("exact_top1"):
        exact = _eval_topn(actual_score, model.get("exact_top1"), model.get("exact_top3") or [])
    else:
        exact = {"exact_top1_hit": None, "exact_top3_hit": None}
    markets = _eval_market_picks(
        pick_1x2=model.get("pick_1x2"),
        pick_btts=model.get("pick_btts"),
        pick_ou25=model.get("pick_ou25"),
        hg=hg,
        ag=ag,
    )
    out: dict[str, Any] = {
        "status": "EVALUATED",
        "model": model.get("model"),
        "label": model.get("label"),
        **exact,
        **markets,
    }
    if model.get("model") == "wde_shadow":
        out["shadow_only"] = True
        out["production_counted"] = False
    return out


def _wde_shadow_comparison(pred: dict[str, Any], hg: int, ag: int) -> dict[str, Any]:
    shadow = pred.get("wde_shadow") or {}
    if not shadow:
        return {"status": "NO_SHADOW", "label": "SHADOW_ONLY"}
    model = _wde_shadow_pick(pred)
    eval_row = _evaluate_model_pick(model, f"{hg}-{ag}", hg, ag)
    production = {
        "pick_1x2": pred.get("pick_1x2"),
        "pick_btts": pred.get("pick_btts"),
        "pick_ou25": pred.get("pick_ou25"),
    }
    prod_eval = _eval_market_picks(
        pick_1x2=production["pick_1x2"],
        pick_btts=production["pick_btts"],
        pick_ou25=production["pick_ou25"],
        hg=hg,
        ag=ag,
    )
    shadow_agrees_production = (
        shadow.get("1x2") == production["pick_1x2"]
        and shadow.get("btts") == production["pick_btts"]
        and shadow.get("ou25") == production["pick_ou25"]
    )
    shadow_beats_production = (
        (eval_row.get("one_x_two_hit") and not prod_eval.get("one_x_two_hit"))
        or (eval_row.get("btts_hit") and not prod_eval.get("btts_hit"))
        or (eval_row.get("over_under_2_5_hit") and not prod_eval.get("over_under_2_5_hit"))
    )
    return {
        "status": "COMPARED",
        "label": shadow.get("label") or "SHADOW_ONLY",
        "shadow_only": True,
        "shadow_agrees_production": shadow_agrees_production,
        "shadow_beats_production_on_market": shadow_beats_production,
        "shadow_evaluation": eval_row,
        "production_evaluation": prod_eval,
    }


def _try_refresh_result_from_api(
    conn,
    fixture_id: int,
    *,
    settings: Settings,
) -> dict[str, Any] | None:
    api = ApiFootballClient(settings)
    if not api.is_configured:
        return None
    try:
        call = api._safe_get(
            "fixtures",
            {"id": fixture_id},
            placeholder_factory=lambda: None,
            force_refresh=True,
        )
        if not call.data:
            return None
        item = call.data[0] if isinstance(call.data, list) else call.data
        if not isinstance(item, dict):
            return None
        fixture = parse_api_fixture_item(item)
        if fixture.home_goals is None or fixture.away_goals is None:
            return None
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        repo.upsert_fixture_result(fixture, outcome_source=call.source or "api-football")
        return load_fixture_result(conn, fixture_id)
    except Exception as exc:
        logger.warning("API result refresh failed for fixture %s: %s", fixture_id, exc)
        return None


def _resolve_final_result(
    conn,
    fixture_id: int,
    *,
    settings: Settings,
    refresh_api: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    result = load_fixture_result(conn, fixture_id)
    status = _fixture_status(conn, fixture_id)

    if result and result.get("home_goals") is not None and result.get("away_goals") is not None:
        if _is_finished_status(status):
            return result, status

    if refresh_api:
        refreshed = _try_refresh_result_from_api(conn, fixture_id, settings=settings)
        if refreshed:
            status = _fixture_status(conn, fixture_id)
            if _is_finished_status(status):
                return refreshed, status

    return result if result else None, status


def _accuracy_rate(hits: list[bool | None]) -> float | None:
    valid = [h for h in hits if h is not None]
    if not valid:
        return None
    return round(sum(1 for h in valid if h) / len(valid), 4)


def _aggregate_model_metrics(rows: list[dict[str, Any]], model_key: str) -> dict[str, Any]:
    evals = [r.get("model_comparison", {}).get(model_key) or {} for r in rows]
    evaluated = [e for e in evals if e.get("status") == "EVALUATED"]
    return {
        "evaluated_count": len(evaluated),
        "exact_top1_accuracy": _accuracy_rate([e.get("exact_top1_hit") for e in evaluated]),
        "exact_top3_accuracy": _accuracy_rate([e.get("exact_top3_hit") for e in evaluated]),
        "one_x_two_accuracy": _accuracy_rate([e.get("one_x_two_hit") for e in evaluated]),
        "btts_accuracy": _accuracy_rate([e.get("btts_hit") for e in evaluated]),
        "over_under_2_5_accuracy": _accuracy_rate([e.get("over_under_2_5_hit") for e in evaluated]),
    }


def _calibration_summary(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    bands: dict[str, dict[str, Any]] = {}
    overconfident: list[dict[str, Any]] = []
    underconfident: list[dict[str, Any]] = []

    for row in fixtures:
        if row.get("evaluation_status") != "EVALUATED":
            continue
        conf = float(row.get("confidence") or 0)
        band = _confidence_band(conf)
        bucket = bands.setdefault(
            band,
            {"band": band, "count": 0, "exact_top1_hits": 0, "exact_top1_misses": 0},
        )
        bucket["count"] += 1
        hit = bool(row.get("production_evaluation", {}).get("exact_top1_hit"))
        if hit:
            bucket["exact_top1_hits"] += 1
        else:
            bucket["exact_top1_misses"] += 1

        if conf >= 70 and not hit:
            overconfident.append(
                {
                    "fixture_id": row.get("fixture_id"),
                    "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                    "confidence": conf,
                    "predicted": row.get("production_evaluation", {}).get("exact_top1_predicted"),
                    "actual": row.get("final_score"),
                }
            )
        if conf < 60 and hit:
            underconfident.append(
                {
                    "fixture_id": row.get("fixture_id"),
                    "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                    "confidence": conf,
                    "predicted": row.get("production_evaluation", {}).get("exact_top1_predicted"),
                    "actual": row.get("final_score"),
                }
            )

    for bucket in bands.values():
        total = bucket["count"] or 1
        bucket["exact_top1_accuracy"] = round(bucket["exact_top1_hits"] / total, 4)

    conf_correct = [
        float(r["confidence"])
        for r in fixtures
        if r.get("evaluation_status") == "EVALUATED"
        and r.get("production_evaluation", {}).get("exact_top1_hit")
    ]
    conf_wrong = [
        float(r["confidence"])
        for r in fixtures
        if r.get("evaluation_status") == "EVALUATED"
        and r.get("production_evaluation", {}).get("exact_top1_hit") is False
    ]

    return {
        "bands": list(bands.values()),
        "avg_confidence_on_correct": round(sum(conf_correct) / len(conf_correct), 2) if conf_correct else None,
        "avg_confidence_on_wrong": round(sum(conf_wrong) / len(conf_wrong), 2) if conf_wrong else None,
        "high_confidence_miss_count": len(overconfident),
        "low_confidence_hit_count": len(underconfident),
        "overconfident_misses": overconfident,
        "underconfident_hits": underconfident,
    }


def artifact_json_path(process_date: date) -> Path:
    return ARTIFACTS_DIR / f"owner_knockout_prediction_evaluation_{_date_tag(process_date)}.json"


def report_md_path(process_date: date) -> Path:
    return REPORTS_DIR / f"owner_knockout_prediction_evaluation_{_date_tag(process_date)}.md"


def jsonl_path(process_date: date) -> Path:
    return EVAL_JSONL_DIR / f"owner_knockout_prediction_eval_{_date_tag(process_date)}.jsonl"


def _jsonl_dedupe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row.get("process_date"), int(row.get("fixture_id") or 0))


def _evaluate_fixture(
    pred: dict[str, Any],
    *,
    conn,
    settings: Settings,
    process_date: date,
    refresh_api: bool,
) -> dict[str, Any]:
    fid = int(pred["fixture_id"])
    audit = pred.get("source_audit") or {}
    row: dict[str, Any] = {
        "match_no": pred.get("match_no"),
        "fixture_id": fid,
        "home_team": pred.get("home_team"),
        "away_team": pred.get("away_team"),
        "kickoff_local": pred.get("kickoff_local"),
        "production_source": audit.get("production_source"),
        "exact_score_source": audit.get("exact_score_source"),
        "ecse_attached": audit.get("ecse_attached"),
        "wde_attached": audit.get("wde_attached"),
        "manual_fallback": audit.get("manual_fallback") or audit.get("fallback_used"),
        "confidence": pred.get("confidence"),
        "risk_badge": pred.get("risk_badge"),
        "wde_shadow_label": (pred.get("wde_shadow_status") or {}).get("label") or "SHADOW_ONLY",
    }

    result, status = _resolve_final_result(conn, fid, settings=settings, refresh_api=refresh_api)
    row["status"] = status

    if not result or result.get("home_goals") is None or result.get("away_goals") is None:
        row["evaluation_status"] = "WAITING_FOR_RESULT"
        return row

    if not _is_finished_status(status):
        row["evaluation_status"] = "WAITING_FOR_RESULT"
        return row

    hg = int(result["home_goals"])
    ag = int(result["away_goals"])
    actual_score = f"{hg}-{ag}"
    row["evaluation_status"] = "EVALUATED"
    row["final_score"] = actual_score
    row["result_source"] = str(result.get("outcome_source") or result.get("source") or "unknown")

    production_eval = {
        "exact_top1_predicted": pred.get("exact_top1"),
        "exact_top3_predicted": pred.get("exact_top3") or [],
        **_eval_topn(actual_score, pred.get("exact_top1"), pred.get("exact_top3") or []),
        **_eval_market_picks(
            pick_1x2=pred.get("pick_1x2"),
            pick_btts=pred.get("pick_btts"),
            pick_ou25=pred.get("pick_ou25"),
            hg=hg,
            ag=ag,
        ),
    }
    row["production_evaluation"] = production_eval

    ecse_model = _ecse_production_pick(pred)
    wde_model = _wde_production_pick(pred)
    shadow_model = _wde_shadow_pick(pred)
    poisson_model = _manual_poisson_pick(pred)

    row["model_comparison"] = {
        "ecse_production": _evaluate_model_pick(ecse_model, actual_score, hg, ag),
        "wde_production": _evaluate_model_pick(wde_model, actual_score, hg, ag),
        "wde_shadow": _evaluate_model_pick(shadow_model, actual_score, hg, ag),
        "manual_poisson": _evaluate_model_pick(poisson_model, actual_score, hg, ag),
    }
    row["wde_shadow_comparison"] = _wde_shadow_comparison(pred, hg, ag)
    row["evaluated_at"] = _utc_now_iso()
    row["process_date"] = process_date.isoformat()
    return row


@dataclass
class KnockoutEvalResult:
    phase: str = EVAL_PHASE
    process_date: str = ""
    fixture_count: int = 0
    evaluated_count: int = 0
    waiting_result_count: int = 0
    fixtures: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    model_comparison_summary: dict[str, Any] = field(default_factory=dict)
    calibration: dict[str, Any] = field(default_factory=dict)
    json_path: str = ""
    md_path: str = ""
    jsonl_path: str = ""
    jsonl_append: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "process_date": self.process_date,
                "fixture_count": self.fixture_count,
                "evaluated_count": self.evaluated_count,
                "waiting_result_count": self.waiting_result_count,
                "metrics": self.metrics,
                "model_comparison_summary": self.model_comparison_summary,
                "calibration": self.calibration,
                "json_path": self.json_path,
                "md_path": self.md_path,
                "jsonl_path": self.jsonl_path,
                "jsonl_append": self.jsonl_append,
                "fixtures": self.fixtures,
            }
        )


def _production_metrics(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [r for r in fixtures if r.get("evaluation_status") == "EVALUATED"]
    pe = [r.get("production_evaluation") or {} for r in evaluated]
    return {
        "exact_top1_accuracy": _accuracy_rate([p.get("exact_top1_hit") for p in pe]),
        "exact_top3_accuracy": _accuracy_rate([p.get("exact_top3_hit") for p in pe]),
        "one_x_two_accuracy": _accuracy_rate([p.get("one_x_two_hit") for p in pe]),
        "btts_accuracy": _accuracy_rate([p.get("btts_hit") for p in pe]),
        "over_under_2_5_accuracy": _accuracy_rate([p.get("over_under_2_5_hit") for p in pe]),
    }


def _write_reports(result: KnockoutEvalResult, process_date: date) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_JSONL_DIR.mkdir(parents=True, exist_ok=True)

    json_out = artifact_json_path(process_date)
    md_out = report_md_path(process_date)
    jsonl_out = jsonl_path(process_date)

    json_out.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    result.json_path = str(json_out)
    result.md_path = str(md_out)
    result.jsonl_path = str(jsonl_out)

    ledger_rows = [
        {
            "phase": EVAL_PHASE,
            "process_date": process_date.isoformat(),
            "fixture_id": r.get("fixture_id"),
            "match_no": r.get("match_no"),
            "evaluation_status": r.get("evaluation_status"),
            "final_score": r.get("final_score"),
            "production_source": r.get("production_source"),
            "production_evaluation": r.get("production_evaluation"),
            "model_comparison": r.get("model_comparison"),
            "confidence": r.get("confidence"),
            "risk_badge": r.get("risk_badge"),
            "evaluated_at": r.get("evaluated_at") or _utc_now_iso(),
            "OWNER_ONLY": True,
            "PUBLIC_PUBLISH": False,
        }
        for r in result.fixtures
        if r.get("evaluation_status") == "EVALUATED"
    ]
    result.jsonl_append = append_jsonl_rows(jsonl_out, ledger_rows, dedupe_key=_jsonl_dedupe_key)
    if not jsonl_out.exists():
        jsonl_out.write_text("", encoding="utf-8")

    m = result.metrics
    cal = result.calibration
    mc = result.model_comparison_summary
    lines = [
        f"# Owner Knockout Prediction Evaluation — {process_date.isoformat()}",
        "",
        f"Fixtures: **{result.fixture_count}** | Evaluated: **{result.evaluated_count}** | Waiting: **{result.waiting_result_count}**",
        "",
        "## Production metrics",
        "",
        f"- Exact top-1 accuracy: **{m.get('exact_top1_accuracy')}**",
        f"- Exact top-3 accuracy: **{m.get('exact_top3_accuracy')}**",
        f"- 1X2 accuracy: **{m.get('one_x_two_accuracy')}**",
        f"- BTTS accuracy: **{m.get('btts_accuracy')}**",
        f"- O/U 2.5 accuracy: **{m.get('over_under_2_5_accuracy')}**",
        "",
        "## Model comparison",
        "",
        "| Model | Evaluated | Top-1 | Top-3 | 1X2 | BTTS | O/U 2.5 |",
        "|-------|-----------|-------|-------|-----|------|---------|",
    ]
    for key, label in (
        ("ecse_production", "ECSE production"),
        ("wde_production", "WDE production"),
        ("wde_shadow", "WDE shadow (SHADOW_ONLY)"),
        ("manual_poisson", "Manual Poisson"),
    ):
        s = mc.get(key) or {}
        lines.append(
            f"| {label} | {s.get('evaluated_count', 0)} | {s.get('exact_top1_accuracy')} | "
            f"{s.get('exact_top3_accuracy')} | {s.get('one_x_two_accuracy')} | "
            f"{s.get('btts_accuracy')} | {s.get('over_under_2_5_accuracy')} |"
        )

    lines.extend(
        [
            "",
            "## Confidence calibration",
            "",
            f"- Avg confidence on correct top-1: **{cal.get('avg_confidence_on_correct')}**",
            f"- Avg confidence on wrong top-1: **{cal.get('avg_confidence_on_wrong')}**",
            f"- High-confidence misses (≥70): **{cal.get('high_confidence_miss_count')}**",
            f"- Low-confidence hits (<60): **{cal.get('low_confidence_hit_count')}**",
            "",
            "| Band | Count | Top-1 accuracy |",
            "|------|-------|----------------|",
        ]
    )
    for band in cal.get("bands") or []:
        lines.append(
            f"| {band.get('band')} | {band.get('count')} | {band.get('exact_top1_accuracy')} |"
        )

    lines.extend(
        [
            "",
            "## Per-fixture",
            "",
            "| Match | Final | Prod T1 | Prod T3 | 1X2 | BTTS | O/U | Status |",
            "|-------|-------|---------|---------|-----|------|-----|--------|",
        ]
    )
    for r in result.fixtures:
        if r.get("evaluation_status") == "WAITING_FOR_RESULT":
            lines.append(
                f"| {r.get('home_team')} vs {r.get('away_team')} | — | — | — | — | — | — | WAITING_FOR_RESULT |"
            )
            continue
        pe = r.get("production_evaluation") or {}
        lines.append(
            f"| {r.get('home_team')} vs {r.get('away_team')} | {r.get('final_score')} | "
            f"{pe.get('exact_top1_hit')} | {pe.get('exact_top3_hit')} | {pe.get('one_x_two_hit')} | "
            f"{pe.get('btts_hit')} | {pe.get('over_under_2_5_hit')} | EVALUATED |"
        )

    lines.extend(
        [
            "",
            "## Safety labels",
            "",
            *[f"- **{k}:** `{v}`" for k, v in SAFETY_LABELS.items()],
            "",
            "**No public publish. No retrain. WDE shadow is comparison-only.**",
        ]
    )
    md_out.write_text("\n".join(lines), encoding="utf-8")


def evaluate_owner_knockout_predictions(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
    settings: Settings | None = None,
    refresh_api: bool = True,
) -> KnockoutEvalResult:
    settings = settings or get_settings()
    process_date = resolve_process_date(date_arg, timezone)
    predictions_payload = _load_predictions_artifact(process_date)
    preds = predictions_payload.get("predictions") or []

    conn = connect(settings.sqlite_path)
    fixture_rows: list[dict[str, Any]] = []
    evaluated = 0
    waiting = 0

    for pred in preds:
        if not pred.get("fixture_id"):
            waiting += 1
            fixture_rows.append(
                {
                    "match_no": pred.get("match_no"),
                    "fixture_id": pred.get("fixture_id"),
                    "home_team": pred.get("home_team"),
                    "away_team": pred.get("away_team"),
                    "evaluation_status": "WAITING_FOR_RESULT",
                    "reason": "no_fixture_id",
                }
            )
            continue
        row = _evaluate_fixture(pred, conn=conn, settings=settings, process_date=process_date, refresh_api=refresh_api)
        if row.get("evaluation_status") == "EVALUATED":
            evaluated += 1
        else:
            waiting += 1
        fixture_rows.append(row)

    fixture_rows.sort(key=lambda r: (r.get("match_no") or 0, r.get("fixture_id") or 0))

    result = KnockoutEvalResult(
        process_date=process_date.isoformat(),
        fixture_count=len(fixture_rows),
        evaluated_count=evaluated,
        waiting_result_count=waiting,
        fixtures=fixture_rows,
        metrics=_production_metrics(fixture_rows),
        model_comparison_summary={
            "ecse_production": _aggregate_model_metrics(fixture_rows, "ecse_production"),
            "wde_production": _aggregate_model_metrics(fixture_rows, "wde_production"),
            "wde_shadow": _aggregate_model_metrics(fixture_rows, "wde_shadow"),
            "manual_poisson": _aggregate_model_metrics(fixture_rows, "manual_poisson"),
        },
        calibration=_calibration_summary(fixture_rows),
    )

    _write_reports(result, process_date)
    return result


def load_evaluation_artifact(process_date: date) -> dict[str, Any] | None:
    path = artifact_json_path(process_date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
