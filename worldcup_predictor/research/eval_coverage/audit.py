"""Read-only evaluation coverage audit against canonical SQLite DB."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_exists

PHASE = "EVAL-COVERAGE-1"

FINISHED_STATUSES = ("FT", "AET", "PEN")
WC_KEY = "world_cup_2026"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def _max_ts(conn: sqlite3.Connection, table: str, column: str) -> str | None:
    if not table_exists(conn, table):
        return None
    try:
        row = conn.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
        return row[0] if row and row[0] else None
    except sqlite3.Error:
        return None


def _knockout_clause(alias: str = "f") -> str:
    rn = f"LOWER(COALESCE({alias}.round_name, ''))"
    return (
        f"({rn} LIKE '%round of 16%' OR {rn} LIKE '%quarter%' OR {rn} LIKE '%semi%'"
        f" OR {rn} LIKE '%final%' OR {rn} LIKE '%knockout%' OR {rn} LIKE '%play-off%'"
        f" OR {rn} LIKE '%playoff%')"
    )


def run_coverage_audit(db_path: str | None = None) -> dict[str, Any]:
    conn = connect_readonly(db_path)
    finished_in = ",".join(f"'{s}'" for s in FINISHED_STATUSES)
    ko = _knockout_clause("f")

    total_fixtures = _scalar(
        conn,
        "SELECT COUNT(*) FROM fixtures WHERE is_placeholder = 0",
    )
    wc_fixtures = _scalar(
        conn,
        "SELECT COUNT(*) FROM fixtures WHERE is_placeholder = 0 AND competition_key = ?",
        (WC_KEY,),
    )
    finished_all = _scalar(
        conn,
        f"SELECT COUNT(*) FROM fixtures WHERE is_placeholder = 0 AND UPPER(status) IN ({finished_in})",
    )
    finished_wc = _scalar(
        conn,
        f"""SELECT COUNT(*) FROM fixtures f
            WHERE f.is_placeholder = 0 AND f.competition_key = ?
              AND UPPER(f.status) IN ({finished_in})""",
        (WC_KEY,),
    )
    finished_with_result = _scalar(
        conn,
        f"""SELECT COUNT(*) FROM fixtures f
            JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0 AND f.competition_key = ?
              AND UPPER(f.status) IN ({finished_in})
              AND fr.home_goals IS NOT NULL AND fr.away_goals IS NOT NULL""",
        (WC_KEY,),
    )
    finished_without_result = finished_wc - finished_with_result

    has_wde = table_exists(conn, "worldcup_stored_predictions")
    has_wde_eval = table_exists(conn, "worldcup_prediction_evaluations")
    has_ecse = table_exists(conn, "ecse_prediction_snapshots")
    has_ecse_eval = table_exists(conn, "ecse_prediction_evaluations")

    finished_with_wde = 0
    finished_with_ecse = 0
    finished_with_any_pred = 0
    finished_pred_no_wde_eval = 0
    finished_pred_no_ecse_eval = 0
    finished_pred_no_any_eval = 0
    wde_pending = 0
    ecse_pending = 0
    wde_evaluated = 0
    ecse_evaluated = 0
    wde_ecse_knockout_eval = 0
    wde_ecse_wc_eval = 0
    ecse_finished_with_result = 0

    if has_wde:
        finished_with_wde = _scalar(
            conn,
            f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                JOIN worldcup_stored_predictions sp ON sp.fixture_id = f.fixture_id
                WHERE f.is_placeholder = 0 AND f.competition_key = ?
                  AND UPPER(f.status) IN ({finished_in})""",
            (WC_KEY,),
        )
    if has_ecse:
        finished_with_ecse = _scalar(
            conn,
            f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
                WHERE f.is_placeholder = 0 AND f.competition_key = ?
                  AND UPPER(f.status) IN ({finished_in})""",
            (WC_KEY,),
        )
        ecse_finished_with_result = _scalar(
            conn,
            f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
                JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
                WHERE f.is_placeholder = 0 AND f.competition_key = ?
                  AND UPPER(f.status) IN ({finished_in})
                  AND fr.home_goals IS NOT NULL""",
            (WC_KEY,),
        )

    finished_with_any_pred = _scalar(
        conn,
        f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
            WHERE f.is_placeholder = 0 AND f.competition_key = ?
              AND UPPER(f.status) IN ({finished_in})
              AND (
                EXISTS (SELECT 1 FROM worldcup_stored_predictions sp WHERE sp.fixture_id = f.fixture_id)
                OR EXISTS (SELECT 1 FROM ecse_prediction_snapshots ec WHERE ec.fixture_id = f.fixture_id)
              )"""
        if has_wde or has_ecse
        else "SELECT 0",
        (WC_KEY,) if has_wde or has_ecse else (),
    )

    if has_wde and has_wde_eval:
        finished_pred_no_wde_eval = _scalar(
            conn,
            f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                JOIN worldcup_stored_predictions sp ON sp.fixture_id = f.fixture_id
                LEFT JOIN worldcup_prediction_evaluations ev ON ev.fixture_id = f.fixture_id
                WHERE f.is_placeholder = 0 AND f.competition_key = ?
                  AND UPPER(f.status) IN ({finished_in})
                  AND ev.fixture_id IS NULL""",
            (WC_KEY,),
        )
        wde_pending = finished_pred_no_wde_eval
        wde_evaluated = _scalar(
            conn,
            "SELECT COUNT(*) FROM worldcup_prediction_evaluations WHERE competition_key = ?",
            (WC_KEY,),
        )

    if has_ecse and has_ecse_eval:
        finished_pred_no_ecse_eval = _scalar(
            conn,
            f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
                JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
                LEFT JOIN ecse_prediction_evaluations ee ON ee.fixture_id = f.fixture_id
                WHERE f.is_placeholder = 0 AND f.competition_key = ?
                  AND UPPER(f.status) IN ({finished_in})
                  AND fr.home_goals IS NOT NULL
                  AND ee.fixture_id IS NULL""",
            (WC_KEY,),
        )
        ecse_pending = finished_pred_no_ecse_eval
        ecse_evaluated = _scalar(conn, "SELECT COUNT(*) FROM ecse_prediction_evaluations")

    if (has_wde or has_ecse) and (has_wde_eval or has_ecse_eval):
        finished_pred_no_any_eval = _scalar(
            conn,
            f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
                WHERE f.is_placeholder = 0 AND f.competition_key = ?
                  AND UPPER(f.status) IN ({finished_in})
                  AND fr.home_goals IS NOT NULL
                  AND (
                    EXISTS (SELECT 1 FROM worldcup_stored_predictions sp WHERE sp.fixture_id = f.fixture_id)
                    OR EXISTS (SELECT 1 FROM ecse_prediction_snapshots ec WHERE ec.fixture_id = f.fixture_id)
                  )
                  AND NOT (
                    EXISTS (SELECT 1 FROM worldcup_prediction_evaluations wv WHERE wv.fixture_id = f.fixture_id)
                    OR EXISTS (SELECT 1 FROM ecse_prediction_evaluations ev WHERE ev.fixture_id = f.fixture_id)
                  )""",
            (WC_KEY,),
        )

    wde_ecse_knockout_eval = _scalar(
        conn,
        f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
            JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
            JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
            JOIN ecse_prediction_evaluations ee ON ee.fixture_id = f.fixture_id
            LEFT JOIN worldcup_prediction_evaluations wv ON wv.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0 AND f.competition_key = ?
              AND UPPER(f.status) IN ({finished_in})
              AND fr.home_goals IS NOT NULL
              AND {ko}
              AND wv.fixture_id IS NOT NULL"""
        if has_ecse_eval and has_wde_eval
        else "SELECT 0",
        (WC_KEY,) if has_ecse_eval and has_wde_eval else (),
    )

    wde_ecse_wc_eval = _scalar(
        conn,
        f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
            JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
            JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
            JOIN ecse_prediction_evaluations ee ON ee.fixture_id = f.fixture_id
            LEFT JOIN worldcup_prediction_evaluations wv ON wv.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0 AND f.competition_key = ?
              AND UPPER(f.status) IN ({finished_in})
              AND fr.home_goals IS NOT NULL
              AND wv.fixture_id IS NOT NULL"""
        if has_ecse_eval and has_wde_eval
        else "SELECT 0",
        (WC_KEY,) if has_ecse_eval and has_wde_eval else (),
    )

    ecse_research_finished = _scalar(
        conn,
        f"""SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
            JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
            JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0 AND f.competition_key = ?
              AND UPPER(f.status) IN ({finished_in})
              AND fr.home_goals IS NOT NULL"""
        if has_ecse
        else "SELECT 0",
        (WC_KEY,) if has_ecse else (),
    )

    rows = [
        {
            "category": "Total fixtures (all competitions)",
            "count": total_fixtures,
            "data_source_table": "fixtures",
            "newest_timestamp": _max_ts(conn, "fixtures", "updated_at"),
            "notes": "is_placeholder=0",
        },
        {
            "category": "Total WC 2026 fixtures",
            "count": wc_fixtures,
            "data_source_table": "fixtures",
            "newest_timestamp": _max_ts(conn, "fixtures", "updated_at"),
            "notes": f"competition_key={WC_KEY}",
        },
        {
            "category": "Finished fixtures (all competitions)",
            "count": finished_all,
            "data_source_table": "fixtures",
            "newest_timestamp": _max_ts(conn, "fixtures", "updated_at"),
            "notes": f"status in {FINISHED_STATUSES}",
        },
        {
            "category": "Finished WC fixtures",
            "count": finished_wc,
            "data_source_table": "fixtures",
            "newest_timestamp": _max_ts(conn, "fixtures", "updated_at"),
            "notes": f"status in {FINISHED_STATUSES}",
        },
        {
            "category": "Finished WC with real result (90' goals)",
            "count": finished_with_result,
            "data_source_table": "fixtures + fixture_results",
            "newest_timestamp": _max_ts(conn, "fixture_results", "finished_at"),
            "notes": "home_goals/away_goals NOT NULL",
        },
        {
            "category": "Finished WC without real result",
            "count": max(0, finished_without_result),
            "data_source_table": "fixtures LEFT JOIN fixture_results",
            "newest_timestamp": None,
            "notes": "finished status but missing fixture_results goals",
        },
        {
            "category": "Finished WC with WDE stored prediction",
            "count": finished_with_wde,
            "data_source_table": "worldcup_stored_predictions",
            "newest_timestamp": _max_ts(conn, "worldcup_stored_predictions", "generated_at")
            if has_wde
            else None,
            "notes": "",
        },
        {
            "category": "Finished WC with ECSE snapshot",
            "count": finished_with_ecse,
            "data_source_table": "ecse_prediction_snapshots",
            "newest_timestamp": _max_ts(conn, "ecse_prediction_snapshots", "generated_at")
            if has_ecse
            else None,
            "notes": "",
        },
        {
            "category": "Finished WC with any stored prediction",
            "count": finished_with_any_pred,
            "data_source_table": "worldcup_stored_predictions / ecse_prediction_snapshots",
            "newest_timestamp": None,
            "notes": "WDE and/or ECSE",
        },
        {
            "category": "Finished WC with prediction but no WDE evaluation",
            "count": finished_pred_no_wde_eval,
            "data_source_table": "worldcup_stored_predictions LEFT JOIN worldcup_prediction_evaluations",
            "newest_timestamp": None,
            "notes": "pending WDE eval",
        },
        {
            "category": "Finished WC with ECSE+result but no ECSE evaluation",
            "count": finished_pred_no_ecse_eval,
            "data_source_table": "ecse_prediction_snapshots LEFT JOIN ecse_prediction_evaluations",
            "newest_timestamp": None,
            "notes": "pending ECSE eval",
        },
        {
            "category": "Finished WC with prediction but no any evaluation",
            "count": finished_pred_no_any_eval,
            "data_source_table": "combined",
            "newest_timestamp": None,
            "notes": "missing both WDE and ECSE eval rows",
        },
        {
            "category": "WDE stored predictions pending evaluation",
            "count": wde_pending,
            "data_source_table": "worldcup_stored_predictions",
            "newest_timestamp": None,
            "notes": "finished + stored + no worldcup_prediction_evaluations row",
        },
        {
            "category": "ECSE snapshots pending evaluation",
            "count": ecse_pending,
            "data_source_table": "ecse_prediction_snapshots",
            "newest_timestamp": None,
            "notes": "finished + result + no ecse_prediction_evaluations row",
        },
        {
            "category": "WDE evaluations (WC)",
            "count": wde_evaluated,
            "data_source_table": "worldcup_prediction_evaluations",
            "newest_timestamp": _max_ts(conn, "worldcup_prediction_evaluations", "evaluated_at")
            if has_wde_eval
            else None,
            "notes": "",
        },
        {
            "category": "ECSE evaluations (all)",
            "count": ecse_evaluated,
            "data_source_table": "ecse_prediction_evaluations",
            "newest_timestamp": _max_ts(conn, "ecse_prediction_evaluations", "evaluated_at")
            if has_ecse_eval
            else None,
            "notes": "",
        },
        {
            "category": "Evaluated WDE+ECSE WC knockout (both eval rows)",
            "count": wde_ecse_knockout_eval,
            "data_source_table": "combined",
            "newest_timestamp": None,
            "notes": "research knockout sample (dual-eval)",
        },
        {
            "category": "Evaluated WDE+ECSE WC all stages (both eval rows)",
            "count": wde_ecse_wc_eval,
            "data_source_table": "combined",
            "newest_timestamp": None,
            "notes": "dual-eval finished WC",
        },
        {
            "category": "ECSE research sample (finished+result+snapshot)",
            "count": ecse_research_finished,
            "data_source_table": "ecse_prediction_snapshots + fixture_results",
            "newest_timestamp": None,
            "notes": "used by shadow optimizers (actual_90min required)",
        },
    ]

    conn.close()
    return {
        "phase": PHASE,
        "audited_at": _utc_now(),
        "db_path": db_path,
        "summary": {
            "total_fixtures": total_fixtures,
            "finished_wc": finished_wc,
            "finished_with_result": finished_with_result,
            "ecse_research_finished": ecse_research_finished,
            "wde_ecse_knockout_eval": wde_ecse_knockout_eval,
            "ecse_pending": ecse_pending,
            "wde_pending": wde_pending,
        },
        "rows": rows,
    }


def render_audit_markdown(payload: dict[str, Any], *, label: str = "Before") -> str:
    lines = [
        f"# EVAL-COVERAGE-1 — Evaluation Coverage Audit ({label})",
        "",
        f"Phase: **{PHASE}** | Audited: **{payload.get('audited_at')}**",
        "",
        "## Coverage Table",
        "",
        "| Category | Count | Data Source | Newest Timestamp | Notes |",
        "|----------|------:|-------------|------------------|-------|",
    ]
    for row in payload.get("rows", []):
        ts = row.get("newest_timestamp") or "—"
        lines.append(
            f"| {row['category']} | {row['count']} | {row['data_source_table']} | {ts} | {row.get('notes', '')} |"
        )
    s = payload.get("summary", {})
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Finished WC fixtures: **{s.get('finished_wc', 0)}**",
            f"- Finished with 90' result: **{s.get('finished_with_result', 0)}**",
            f"- ECSE research sample (finished+snapshot+result): **{s.get('ecse_research_finished', 0)}**",
            f"- ECSE pending evaluation: **{s.get('ecse_pending', 0)}**",
            f"- WDE pending evaluation: **{s.get('wde_pending', 0)}**",
            "",
        ]
    )
    return "\n".join(lines)
