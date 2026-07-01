"""PHASE WC-OWNER-EVAL-SUMMARY — Owner WC daily evaluation summary (read-only)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.research.ecse_wc.knockout_draw_pen_risk import load_knockout_draw_pen_risk_rows
from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT as SHADOW_EVAL_ARTIFACT
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES

PHASE = "WC-OWNER-EVAL-SUMMARY"
REPORTS_DIR = Path("reports/owner")

EvalRecommendation = Literal[
    "OWNER_EVAL_SUMMARY_READY",
    "WAITING_FOR_RESULTS",
    "NEED_EXISTING_RESULT_SYNC_RUN",
    "PARTIAL_EVALUATION_READY",
    "DO_NOT_USE_EVALUATION",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _is_finished(status: str | None) -> bool:
    return str(status or "").upper() in FINISHED_STATUSES


def _status_label(status: str | None, *, has_result: bool) -> str:
    if _is_finished(status) and has_result:
        return str(status or "FT").upper()
    if _is_finished(status):
        return "FINISHED_NO_RESULT_ROW"
    return "WAITING_FOR_RESULT"


def _market_result(status: str | None, *, finished: bool) -> str:
    if not finished:
        return "WAITING_FOR_RESULT"
    text = str(status or "").lower()
    if text in {"correct", "hit", "true", "1"}:
        return "HIT"
    if text in {"wrong", "miss", "false", "0"}:
        return "MISS"
    if text in {"partial", "unavailable", "unknown", "pending", ""}:
        return str(status or "UNKNOWN").upper()
    return text.upper()


def _draw_pen_warning_in_note(note: str | None) -> bool:
    text = str(note or "").lower()
    return "draw/pen risk" in text or "1-1 should be considered" in text


def _evaluate_draw_pen_warning(
    *,
    warning_present: bool,
    finished: bool,
    final_score: str | None,
    match_outcome_type: str | None,
    knockout_risk: dict[str, Any] | None,
) -> str:
    if not finished:
        return "WAITING_FOR_RESULT"
    if not warning_present and not (knockout_risk or {}).get("knockout_draw_pen_risk"):
        return "NO_WARNING"
    score = str(final_score or "")
    mot = str(match_outcome_type or "").upper()
    if score in ("1-1", "0-0") or mot == "PEN":
        return "USEFUL"
    try:
        hg, ag = [int(x) for x in score.split("-", 1)]
        if abs(hg - ag) <= 1 and (hg + ag) <= 2:
            return "USEFUL"
    except (TypeError, ValueError):
        pass
    return "FALSE_ALARM"


def _advancing_team(
    *,
    home_team: str,
    away_team: str,
    match_outcome_type: str | None,
    penalty_score: str | None,
    winner: str | None,
) -> str | None:
    mot = str(match_outcome_type or "").upper()
    if mot == "PEN" and penalty_score and "-" in penalty_score:
        try:
            ph, pa = [int(x.strip()) for x in penalty_score.split("-", 1)]
            if ph > pa:
                return home_team
            if pa > ph:
                return away_team
        except (TypeError, ValueError):
            pass
    w = str(winner or "").lower()
    if w == "home":
        return home_team
    if w == "away":
        return away_team
    return None


def _load_shadow_evaluation(fixture_id: int) -> dict[str, Any] | None:
    path = Path(SHADOW_EVAL_ARTIFACT)
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if int(row.get("fixture_id") or 0) != int(fixture_id):
            continue
        latest = row
    return latest


def _load_prediction_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_fixture_bundle(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    fx = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key, round_name
        FROM fixtures WHERE fixture_id = ?
        """,
        (int(fixture_id),),
    ).fetchone()
    result = conn.execute(
        """
        SELECT final_score, penalty_score, match_outcome_type, winner, home_goals, away_goals
        FROM fixture_results WHERE fixture_id = ?
        """,
        (int(fixture_id),),
    ).fetchone()
    return {
        "fixture": dict(fx) if fx else None,
        "result": dict(result) if result else None,
    }


def _load_ecse_evaluation(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT final_score, top1_correct, top3_correct, top5_correct, top10_correct,
               rank_of_actual_score, evaluated_at
        FROM ecse_prediction_evaluations
        WHERE fixture_id = ?
        ORDER BY evaluated_at DESC LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def build_fixture_eval_row(
    pred: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    knockout_map: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    fid = int(pred["fixture_id"])
    bundle = _load_fixture_bundle(conn, fid)
    fx = bundle.get("fixture") or {}
    res = bundle.get("result") or {}
    status = fx.get("status") or pred.get("status")
    has_result = bool(res.get("final_score"))
    finished = _is_finished(status) and has_result

    wde_eval = repo.get_worldcup_prediction_evaluation(fid)
    ecse_eval = _load_ecse_evaluation(conn, fid) if finished else None
    shadow_eval = _load_shadow_evaluation(fid) if finished else None
    knockout = knockout_map.get(fid)

    final_score = res.get("final_score") if finished else None
    penalty_score = res.get("penalty_score") if finished else None
    match_outcome = res.get("match_outcome_type") or status

    warning_present = _draw_pen_warning_in_note(pred.get("note")) or bool(
        (knockout or {}).get("knockout_draw_pen_risk")
    )
    draw_pen_result = _evaluate_draw_pen_warning(
        warning_present=warning_present,
        finished=finished,
        final_score=final_score,
        match_outcome_type=match_outcome,
        knockout_risk=knockout,
    )

    shadow_result = "WAITING_FOR_RESULT"
    if finished and shadow_eval:
        enh = shadow_eval.get("enhanced_hits") or {}
        base = shadow_eval.get("baseline_hits") or {}
        if enh.get("hit_top1") or base.get("hit_top1"):
            shadow_result = "TOP1_HIT"
        elif enh.get("hit_top3") or base.get("hit_top3"):
            shadow_result = "TOP3_HIT"
        elif enh.get("hit_top5") or base.get("hit_top5"):
            shadow_result = "TOP5_HIT"
        elif enh.get("hit_top10") or base.get("hit_top10"):
            shadow_result = "TOP10_HIT"
        else:
            shadow_result = "MISS"
    elif finished:
        shadow_result = "NO_SHADOW_EVAL"

    owner_note_parts: list[str] = []
    if not finished:
        owner_note_parts.append("Awaiting final result.")
    if draw_pen_result == "USEFUL":
        owner_note_parts.append("Draw/PEN cover warning validated at FT.")
    elif draw_pen_result == "FALSE_ALARM":
        owner_note_parts.append("Draw/PEN warning did not materialize at FT.")
    if penalty_score and final_score:
        owner_note_parts.append(
            f"ECSE/WDE scored on FT {final_score}; penalties {penalty_score} stored separately."
        )
    if pred.get("owner_label") == "STRONG_SIGNAL" and finished:
        owner_note_parts.append(f"Strongest-signal candidate — see market results.")

    return {
        "fixture_id": fid,
        "match": pred.get("match"),
        "kickoff": pred.get("kickoff_vienna") or pred.get("kickoff_utc"),
        "status": _status_label(status, has_result=has_result),
        "final_score": final_score,
        "penalty_score": penalty_score if finished else None,
        "advancing_team": _advancing_team(
            home_team=str(fx.get("home_team") or pred.get("match", "").split(" vs ")[0]),
            away_team=str(fx.get("away_team") or pred.get("match", "").split(" vs ")[-1]),
            match_outcome_type=match_outcome,
            penalty_score=penalty_score,
            winner=res.get("winner"),
        )
        if finished
        else None,
        "predictions": {
            "wde_1x2": pred.get("wde_1x2"),
            "wde_ou_25": pred.get("wde_ou_25"),
            "wde_btts": pred.get("wde_btts"),
            "wde_confidence": pred.get("wde_confidence"),
            "ecse_top1": pred.get("ecse_top1"),
            "ecse_top3": pred.get("ecse_top3"),
            "shadow_enhanced_top1": pred.get("shadow_enhanced_top1"),
            "owner_label": pred.get("owner_label"),
            "draw_pen_warning": warning_present,
        },
        "results": {
            "wde_1x2": _market_result(
                (wde_eval or {}).get("market_1x2_status"), finished=finished
            ),
            "wde_ou_25": _market_result(
                (wde_eval or {}).get("market_ou_status"), finished=finished
            ),
            "wde_btts": _market_result(
                (wde_eval or {}).get("market_btts_status"), finished=finished
            ),
            "ecse_top1": pred.get("ecse_top1"),
            "ecse_actual_rank": (
                ecse_eval.get("rank_of_actual_score") if ecse_eval else "WAITING_FOR_RESULT"
            ),
            "ecse_top3_hit": (
                bool(ecse_eval.get("top3_correct")) if ecse_eval else "WAITING_FOR_RESULT"
            ),
            "ecse_top5_hit": (
                bool(ecse_eval.get("top5_correct")) if ecse_eval else "WAITING_FOR_RESULT"
            ),
            "ecse_top1_hit": (
                bool(ecse_eval.get("top1_correct")) if ecse_eval else "WAITING_FOR_RESULT"
            ),
            "shadow_result": shadow_result,
            "draw_pen_warning_result": draw_pen_result,
        },
        "owner_note": " | ".join(owner_note_parts) if owner_note_parts else pred.get("note"),
        "evaluation_sources": {
            "wde_evaluation": bool(wde_eval) if finished else False,
            "ecse_evaluation": bool(ecse_eval) if finished else False,
            "shadow_evaluation": bool(shadow_eval) if finished else False,
            "knockout_risk": bool(knockout),
        },
    }


def _compute_metrics(rows: list[dict[str, Any]], *, strongest_match: str | None) -> dict[str, Any]:
    finished = [r for r in rows if r["status"] not in ("WAITING_FOR_RESULT", "FINISHED_NO_RESULT_ROW")]
    waiting = [r for r in rows if r["status"] == "WAITING_FOR_RESULT"]

    def _count_hits(key: str) -> int:
        return sum(1 for r in finished if r["results"].get(key) == "HIT")

    def _count_bool(key: str) -> int:
        return sum(
            1
            for r in finished
            if r["results"].get(key) is True or r["results"].get(key) == "TOP1_HIT"
        )

    draw_pen_useful = sum(1 for r in finished if r["results"].get("draw_pen_warning_result") == "USEFUL")
    draw_pen_false = sum(1 for r in finished if r["results"].get("draw_pen_warning_result") == "FALSE_ALARM")

    strongest_result = None
    if strongest_match:
        for r in rows:
            if r.get("match") == strongest_match and r["status"] != "WAITING_FOR_RESULT":
                strongest_result = {
                    "match": r["match"],
                    "owner_label": r["predictions"].get("owner_label"),
                    "wde_1x2": r["results"].get("wde_1x2"),
                    "ecse_top3_hit": r["results"].get("ecse_top3_hit"),
                    "final_score": r.get("final_score"),
                }
                break
        if strongest_match and strongest_result is None:
            strongest_result = {"match": strongest_match, "status": "WAITING_FOR_RESULT"}

    return {
        "fixtures_total": len(rows),
        "finished_fixtures": len(finished),
        "waiting_fixtures": len(waiting),
        "wde_1x2_hits": _count_hits("wde_1x2"),
        "wde_ou_hits": _count_hits("wde_ou_25"),
        "wde_btts_hits": _count_hits("wde_btts"),
        "ecse_top1_hits": sum(1 for r in finished if r["results"].get("ecse_top1_hit") is True),
        "ecse_top3_hits": sum(1 for r in finished if r["results"].get("ecse_top3_hit") is True),
        "ecse_top5_hits": sum(1 for r in finished if r["results"].get("ecse_top5_hit") is True),
        "draw_pen_warning_useful_count": draw_pen_useful,
        "draw_pen_false_alarm_count": draw_pen_false,
        "strongest_signal_result": strongest_result,
    }


def _final_recommendation(
    metrics: dict[str, Any],
    *,
    finished_missing_eval: int,
) -> EvalRecommendation:
    total = int(metrics["fixtures_total"])
    finished = int(metrics["finished_fixtures"])
    waiting = int(metrics["waiting_fixtures"])

    if finished_missing_eval > 0 and finished > 0:
        return "NEED_EXISTING_RESULT_SYNC_RUN"
    if finished == 0 and waiting == total:
        return "WAITING_FOR_RESULTS"
    if waiting > 0 and finished > 0:
        return "PARTIAL_EVALUATION_READY"
    if finished == total and finished > 0:
        return "OWNER_EVAL_SUMMARY_READY"
    return "DO_NOT_USE_EVALUATION"


def build_wc_owner_eval_summary(
    *,
    prediction_report_path: Path,
    date_ymd: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Build owner evaluation summary from prediction report + existing eval rows."""
    settings = settings or get_settings()
    report = _load_prediction_report(prediction_report_path)
    pred_rows = report.get("rows") or []
    summary_in = report.get("summary") or {}
    ymd = date_ymd or str(summary_in.get("date", "")).replace("-", "")
    if not ymd:
        ymd = datetime.now(timezone.utc).strftime("%Y%m%d")

    db_path = get_db_path(settings.sqlite_path)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=60.0)
    conn.row_factory = sqlite3.Row
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    knockout_map = {int(r["fixture_id"]): r for r in load_knockout_draw_pen_risk_rows()}

    eval_rows: list[dict[str, Any]] = []
    finished_missing_eval = 0
    for pred in pred_rows:
        row = build_fixture_eval_row(
            pred, conn=conn, repo=repo, knockout_map=knockout_map
        )
        if row["status"] != "WAITING_FOR_RESULT":
            has_any = any(
                row["evaluation_sources"].get(k)
                for k in ("wde_evaluation", "ecse_evaluation")
            )
            if not has_any:
                finished_missing_eval += 1
        eval_rows.append(row)

    metrics = _compute_metrics(
        eval_rows,
        strongest_match=summary_in.get("strongest_signal_of_the_day"),
    )
    recommendation = _final_recommendation(metrics, finished_missing_eval=finished_missing_eval)

    payload = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "prediction_report": str(prediction_report_path),
        "date": summary_in.get("date"),
        "timezone": summary_in.get("timezone"),
        "competition": summary_in.get("competition") or "world_cup_2026",
        "final_recommendation": recommendation,
        "metrics": metrics,
        "fixtures": eval_rows,
        "public_output_changed": False,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"wc_owner_eval_summary_{ymd}.json"
    md_path = REPORTS_DIR / f"wc_owner_eval_summary_{ymd}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# WC Owner Evaluation Summary — {summary_in.get('date') or ymd}",
        "",
        f"**Phase:** {PHASE} | **Owner/internal only**",
        f"**Recommendation:** `{recommendation}`",
        "",
        "## Metrics",
        "",
        f"- Fixtures total: **{metrics['fixtures_total']}**",
        f"- Finished: **{metrics['finished_fixtures']}** | Waiting: **{metrics['waiting_fixtures']}**",
        f"- WDE hits (1X2 / O/U / BTTS): **{metrics['wde_1x2_hits']}** / **{metrics['wde_ou_hits']}** / **{metrics['wde_btts_hits']}**",
        f"- ECSE hits (Top-1 / Top-3 / Top-5): **{metrics['ecse_top1_hits']}** / **{metrics['ecse_top3_hits']}** / **{metrics['ecse_top5_hits']}**",
        f"- Draw/PEN useful / false alarm: **{metrics['draw_pen_warning_useful_count']}** / **{metrics['draw_pen_false_alarm_count']}**",
        "",
        "## Evaluation table",
        "",
        "| Match | Status | Final | Penalties | WDE 1X2 | WDE O/U | WDE BTTS | ECSE Top-1 | ECSE rank | ECSE Top-3 | Shadow | Draw/PEN | Note |",
        "|-------|--------|-------|-----------|---------|---------|----------|------------|-----------|------------|--------|----------|------|",
    ]
    for r in eval_rows:
        res = r["results"]
        md_lines.append(
            f"| {r['match']} | {r['status']} | {r.get('final_score') or '—'} | "
            f"{r.get('penalty_score') or '—'} | {res.get('wde_1x2')} | {res.get('wde_ou_25')} | "
            f"{res.get('wde_btts')} | {res.get('ecse_top1')} | {res.get('ecse_actual_rank')} | "
            f"{res.get('ecse_top3_hit')} | {res.get('shadow_result')} | {res.get('draw_pen_warning_result')} | "
            f"{(r.get('owner_note') or '')[:60]} |"
        )

    md_lines.extend(["", "## Fixture details", ""])
    for r in eval_rows:
        md_lines.append(f"### {r['match']} (fixture {r['fixture_id']})")
        md_lines.append(f"- Status: {r['status']} | Final: {r.get('final_score') or '—'} | Penalties: {r.get('penalty_score') or '—'}")
        if r.get("advancing_team"):
            md_lines.append(f"- Advancing: **{r['advancing_team']}**")
        p = r["predictions"]
        md_lines.append(
            f"- Pre-match WDE: 1X2={p.get('wde_1x2')} O/U={p.get('wde_ou_25')} BTTS={p.get('wde_btts')} "
            f"conf={p.get('wde_confidence')} label={p.get('owner_label')}"
        )
        md_lines.append(
            f"- Pre-match ECSE Top-1/Top-3: {p.get('ecse_top1')} / {p.get('ecse_top3')}"
        )
        md_lines.append(f"- {r.get('owner_note')}")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    conn.close()
    repo.close()

    return {
        **payload,
        "md_path": str(md_path),
        "json_path": str(json_path),
    }
