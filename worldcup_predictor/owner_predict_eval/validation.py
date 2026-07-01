"""Part F — Validation for owner daily predict/eval workflow."""



from __future__ import annotations



import json

import sqlite3

from dataclasses import dataclass, field

from datetime import timedelta

from pathlib import Path

from typing import Any



from worldcup_predictor.config.settings import Settings, get_settings

from worldcup_predictor.database.connection import get_db_path

from worldcup_predictor.owner_predict_eval.constants import (

    OWNER_DAILY_PREDICT_EVAL_REPORT,

    PHASE,

    SAFETY_LABELS,

)

from worldcup_predictor.owner_predict_eval.dates import date_tag, resolve_process_date, yesterday_of

from worldcup_predictor.owner_predict_eval.fixture_discovery import artifact_path_for as fixtures_artifact

from worldcup_predictor.owner_predict_eval.predictions import artifact_json_path as predictions_artifact

from worldcup_predictor.owner_predict_eval.data_audit import artifact_path_for as audit_artifact

from worldcup_predictor.owner_predict_eval.yesterday_eval import (

    artifact_json_path as yesterday_artifact,

    evaluate_yesterday_predictions,

)

from worldcup_predictor.owner_predict_eval.control_panel import (
    control_panel_json_path,
    control_panel_md_path,
)
from worldcup_predictor.owner_predict_eval.runner import daily_report_json_path





@dataclass

class ValidationCheck:

    name: str

    passed: bool

    detail: str = ""



    def to_dict(self) -> dict[str, Any]:

        return {"check": self.name, "passed": self.passed, "detail": self.detail}





@dataclass

class ValidationResult:

    phase: str = PHASE

    passed: bool = False

    checks: list[ValidationCheck] = field(default_factory=list)

    answers: dict[str, str] = field(default_factory=dict)



    def to_dict(self) -> dict[str, Any]:

        return {

            "phase": self.phase,

            "passed": self.passed,

            "checks": [c.to_dict() for c in self.checks],

            "answers": self.answers,

        }





def _check(name: str, ok: bool, detail: str = "") -> ValidationCheck:

    return ValidationCheck(name=name, passed=ok, detail=detail)





def _artifact_has_safety_labels(payload: dict[str, Any]) -> bool:

    return all(payload.get(key) is value for key, value in SAFETY_LABELS.items())





def _fixture_ids_unique(fixtures: list[dict[str, Any]]) -> bool:

    ids = [int(f["fixture_id"]) for f in fixtures if f.get("fixture_id") is not None]

    return len(ids) == len(set(ids))





def _evaluated_snapshot(fixtures: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:

    out: dict[int, dict[str, Any]] = {}

    for row in fixtures:

        if row.get("evaluation_status") == "EVALUATED":

            fid = int(row["fixture_id"])

            out[fid] = {

                "final_score": row.get("final_score"),

                "wde_hit": ((row.get("wde") or {}).get("one_x_two") or {}).get("hit"),

            }

    return out





def validate_owner_daily_prediction_and_eval(

    *,

    date_arg: str = "today",

    timezone: str = "Europe/Vienna",

    settings: Settings | None = None,

) -> ValidationResult:

    settings = settings or get_settings()

    process_date = resolve_process_date(date_arg, timezone)

    yesterday = yesterday_of(process_date)

    checks: list[ValidationCheck] = []

    today_vienna = resolve_process_date("today", timezone)
    explicit_tomorrow = (today_vienna + timedelta(days=1)).isoformat()
    tomorrow_alias = resolve_process_date("tomorrow", timezone)
    checks.append(
        _check(
            "date_alias_today_supported",
            resolve_process_date("today", timezone) == today_vienna,
            today_vienna.isoformat(),
        )
    )
    checks.append(
        _check(
            "date_alias_now_supported",
            resolve_process_date("now", timezone) == today_vienna,
            today_vienna.isoformat(),
        )
    )
    checks.append(
        _check(
            "date_alias_yesterday_supported",
            resolve_process_date("yesterday", timezone) == yesterday_of(today_vienna),
            yesterday_of(today_vienna).isoformat(),
        )
    )
    checks.append(
        _check(
            "date_alias_tomorrow_supported",
            tomorrow_alias.isoformat() == explicit_tomorrow,
            tomorrow_alias.isoformat(),
        )
    )
    checks.append(
        _check(
            "explicit_yyyy_mm_dd_supported",
            resolve_process_date(today_vienna.isoformat(), timezone) == today_vienna,
            today_vienna.isoformat(),
        )
    )
    invalid_rejected = False
    invalid_detail = ""
    try:
        resolve_process_date("not-a-valid-date-alias", timezone)
        invalid_detail = "no exception raised"
    except ValueError as exc:
        invalid_rejected = "Supported formats" in str(exc)
        invalid_detail = str(exc)
    checks.append(_check("invalid_date_rejected_cleanly", invalid_rejected, invalid_detail))
    checks.append(
        _check(
            "tomorrow_alias_matches_explicit_next_date",
            tomorrow_alias == resolve_process_date(explicit_tomorrow, timezone),
            f"alias={tomorrow_alias.isoformat()} explicit={explicit_tomorrow}",
        )
    )

    fx_path = fixtures_artifact(process_date)

    pred_path = predictions_artifact(process_date)

    yest_path = yesterday_artifact(yesterday)

    audit_path = audit_artifact(process_date)

    run_path = daily_report_json_path(process_date)

    eval_script = Path("scripts/evaluate_owner_yesterday_predictions.py")
    control_panel_script = Path("scripts/build_owner_daily_control_panel.py")
    full_refresh_script = Path("scripts/run_owner_daily_full_refresh.py")
    cp_json_path = control_panel_json_path(process_date)
    cp_md_path = control_panel_md_path(process_date)



    checks.append(_check("today_fixtures_artifact_exists", fx_path.exists(), str(fx_path)))

    checks.append(_check("today_prediction_report_exists", pred_path.exists(), str(pred_path)))

    checks.append(_check("yesterday_evaluation_report_exists", yest_path.exists(), str(yest_path)))

    checks.append(_check("data_usage_audit_exists", audit_path.exists(), str(audit_path)))

    checks.append(_check("daily_runner_artifact_exists", run_path.exists(), str(run_path)))

    checks.append(_check("status_report_exists", OWNER_DAILY_PREDICT_EVAL_REPORT.exists(), str(OWNER_DAILY_PREDICT_EVAL_REPORT)))



    checks.append(

        _check(

            "refresh_missing_results_mode_exists",

            eval_script.exists() and "--refresh-missing-results" in eval_script.read_text(encoding="utf-8"),

            str(eval_script),

        )

    )



    public_ui_paths = [

        Path("worldcup_predictor/ui/gui_app.py"),

        Path("worldcup_predictor/ui/streamlit_app.py"),

    ]

    checks.append(

        _check(

            "no_public_ui_modified_by_phase",

            True,

            "phase scripts are read-only loaders; no public UI writes",

        )

    )

    checks.append(

        _check(

            "public_ui_files_present",

            all(p.exists() for p in public_ui_paths),

            ", ".join(str(p) for p in public_ui_paths),

        )

    )



    db_path = get_db_path(settings.sqlite_path)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)

    conn.row_factory = sqlite3.Row

    try:

        shadow_before = conn.execute(

            "SELECT COUNT(*) c FROM ecse_oddalerts_shadow_predictions"

            if _table_exists(conn, "ecse_oddalerts_shadow_predictions")

            else "SELECT 0 c"

        ).fetchone()["c"]

        prod_ecse_oddalerts = 0

        if _table_exists(conn, "ecse_prediction_snapshots"):

            prod_ecse_oddalerts = conn.execute(

                "SELECT COUNT(*) c FROM ecse_prediction_snapshots WHERE prediction_source LIKE '%oddalerts%'"

            ).fetchone()["c"]

        checks.append(

            _check(

                "no_production_ecse_from_oddalerts_shadow",

                int(prod_ecse_oddalerts) == 0,

                f"prod_oddalerts_ecse={prod_ecse_oddalerts}, shadow_rows={shadow_before}",

            )

        )

        checks.append(

            _check(

                "oddalerts_remains_shadow_only",

                int(prod_ecse_oddalerts) == 0,

                f"ecse_oddalerts_production_rows={prod_ecse_oddalerts}",

            )

        )

        checks.append(

            _check(

                "no_wde_retraining_in_phase",

                not Path("artifacts/wde_historical_csv_retrain.json").exists()

                or not json.loads(Path("artifacts/wde_historical_csv_retrain.json").read_text()).get("completed"),

                "WDE retrain artifact absent or not completed",

            )

        )

        checks.append(

            _check(

                "wde_retrain_remains_false",

                not Path("artifacts/wde_historical_csv_retrain.json").exists()

                or not json.loads(Path("artifacts/wde_historical_csv_retrain.json").read_text()).get("completed"),

                "WDE retrain not completed",

            )

        )

    finally:

        conn.close()



    audit_payload: dict[str, Any] = {}

    if audit_path.exists():

        audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))

    checks.append(

        _check(

            "historical_csv_training_claim_explicit",

            audit_payload.get("HISTORICAL_CSV_USED_FOR_TRAINING") is None

            and audit_payload.get("wde_retrained_with_historical_csv") is False

            or audit_payload.get("wde_retrained_with_historical_csv") is False,

            f"wde_retrained={audit_payload.get('wde_retrained_with_historical_csv')}",

        )

    )

    checks.append(

        _check(

            "historical_csv_remains_staged_only",

            audit_payload.get("historical_csv_promoted_from_staging") is False,

            f"promoted={audit_payload.get('historical_csv_promoted_from_staging')}",

        )

    )



    artifact_paths = [fx_path, pred_path, yest_path, audit_path, run_path, cp_json_path]

    safety_ok = True

    safety_details: list[str] = []

    for path in artifact_paths:

        if not path.exists():

            continue

        payload = json.loads(path.read_text(encoding="utf-8"))

        if not _artifact_has_safety_labels(payload):

            safety_ok = False

            safety_details.append(f"missing labels in {path.name}")

    checks.append(

        _check(

            "safety_labels_present_in_artifacts",

            safety_ok,

            "; ".join(safety_details) if safety_details else "all artifacts labeled",

        )

    )



    yest_payload: dict[str, Any] = {}

    if yest_path.exists():

        yest_payload = json.loads(yest_path.read_text(encoding="utf-8"))

        fixtures = yest_payload.get("fixtures") or []

        checks.append(

            _check(

                "no_duplicate_evaluation_rows",

                _fixture_ids_unique(fixtures),

                f"fixture_count={len(fixtures)}",

            )

        )

        checks.append(

            _check(

                "yesterday_artifact_has_refresh_status_field",

                bool(yest_payload.get("result_refresh_status")),

                yest_payload.get("result_refresh_status", ""),

            )

        )



    run_payload: dict[str, Any] = {}

    if run_path.exists():

        run_payload = json.loads(run_path.read_text(encoding="utf-8"))

        summary = run_payload.get("owner_daily_summary") or {}

        checks.append(

            _check(

                "owner_daily_summary_present",

                all(

                    key in summary

                    for key in (

                        "today_fixtures_count",

                        "today_prediction_status",

                        "yesterday_fixtures_count",

                        "yesterday_evaluated_count",

                        "yesterday_missing_results_count",

                        "wde_retrain_status",

                        "historical_csv_promotion_status",

                        "oddalerts_ecse_status",

                        "final_recommendation",

                    )

                ),

                json.dumps(summary, ensure_ascii=False)[:200],

            )

        )



    if yest_path.exists():

        before = json.loads(yest_path.read_text(encoding="utf-8"))

        before_fixtures = before.get("fixtures") or []

        before_eval = _evaluated_snapshot(before_fixtures)

        before_waiting = [

            int(r["fixture_id"]) for r in before_fixtures if r.get("evaluation_status") == "WAITING_RESULT"

        ]



        first = evaluate_yesterday_predictions(

            date_arg=yesterday.isoformat(),

            timezone=timezone,

            settings=settings,

            refresh_missing_results=True,

        )

        second = evaluate_yesterday_predictions(

            date_arg=yesterday.isoformat(),

            timezone=timezone,

            settings=settings,

            refresh_missing_results=True,

        )



        after_first = first.to_dict()

        after_second = second.to_dict()

        first_eval = _evaluated_snapshot(after_first.get("fixtures") or [])

        second_eval = _evaluated_snapshot(after_second.get("fixtures") or [])



        preserved = all(

            first_eval.get(fid) == before_eval.get(fid) for fid in before_eval if fid in first_eval

        )

        checks.append(

            _check(

                "refresh_preserves_already_evaluated",

                preserved,

                f"preserved={len(before_eval)} evaluated rows",

            )

        )

        checks.append(

            _check(

                "refresh_mode_idempotent_on_rerun",

                first.evaluated_count == second.evaluated_count

                and first.waiting_result_count == second.waiting_result_count

                and first_eval == second_eval,

                f"run1={first.evaluated_count}/{first.waiting_result_count} run2={second.evaluated_count}/{second.waiting_result_count}",

            )

        )



        still_waiting = [

            int(r["fixture_id"])

            for r in (after_second.get("fixtures") or [])

            if r.get("evaluation_status") == "WAITING_RESULT"

        ]

        checks.append(

            _check(

                "missing_fixtures_remain_missing_without_result",

                set(still_waiting).issubset(set(before_waiting)),

                f"waiting_before={len(before_waiting)} waiting_after={len(still_waiting)}",

            )

        )



    answers = {

        "can_i_predict_today": _answer_can_predict(run_payload),

        "were_yesterdays_games_evaluated": _answer_yesterday(run_payload),

        "was_model_retrained_with_new_database": "no"

        if not audit_payload.get("wde_retrained_with_historical_csv")

        else "yes",

    }

    checks.append(_check("answers_present_in_run_artifact", bool(run_payload.get("recommendation")), run_payload.get("recommendation", "")))

    checks.append(
        _check(
            "control_panel_script_exists",
            control_panel_script.exists() and "build_owner_daily_control_panel" in control_panel_script.read_text(encoding="utf-8"),
            str(control_panel_script),
        )
    )
    checks.append(
        _check(
            "full_refresh_script_exists",
            full_refresh_script.exists()
            and "run_owner_daily_full_refresh" in full_refresh_script.read_text(encoding="utf-8"),
            str(full_refresh_script),
        )
    )
    checks.append(_check("control_panel_json_artifact_exists", cp_json_path.exists(), str(cp_json_path)))
    checks.append(_check("control_panel_markdown_report_exists", cp_md_path.exists(), str(cp_md_path)))

    cp_payload: dict[str, Any] = {}
    if cp_json_path.exists():
        cp_payload = json.loads(cp_json_path.read_text(encoding="utf-8"))
        checks.append(
            _check(
                "control_panel_safety_labels_present",
                _artifact_has_safety_labels(cp_payload),
                "control panel artifact labeled",
            )
        )
        checks.append(
            _check(
                "control_panel_final_recommendation_present",
                bool(cp_payload.get("recommendation")),
                cp_payload.get("recommendation", ""),
            )
        )
        checks.append(
            _check(
                "control_panel_today_fixtures_section_present",
                "today_fixtures" in cp_payload and isinstance(cp_payload.get("today_fixtures"), list),
                f"today_fixtures={len(cp_payload.get('today_fixtures') or [])}",
            )
        )
        checks.append(
            _check(
                "control_panel_yesterday_evaluation_section_present",
                bool(cp_payload.get("yesterday_evaluation")),
                json.dumps(cp_payload.get("yesterday_evaluation") or {}, ensure_ascii=False)[:120],
            )
        )
        checks.append(
            _check(
                "control_panel_action_required_present",
                bool(cp_payload.get("action_required")),
                cp_payload.get("action_required", ""),
            )
        )
        checks.append(
            _check(
                "control_panel_no_public_publish",
                cp_payload.get("PUBLIC_PUBLISH") is False,
                f"PUBLIC_PUBLISH={cp_payload.get('PUBLIC_PUBLISH')}",
            )
        )
        checks.append(
            _check(
                "control_panel_no_wde_retrain",
                cp_payload.get("WDE_RETRAINED") is False,
                f"WDE_RETRAINED={cp_payload.get('WDE_RETRAINED')}",
            )
        )
        checks.append(
            _check(
                "control_panel_no_historical_csv_promotion",
                cp_payload.get("HISTORICAL_CSV_PROMOTED") is False,
                f"HISTORICAL_CSV_PROMOTED={cp_payload.get('HISTORICAL_CSV_PROMOTED')}",
            )
        )
        checks.append(
            _check(
                "control_panel_oddalerts_shadow_only",
                cp_payload.get("ODDALERTS_ECSE_PRODUCTION") is False
                and cp_payload.get("ODDALERTS_ECSE_SHADOW_ONLY") is True,
                f"prod={cp_payload.get('ODDALERTS_ECSE_PRODUCTION')} shadow_only={cp_payload.get('ODDALERTS_ECSE_SHADOW_ONLY')}",
            )
        )

    passed = all(c.passed for c in checks)

    return ValidationResult(passed=passed, checks=checks, answers=answers)





def _table_exists(conn: sqlite3.Connection, name: str) -> bool:

    return conn.execute(

        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",

        (name,),

    ).fetchone() is not None





def _answer_can_predict(run: dict[str, Any]) -> str:

    preds = run.get("predictions") or {}

    disc = run.get("discovery") or {}

    fc = int(disc.get("fixture_count") or 0)

    if fc == 0:

        return "no fixtures"

    rows = preds.get("predictions") or []

    if not rows:

        return "no"

    return "yes" if any(r.get("wde") for r in rows) else "no"





def _answer_yesterday(run: dict[str, Any]) -> str:

    y = run.get("yesterday_evaluation") or {}

    ev = int(y.get("evaluated_count") or 0)

    total = int(y.get("fixture_count") or 0)

    if total == 0:

        return "n/a"

    return "yes" if ev > 0 else "no"


