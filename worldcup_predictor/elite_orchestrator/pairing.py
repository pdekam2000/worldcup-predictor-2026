"""Part E — post-match pairing of shadow predictions with results."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_orchestrator.shadow_config import EVALUATIONS_PATH, MODEL_VERSION, PREDICTIONS_PATH
from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import append_jsonl_rows, load_jsonl

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "football_intelligence.db"

_FINISHED = ("FT", "AET", "PEN", "FINISHED", "AWD", "WO")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_predictions(path: Path | None = None) -> list[dict[str, Any]]:
    return load_jsonl(path or PREDICTIONS_PATH)


def _eval_dedupe_key(row: dict[str, Any]) -> tuple[int, str, str]:
    return (
        int(row.get("fixture_id") or 0),
        str(row.get("market_id") or ""),
        str(row.get("prediction_day") or ""),
    )


def _fixture_result(fixture_id: int) -> dict[str, Any] | None:
    if not DB_PATH.is_file():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (int(fixture_id),)).fetchone()
    res = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (int(fixture_id),)).fetchone()
    fg = conn.execute(
        """
        SELECT team, minute, extra_minute FROM fixture_goal_events
        WHERE fixture_id=? AND sort_index=0
        """,
        (int(fixture_id),),
    ).fetchone()
    conn.close()
    if not fx:
        return None
    status = str(fx["status"] or "")
    finished = status in _FINISHED
    out: dict[str, Any] = {
        "fixture_id": int(fixture_id),
        "status": status,
        "finished": finished,
        "home_team": fx["home_team"],
        "away_team": fx["away_team"],
        "kickoff_utc": fx["kickoff_utc"],
    }
    if res:
        hg, ag = int(res["home_goals"] or 0), int(res["away_goals"] or 0)
        out["home_goals"] = hg
        out["away_goals"] = ag
        if hg > ag:
            out["match_winner"] = "home"
        elif ag > hg:
            out["match_winner"] = "away"
        else:
            out["match_winner"] = "draw"
        out["over_under"] = "over_2_5" if (hg + ag) > 2 else "under_2_5"
    if fg and fx:
        team = str(fg["team"] or "")
        home = str(fx["home_team"] or "")
        away = str(fx["away_team"] or "")
        minute = int(fg["minute"] or 0) + int(fg["extra_minute"] or 0)
        out["first_goal_minute"] = minute
        if team == home:
            out["first_goal_team"] = "home"
        elif team == away:
            out["first_goal_team"] = "away"
        out["goalscorer"] = team
    return out


def _reality_for_market(market_id: str, result: dict[str, Any]) -> Any:
    if market_id in ("first_goal_team", "team_to_score_first"):
        return result.get("first_goal_team")
    if market_id == "1x2":
        return result.get("match_winner")
    if market_id in ("btts", "both_teams_to_score"):
        hg, ag = result.get("home_goals"), result.get("away_goals")
        if hg is None or ag is None:
            return None
        return "yes" if int(hg) > 0 and int(ag) > 0 else "no"
    if market_id in ("over_under_2_5", "over_under_25", "over_under"):
        return result.get("over_under")
    if market_id == "correct_score":
        hg, ag = result.get("home_goals"), result.get("away_goals")
        if hg is None or ag is None:
            return None
        return f"{int(hg)}-{int(ag)}"
    if market_id in ("anytime_goalscorer", "first_goalscorer", "goalscorer"):
        return result.get("goalscorer")
    if market_id == "goal_timing":
        return result.get("first_goal_minute")
    return None


def _outcome(market_id: str, prediction: Any, reality: Any) -> str:
    if reality is None:
        return "pending"
    if prediction is None:
        return "abstain"
    if market_id == "1x2" and isinstance(prediction, dict):
        pick = max(prediction, key=prediction.get)
        return "correct" if str(pick) == str(reality) else "incorrect"
    if isinstance(prediction, list):
        return "pending"
    return "correct" if str(prediction).lower() == str(reality).lower() else "incorrect"


def pair_predictions(
    *,
    predictions_path: Path | None = None,
    evaluations_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    preds = _load_predictions(predictions_path)
    out_path = evaluations_path or EVALUATIONS_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing_days: set[tuple[int, str, str]] = set()
    if out_path.is_file() and not force:
        for row in load_jsonl(out_path):
            existing_days.add(_eval_dedupe_key(row))

    pending = 0
    paired = 0
    to_write: list[dict[str, Any]] = []

    for pred in preds:
        fid = int(pred.get("fixture_id") or 0)
        market_id = str(pred.get("market_id") or "")
        day = str(pred.get("prediction_day") or "")
        dedupe = (fid, market_id, day)
        if dedupe in existing_days:
            continue

        result = _fixture_result(fid)
        mp = pred.get("market_predictions") or {}
        prediction = mp.get("prediction")
        reality = None
        status = "pending"

        if result and result.get("finished"):
            reality = _reality_for_market(market_id, result)
            if reality is not None:
                status = _outcome(market_id, prediction, reality)
                paired += 1
            else:
                status = "pending"
                pending += 1
        else:
            pending += 1

        record = {
            "fixture_id": fid,
            "market_id": market_id,
            "prediction_day": day,
            "generated_at": pred.get("generated_at"),
            "paired_at": _utc_now(),
            "prediction": prediction,
            "confidence": mp.get("confidence"),
            "tier": mp.get("tier"),
            "reality": reality,
            "outcome": status,
            "component_contributions": pred.get("component_contributions"),
            "model_version": (pred.get("model_versions") or {}).get("elite_orchestrator", MODEL_VERSION),
            "is_shadow": True,
            "meta": {"result_status": (result or {}).get("status")},
        }
        to_write.append(record)
        existing_days.add(dedupe)

    write_result = append_jsonl_rows(out_path, to_write, dedupe_key=_eval_dedupe_key, force=force)

    return {
        "predictions_read": len(preds),
        "evaluations_written": write_result.get("written", 0),
        "skipped_duplicates": write_result.get("skipped_duplicates", 0),
        "paired_with_result": paired,
        "pending": pending,
        "path": str(out_path),
    }
