#!/usr/bin/env python3
"""Full production multi-engine match report — read DB + run all active engines."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.explainability.prediction_explainability_engine import build_prediction_explainability
from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.unified_hybrid.engine import UnifiedHybridPredictionEngine

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FIXTURES = [
    (1565178, "Australia", "Egypt"),
    (1565179, "Argentina", "Cape Verde Islands"),
    (1569870, "Paraguay", "France"),
]


def _pct(p: float | None) -> str:
    if p is None:
        return "—"
    return f"{float(p) * 100:.1f}%"


def _poisson_pmf(k: int, lam: float) -> float:
    lam = max(lam, 0.12)
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def _ou_prob(hl: float, al: float, line: float) -> dict[str, float]:
    over = 0.0
    for h in range(8):
        for a in range(8):
            p = _poisson_pmf(h, hl) * _poisson_pmf(a, al)
            if h + a > line:
                over += p
    over = min(max(over, 0.0), 1.0)
    return {"over": over, "under": 1.0 - over}


def _btts_prob(hl: float, al: float) -> dict[str, float]:
    p00 = _poisson_pmf(0, hl) * _poisson_pmf(0, al)
    p_h0 = (1 - _poisson_pmf(0, hl)) * _poisson_pmf(0, al)
    p_0a = _poisson_pmf(0, hl) * (1 - _poisson_pmf(0, al))
    p_both = 1 - p00 - p_h0 - p_0a
    p_both = min(max(p_both, 0.0), 1.0)
    return {"yes": p_both, "no": 1.0 - p_both}


def _dc_probs(p1: float, px: float, p2: float) -> dict[str, float]:
    return {"1X": p1 + px, "12": p1 + p2, "X2": px + p2}


def _risk_badge(conf: float | None) -> str:
    if conf is None:
        return "MEDIUM_RISK"
    if conf >= 70:
        return "LOW_RISK"
    if conf >= 50:
        return "MEDIUM_RISK"
    return "HIGH_RISK"


def _serialize(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return _serialize(asdict(obj))
    if hasattr(obj, "value"):
        return obj.value
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def _load_latest_odds(conn, fixture_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return {"snapshot_at": row["snapshot_at"], "payload": payload}


def _load_xg(conn, fixture_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT snapshot_at, payload_json FROM xg_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        return {"snapshot_at": row["snapshot_at"], "payload": json.loads(row["payload_json"])}
    except (json.JSONDecodeError, TypeError):
        return {}


def _wde_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    detailed = payload.get("detailed_markets") or {}
    ext = payload.get("extended_markets") or {}
    return {
        "one_x_two": payload.get("one_x_two") or detailed.get("match_winner"),
        "over_under": payload.get("over_under") or detailed.get("over_under_25"),
        "btts": ext.get("btts") or detailed.get("btts"),
        "scoreline_candidates": payload.get("scoreline_candidates") or [],
        "confidence_score": payload.get("confidence_score") or payload.get("confidence"),
        "risk_level": payload.get("risk_level"),
        "detailed_markets": detailed,
        "extended_markets": ext,
        "metadata": payload.get("metadata") or {},
        "adaptive_confidence": payload.get("adaptive_confidence"),
    }


def _model_disagreement(wde_1x2: str | None, ecse_top1: str | None, hybrid_1x2: str | None) -> dict[str, Any]:
    def lean(score: str | None) -> str | None:
        if not score or "-" not in score:
            return wde_1x2
        try:
            h, a = map(int, score.replace(":", "-").split("-", 1))
            if h > a:
                return "home_win"
            if h < a:
                return "away_win"
            return "draw"
        except ValueError:
            return None

    ecse_lean = lean(ecse_top1)
    picks = {"wde": wde_1x2, "ecse": ecse_lean, "hybrid": hybrid_1x2}
    unique = {v for v in picks.values() if v}
    return {"picks": picks, "consensus": len(unique) <= 1, "disagreement_count": max(0, len(unique) - 1)}


def build_match_report(fixture_id: int, settings) -> dict[str, Any]:
    conn = connect(settings.sqlite_path)
    try:
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fixture_id,)).fetchone()
        fixture_row = dict(fx) if fx else {}
        odds = _load_latest_odds(conn, fixture_id)
        xg = _load_xg(conn, fixture_id)

        ecse_db = get_snapshot(conn, fixture_id)
        ecse_fresh = build_ecse_live_prediction(conn, fixture_id, fixture_row)
        ecse = ecse_fresh or ecse_db or {}

        from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore

        wde_payload = WorldcupPredictionStore(settings).get(fixture_id) or {}
        if not wde_payload:
            row = conn.execute(
                "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
                (fixture_id,),
            ).fetchone()
            if row:
                try:
                    wde_payload = json.loads(row["payload_json"])
                    wde_payload["stored_at"] = row["predicted_at"]
                except json.JSONDecodeError:
                    pass

        wde_parsed = _wde_from_payload(wde_payload)
    finally:
        conn.close()

    pipeline = PredictPipeline(settings, competition_key="world_cup_2026").run(fixture_id, record_history=False)
    pred = pipeline.prediction if pipeline.success else None
    intel = pipeline.intelligence_report
    spec = pipeline.specialist_report

    explain = None
    if pred and intel:
        try:
            explain = build_prediction_explainability(pred, intel, spec)
        except Exception as exc:
            explain = {"error": str(exc)}

    hybrid = None
    try:
        engine = UnifiedHybridPredictionEngine(settings)
        if engine.is_enabled() or engine.admin_preview_allowed():
            out = engine.predict(fixture_id, competition_key="world_cup_2026", include_compare=True)
            hybrid = _serialize(out)
    except Exception as exc:
        hybrid = {"error": str(exc)}

    goal_timing = None
    try:
        goal_timing = GoalTimingPredictionService(settings).predict_fixture(
            fixture_id, persist=False, competition_key="world_cup_2026"
        )
    except Exception as exc:
        goal_timing = {"error": str(exc)}

    hl = ecse.get("lambda_home")
    al = ecse.get("lambda_away")
    if hl is None and ecse.get("raw_features"):
        rf = ecse.get("raw_features") or {}
        lam = rf.get("lambda_features") or {}
        hl = lam.get("lambda_home")
        al = lam.get("lambda_away")

    derived: dict[str, Any] = {}
    if hl is not None and al is not None:
        hl, al = float(hl), float(al)
        derived["expected_goals"] = {"home": hl, "away": al, "diff": round(hl - al, 3)}
        derived["over_under"] = {
            f"over_{line}": _ou_prob(hl, al, line) for line in (0.5, 1.5, 2.5, 3.5, 4.5)
        }
        derived["btts"] = _btts_prob(hl, al)
        oxt = wde_parsed.get("one_x_two") or {}
        p1 = float(oxt.get("home") or oxt.get("probability_home") or 0.33)
        px = float(oxt.get("draw") or oxt.get("probability_draw") or 0.33)
        p2 = float(oxt.get("away") or oxt.get("probability_away") or 0.33)
        if oxt.get("selection"):
            sel = str(oxt["selection"])
            if sel == "home_win":
                p1, px, p2 = max(p1, 0.5), px * 0.8, p2 * 0.8
            elif sel == "away_win":
                p2, px, p1 = max(p2, 0.5), px * 0.8, p1 * 0.8
        s = p1 + px + p2 or 1
        derived["double_chance"] = _dc_probs(p1 / s, px / s, p2 / s)

    top10 = ecse.get("top_10_scorelines") or []
    if isinstance(top10, str):
        try:
            top10 = json.loads(top10)
        except json.JSONDecodeError:
            top10 = []

    wde_1x2 = None
    if pred:
        wde_1x2 = pred.one_x_two.selection
    elif wde_parsed.get("one_x_two"):
        wde_1x2 = wde_parsed["one_x_two"].get("selection")

    hybrid_1x2 = None
    if isinstance(hybrid, dict):
        m = hybrid.get("markets") or {}
        block = m.get("1x2") or {}
        hybrid_1x2 = block.get("selection") or block.get("fused_selection")

    conf = pred.confidence_score if pred else wde_parsed.get("confidence_score")
    if conf is not None:
        try:
            conf = float(conf)
            if conf <= 1:
                conf *= 100
        except (TypeError, ValueError):
            conf = None

    summary = {
        "final_prediction_summary": {
            "predicted_winner_90min": wde_1x2 or hybrid_1x2,
            "best_exact_score": ecse.get("top_1_score") or (top10[0].get("scoreline") if top10 else None),
            "top_3_exact": ecse.get("top_3_scores") or [x.get("scoreline") for x in top10[:3]],
            "global_confidence_pct": conf,
            "risk_classification": _risk_badge(conf),
        },
        "safest_market": hybrid.get("best_tip") if isinstance(hybrid, dict) else None,
        "model_disagreement": _model_disagreement(wde_1x2, ecse.get("top_1_score"), hybrid_1x2),
    }

    return {
        "fixture_id": fixture_id,
        "home_team": fixture_row.get("home_team"),
        "away_team": fixture_row.get("away_team"),
        "kickoff_utc": fixture_row.get("kickoff_utc"),
        "status": fixture_row.get("status"),
        "data_sources": {
            "odds_snapshot_at": odds.get("snapshot_at"),
            "xg_snapshot_at": xg.get("snapshot_at"),
            "wde_source": wde_payload.get("cache_source") or "sqlite_stored",
            "ecse_source": ecse.get("prediction_source") or "ecse_snapshot",
        },
        "engines": {
            "wde_pipeline_success": pipeline.success,
            "wde_live_prediction": _serialize(pred) if pred else None,
            "wde_stored": wde_parsed,
            "ecse": {
                "top_10_exact_scores": top10,
                "top_1": ecse.get("top_1_score"),
                "top_3": ecse.get("top_3_scores"),
                "top_5": ecse.get("top_5_scores"),
                "lambda_home": hl,
                "lambda_away": al,
                "confidence_score": ecse.get("confidence_score"),
            },
            "unified_hybrid": hybrid,
            "goal_timing": goal_timing,
            "explainability": _serialize(explain) if explain else None,
        },
        "intelligence": _serialize(intel) if intel else None,
        "specialists": _serialize(spec) if spec else None,
        "derived_markets": derived,
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['home_team']} vs {report['away_team']}",
        "",
        f"- Fixture: `{report['fixture_id']}`",
        f"- Kickoff: `{report.get('kickoff_utc')}` | Status: `{report.get('status')}`",
        f"- Generated: {report.get('generated_at')}",
        "",
    ]
    ecse = report["engines"]["ecse"]
    lines += ["## Top 10 Exact Scores (ECSE)", "", "| Rank | Score | Prob |", "| --- | --- | --- |"]
    for i, row in enumerate(ecse.get("top_10_exact_scores") or [], 1):
        if isinstance(row, dict):
            lines.append(f"| {i} | {row.get('scoreline')} | {_pct(row.get('probability'))} |")
    lines.append("")

    dm = report.get("derived_markets") or {}
    if dm.get("expected_goals"):
        xg = dm["expected_goals"]
        lines += [
            "## Expected Goals",
            f"- Home xG: **{xg['home']}** | Away xG: **{xg['away']}** | Diff: **{xg['diff']}**",
            "",
        ]
    if dm.get("over_under"):
        lines += ["## Over/Under (Poisson from ECSE λ)", ""]
        for k, v in dm["over_under"].items():
            line = k.replace("over_", "")
            lines.append(f"- O/U {line}: Over {_pct(v['over'])} | Under {_pct(v['under'])}")
        lines.append("")
    if dm.get("btts"):
        lines += [f"## BTTS: Yes {_pct(dm['btts']['yes'])} | No {_pct(dm['btts']['no'])}", ""]
    if dm.get("double_chance"):
        dc = dm["double_chance"]
        lines += [f"## Double Chance: 1X {_pct(dc['1X'])} | 12 {_pct(dc['12'])} | X2 {_pct(dc['X2'])}", ""]

    wde = report["engines"].get("wde_live_prediction") or {}
    if wde:
        lines += [
            "## WDE / Pipeline (live run)",
            f"- 1X2: {wde.get('one_x_two', {}).get('selection')} ({_pct(wde.get('one_x_two', {}).get('probability'))})",
            f"- O/U 2.5: {wde.get('over_under', {}).get('selection')} ({_pct(wde.get('over_under', {}).get('probability'))})",
            f"- Confidence: {wde.get('confidence_score')}% | Risk: {wde.get('risk_level')}",
            "",
        ]
        cands = wde.get("scoreline_candidates") or []
        if cands:
            lines += ["### WDE Scoreline candidates", ""]
            for c in cands[:5]:
                lines.append(f"- {c.get('label', c)} {_pct(c.get('probability'))}")
            lines.append("")

    s = report["summary"]
    fps = s.get("final_prediction_summary") or {}
    lines += [
        "## Final Summary",
        f"- **Winner 90'**: {fps.get('predicted_winner_90min')}",
        f"- **Best exact score**: {fps.get('best_exact_score')}",
        f"- **Top 3**: {', '.join(fps.get('top_3_exact') or [])}",
        f"- **Global confidence**: {fps.get('global_confidence_pct')}%",
        f"- **Risk**: {fps.get('risk_classification')}",
        "",
        f"- **Model disagreement**: {json.dumps(s.get('model_disagreement'), ensure_ascii=False)}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-ids", nargs="*", type=int, default=[f[0] for f in FIXTURES])
    parser.add_argument("--output-dir", default="artifacts/full_match_reports")
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_reports = []
    md_parts = [f"# Full Production Match Reports\n\nGenerated: {datetime.now(timezone.utc).isoformat()}\n"]

    for fid in args.fixture_ids:
        print(f"Running full report for fixture {fid}...", flush=True)
        report = build_match_report(fid, settings)
        all_reports.append(report)
        md_parts.append(format_markdown(report))
        md_parts.append("\n---\n")

    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"full_production_report_{tag}.json"
    md_path = out_dir / f"FULL_PRODUCTION_MATCH_REPORT_{tag}.md"
    json_path.write_text(json.dumps(all_reports, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text("\n".join(md_parts), encoding="utf-8")
    latest = out_dir / "FULL_PRODUCTION_MATCH_REPORT_LATEST.md"
    latest.write_text("\n".join(md_parts), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "matches": len(all_reports)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
