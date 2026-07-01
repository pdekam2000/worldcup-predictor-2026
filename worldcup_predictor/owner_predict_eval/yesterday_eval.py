"""Part C — Yesterday prediction evaluation against fixture_results."""



from __future__ import annotations



import json

import logging

from dataclasses import dataclass, field

from datetime import date

from pathlib import Path

from typing import Any



from worldcup_predictor.accuracy.evaluator import actual_1x2, actual_over_under

from worldcup_predictor.config.settings import Settings, get_settings

from worldcup_predictor.database.connection import connect

from worldcup_predictor.owner_daily.fixture_discovery import discover_fixtures_from_db, vienna_day_utc_bounds

from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

from worldcup_predictor.owner_predict_eval.constants import (

    ARTIFACTS_DIR,

    PHASE,

    REPORTS_DIR,

    with_safety_labels,

)

from worldcup_predictor.owner_predict_eval.dates import date_tag, resolve_process_date, yesterday_of

from worldcup_predictor.owner_predict_eval.db_helpers import load_fixture_result, table_exists

from worldcup_predictor.owner_predict_eval.predictions import _load_oddalerts_shadow

from worldcup_predictor.owner_daily.report import _load_ecse, _load_wde

from worldcup_predictor.schedule.match_center import FINISHED_STATUSES



logger = logging.getLogger(__name__)



RESULT_SOURCE_RANK: dict[str, int] = {

    "api-football": 100,

    "api_football": 100,

    "sportmonks": 90,

    "official": 80,

    "manual": 70,

    "cache": 40,

    "unknown": 10,

    "": 0,

}





def _parse_json_list(raw: str | None) -> list[Any]:

    if not raw:

        return []

    try:

        val = json.loads(raw)

    except (json.JSONDecodeError, TypeError):

        return []

    return val if isinstance(val, list) else []





def _scorelines_from_rows(rows: list[Any]) -> list[str]:

    out: list[str] = []

    for item in rows:

        if isinstance(item, dict):

            sl = item.get("scoreline") or item.get("label")

            if sl:

                out.append(str(sl))

        elif item:

            out.append(str(item))

    return out





def _eval_topn(actual: str, top1: str | None, top3: list[str], top5: list[str], top10: list[str]) -> dict[str, Any]:

    return {

        "top1_hit": top1 == actual,

        "top3_hit": actual in top3,

        "top5_hit": actual in top5,

        "top10_hit": actual in top10,

    }





def _eval_wde(wde: dict[str, Any] | None, hg: int, ag: int) -> dict[str, Any]:

    if not wde:

        return {"status": "NO_PREDICTION"}

    actual_x2 = actual_1x2(hg, ag)

    actual_ou = actual_over_under(hg, ag)

    pred_x2 = wde.get("predicted_1x2")

    pred_ou = wde.get("predicted_over_under_2_5")

    btts_actual = "yes" if hg > 0 and ag > 0 else "no"

    btts_pred = wde.get("btts_pick")

    return {

        "status": "EVALUATED",

        "one_x_two": {"predicted": pred_x2, "actual": actual_x2, "hit": pred_x2 == actual_x2},

        "over_under_2_5": {"predicted": pred_ou, "actual": actual_ou, "hit": pred_ou == actual_ou},

        "btts": {"predicted": btts_pred, "actual": btts_actual, "hit": btts_pred == btts_actual if btts_pred else None},

    }





def _eval_ecse(ecse: dict[str, Any] | None, actual: str) -> dict[str, Any]:

    if not ecse:

        return {"status": "NO_PREDICTION"}

    top1 = str(ecse.get("top_1_score") or "")

    top3 = _scorelines_from_rows(ecse.get("top_3_scores") or [])

    top5 = _scorelines_from_rows(ecse.get("top_5_scores") or [])

    top10 = _scorelines_from_rows(ecse.get("top_10_scorelines") or ecse.get("top_5_scores") or [])

    return {"status": "EVALUATED", "actual_score": actual, **_eval_topn(actual, top1, top3, top5, top10)}





def _eval_shadow(shadow: dict[str, Any] | None, actual: str) -> dict[str, Any]:

    if not shadow:

        return {"status": "NO_PREDICTION"}

    top1 = str(shadow.get("top_1_score") or "")

    top3 = _scorelines_from_rows(shadow.get("top_3_scores") or [])

    top5 = _scorelines_from_rows(shadow.get("top_5_scores") or [])

    top10 = _scorelines_from_rows(shadow.get("top_10_scores") or [])

    return {"status": "EVALUATED", "actual_score": actual, **_eval_topn(actual, top1, top3, top5, top10)}





def _result_source_rank(source: str | None) -> int:

    key = str(source or "").strip().lower()

    return RESULT_SOURCE_RANK.get(key, RESULT_SOURCE_RANK["unknown"])





def _is_finished_status(status: str) -> bool:

    s = status.upper()

    return s in FINISHED_STATUSES or s in ("FT", "AET", "PEN", "FINISHED")





def _fixture_status(conn, fixture_id: int, fallback: str = "") -> str:

    row = conn.execute(

        "SELECT status FROM fixtures WHERE fixture_id=? LIMIT 1",

        (int(fixture_id),),

    ).fetchone()

    return str(row["status"] if row else fallback).upper()





def _try_evaluate_fixture_row(

    conn,

    fx: dict[str, Any],

    *,

    settings: Settings,

) -> tuple[dict[str, Any], bool, bool]:

    """Return (row, evaluated, newly_evaluated)."""

    fid = int(fx["fixture_id"])

    comp_key = str(fx.get("competition_key") or "")

    status = str(fx.get("status") or "").upper()

    result = load_fixture_result(conn, fid)

    row: dict[str, Any] = {

        "fixture_id": fid,

        "home_team": fx.get("home_team"),

        "away_team": fx.get("away_team"),

        "competition_key": comp_key,

        "kickoff": fx.get("kickoff"),

        "status": status,

    }



    if not result or result.get("home_goals") is None or result.get("away_goals") is None:

        row["evaluation_status"] = "WAITING_RESULT"

        return row, False, False



    if not _is_finished_status(status):

        status = _fixture_status(conn, fid, status)



    if not _is_finished_status(status):

        row["evaluation_status"] = "WAITING_RESULT"

        return row, False, False



    hg = int(result["home_goals"])

    ag = int(result["away_goals"])

    actual_score = f"{hg}-{ag}"

    outcome_source = str(result.get("outcome_source") or result.get("source") or "unknown")

    wde = _load_wde(fid, settings, comp_key)

    ecse = _load_ecse(conn, fid)

    shadow = _load_oddalerts_shadow(conn, fid)



    row["evaluation_status"] = "EVALUATED"

    row["final_score"] = actual_score

    row["result_source"] = outcome_source

    row["wde"] = _eval_wde(wde, hg, ag)

    row["ecse_production"] = _eval_ecse(ecse, actual_score)

    row["ecse_oddalerts_shadow"] = _eval_shadow(shadow, actual_score)

    return row, True, True





def _merge_evaluated_row(

    existing: dict[str, Any],

    fresh: dict[str, Any],

) -> tuple[dict[str, Any], bool]:

    """Preserve existing evaluation unless a safer result source appears. Returns (row, changed)."""

    if existing.get("evaluation_status") != "EVALUATED":

        return fresh, True



    old_score = str(existing.get("final_score") or "")

    new_score = str(fresh.get("final_score") or "")

    old_rank = _result_source_rank(existing.get("result_source"))

    new_rank = _result_source_rank(fresh.get("result_source"))



    if old_score == new_score:

        return existing, False



    if new_rank > old_rank:

        reason = (

            f"fixture {existing.get('fixture_id')}: updated score {old_score} -> {new_score} "

            f"due to safer result source ({existing.get('result_source')} -> {fresh.get('result_source')})"

        )

        logger.info(reason)

        merged = dict(fresh)

        merged["score_update_reason"] = reason

        return merged, True



    reason = (

        f"fixture {existing.get('fixture_id')}: kept existing score {old_score} "

        f"(existing source rank {old_rank} >= new {new_rank})"

    )

    logger.info(reason)

    preserved = dict(existing)

    preserved["score_preserve_reason"] = reason

    return preserved, False





def _derive_refresh_status(*, evaluated_count: int, waiting: int, newly_evaluated: int) -> str:

    if waiting == 0 and evaluated_count > 0:

        return "all_results_evaluated"

    if newly_evaluated > 0:

        return "partial_results_evaluated"

    return "no_new_results_available"





@dataclass

class YesterdayEvalResult:

    phase: str = PHASE

    evaluation_date: str = ""

    fixture_count: int = 0

    evaluated_count: int = 0

    waiting_result_count: int = 0

    newly_evaluated_count: int = 0

    refresh_mode: bool = False

    result_refresh_status: str = ""

    fixtures: list[dict[str, Any]] = field(default_factory=list)

    md_path: str = ""

    json_path: str = ""



    def to_dict(self) -> dict[str, Any]:

        return with_safety_labels(

            {

                "phase": self.phase,

                "evaluation_date": self.evaluation_date,

                "fixture_count": self.fixture_count,

                "evaluated_count": self.evaluated_count,

                "waiting_result_count": self.waiting_result_count,

                "newly_evaluated_count": self.newly_evaluated_count,

                "refresh_mode": self.refresh_mode,

                "result_refresh_status": self.result_refresh_status,

                "md_path": self.md_path,

                "json_path": self.json_path,

                "fixtures": self.fixtures,

            }

        )





def artifact_json_path(target: date) -> Path:

    return ARTIFACTS_DIR / f"owner_yesterday_prediction_evaluation_{date_tag(target)}.json"





def report_md_path(target: date) -> Path:

    return REPORTS_DIR / f"yesterday_prediction_evaluation_{date_tag(target)}.md"





def load_existing_artifact(target: date) -> dict[str, Any] | None:

    path = artifact_json_path(target)

    if not path.exists():

        return None

    try:

        return json.loads(path.read_text(encoding="utf-8"))

    except (json.JSONDecodeError, OSError):

        return None





def _resolve_yesterday_date(date_arg: str, timezone: str) -> date:

    from worldcup_predictor.owner_predict_eval.dates import resolve_yesterday_date

    return resolve_yesterday_date(date_arg, timezone)





def _fixtures_predicted_yesterday(

    conn,

    yesterday: date,

    *,

    timezone: str,

    settings: Settings,

) -> list[dict[str, Any]]:

    start_utc, end_utc = vienna_day_utc_bounds(yesterday, timezone)

    keys = list(DAILY_SUPPORTED_COMPETITIONS)

    fixtures = discover_fixtures_from_db(conn, competition_keys=keys, start_utc=start_utc, end_utc=end_utc)

    out: list[dict[str, Any]] = []

    for fx in fixtures:

        fid = fx.provider_fixture_id

        wde = conn.execute(

            "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",

            (fid,),

        ).fetchone()

        ecse = None

        if table_exists(conn, "ecse_prediction_snapshots"):

            ecse = conn.execute(

                "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=? LIMIT 1",

                (fid,),

            ).fetchone()

        shadow = None

        if table_exists(conn, "ecse_oddalerts_shadow_predictions"):

            shadow = conn.execute(

                "SELECT 1 FROM ecse_oddalerts_shadow_predictions WHERE fixture_id=? LIMIT 1",

                (fid,),

            ).fetchone()

        if not shadow and table_exists(conn, "ecse_oddalerts_shadow_monitor"):

            shadow = conn.execute(

                "SELECT 1 FROM ecse_oddalerts_shadow_monitor WHERE fixture_id=? LIMIT 1",

                (fid,),

            ).fetchone()

        if wde or ecse or shadow:

            out.append(

                {

                    "fixture_id": fid,

                    "competition_key": fx.competition_key,

                    "home_team": fx.home_team,

                    "away_team": fx.away_team,

                    "kickoff": fx.kickoff_utc,

                    "status": fx.status,

                }

            )

    return out





def _write_yesterday_reports(out: YesterdayEvalResult, yesterday: date) -> None:

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = artifact_json_path(yesterday)

    md_path = report_md_path(yesterday)

    json_path.write_text(json.dumps(out.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    out.json_path = str(json_path)

    out.md_path = str(md_path)



    evaluated_rows = out.fixtures

    lines = [

        f"# Yesterday Prediction Evaluation — {yesterday.isoformat()}",

        "",

        f"Fixtures with predictions: **{out.fixture_count}** | Evaluated: **{out.evaluated_count}** | Waiting: **{out.waiting_result_count}**",

    ]

    if out.refresh_mode:

        lines.append(

            f"Refresh mode: **{out.result_refresh_status}** (newly evaluated: {out.newly_evaluated_count})"

        )

    lines.extend(

        [

            "",

            "| Fixture | Final | WDE 1X2 | WDE BTTS | WDE O/U | ECSE T1 | ECSE T3 | Shadow T1 | Status |",

            "|---------|-------|---------|----------|---------|---------|---------|-----------|--------|",

        ]

    )

    for r in evaluated_rows:

        if r.get("evaluation_status") == "WAITING_RESULT":

            lines.append(

                f"| {r.get('home_team')} vs {r.get('away_team')} | — | — | — | — | — | — | — | WAITING_RESULT |"

            )

            continue

        wde = r.get("wde") or {}

        ecse = r.get("ecse_production") or {}

        sh = r.get("ecse_oddalerts_shadow") or {}

        x2 = wde.get("one_x_two") or {}

        btts = wde.get("btts") or {}

        ou = wde.get("over_under_2_5") or {}

        lines.append(

            f"| {r.get('home_team')} vs {r.get('away_team')} | {r.get('final_score')} | "

            f"{x2.get('hit')} | {btts.get('hit')} | {ou.get('hit')} | "

            f"{ecse.get('top1_hit')} | {ecse.get('top3_hit')} | {sh.get('top1_hit')} | EVALUATED |"

        )

    lines.extend(

        [

            "",

            "## Safety labels",

            "",

            "- **PUBLIC_PUBLISH:** `false`",

            "- **WDE_RETRAINED:** `false`",

            "- **HISTORICAL_CSV_PROMOTED:** `false`",

            "- **ODDALERTS_ECSE_PRODUCTION:** `false`",

            "- **ODDALERTS_ECSE_SHADOW_ONLY:** `true`",

        ]

    )

    md_path.write_text("\n".join(lines), encoding="utf-8")





def _evaluate_full(

    conn,

    candidates: list[dict[str, Any]],

    *,

    settings: Settings,

) -> tuple[list[dict[str, Any]], int, int]:

    evaluated_rows: list[dict[str, Any]] = []

    evaluated_count = 0

    waiting = 0

    for fx in candidates:

        row, is_evaluated, _ = _try_evaluate_fixture_row(conn, fx, settings=settings)

        if is_evaluated:

            evaluated_count += 1

        else:

            waiting += 1

        evaluated_rows.append(row)

    evaluated_rows.sort(key=lambda r: (r.get("kickoff") or "", r.get("fixture_id") or 0))

    return evaluated_rows, evaluated_count, waiting





def _evaluate_refresh_missing(

    conn,

    existing: dict[str, Any],

    *,

    settings: Settings,

) -> tuple[list[dict[str, Any]], int, int, int]:

    preserved: list[dict[str, Any]] = []

    waiting_rows: list[dict[str, Any]] = []

    evaluated_count = 0

    newly_evaluated = 0



    for row in existing.get("fixtures") or []:

        if row.get("evaluation_status") == "EVALUATED":

            preserved.append(dict(row))

            evaluated_count += 1

        else:

            waiting_rows.append(dict(row))



    updated_waiting: list[dict[str, Any]] = []

    waiting = 0

    for fx in waiting_rows:

        fid = int(fx["fixture_id"])

        status = _fixture_status(conn, fid, str(fx.get("status") or ""))

        fx["status"] = status

        fresh_row, is_evaluated, _ = _try_evaluate_fixture_row(conn, fx, settings=settings)

        if is_evaluated:

            merged, changed = _merge_evaluated_row(fx, fresh_row)

            if changed or fx.get("evaluation_status") != "EVALUATED":

                newly_evaluated += 1

            preserved.append(merged)

            evaluated_count += 1

        else:

            updated_waiting.append(fresh_row)

            waiting += 1



    all_rows = preserved + updated_waiting

    all_rows.sort(key=lambda r: (r.get("kickoff") or "", r.get("fixture_id") or 0))

    return all_rows, evaluated_count, waiting, newly_evaluated





def evaluate_yesterday_predictions(

    *,

    date_arg: str = "yesterday",

    timezone: str = "Europe/Vienna",

    settings: Settings | None = None,

    refresh_missing_results: bool = False,

) -> YesterdayEvalResult:

    settings = settings or get_settings()

    conn = connect(settings.sqlite_path)

    yesterday = _resolve_yesterday_date(date_arg, timezone)



    if refresh_missing_results:

        existing = load_existing_artifact(yesterday)

        if existing and (existing.get("fixtures") or []):

            rows, evaluated_count, waiting, newly_evaluated = _evaluate_refresh_missing(

                conn, existing, settings=settings

            )

            refresh_status = _derive_refresh_status(

                evaluated_count=evaluated_count,

                waiting=waiting,

                newly_evaluated=newly_evaluated,

            )

            out = YesterdayEvalResult(

                evaluation_date=yesterday.isoformat(),

                fixture_count=len(rows),

                evaluated_count=evaluated_count,

                waiting_result_count=waiting,

                newly_evaluated_count=newly_evaluated,

                refresh_mode=True,

                result_refresh_status=refresh_status,

                fixtures=rows,

            )

            _write_yesterday_reports(out, yesterday)

            return out



    candidates = _fixtures_predicted_yesterday(conn, yesterday, timezone=timezone, settings=settings)

    rows, evaluated_count, waiting = _evaluate_full(conn, candidates, settings=settings)

    refresh_status = _derive_refresh_status(

        evaluated_count=evaluated_count,

        waiting=waiting,

        newly_evaluated=evaluated_count,

    )

    out = YesterdayEvalResult(

        evaluation_date=yesterday.isoformat(),

        fixture_count=len(rows),

        evaluated_count=evaluated_count,

        waiting_result_count=waiting,

        newly_evaluated_count=0,

        refresh_mode=refresh_missing_results,

        result_refresh_status=refresh_status,

        fixtures=rows,

    )

    _write_yesterday_reports(out, yesterday)

    return out


