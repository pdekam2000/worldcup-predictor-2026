"""Read-only daily report retrieval for owner / GPT Actions."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.owner_daily.pipeline.constants import DAILY_REPORTS_DIR, REPORT_INDEX_PATH


def _read_md(path: Path, *, max_bytes: int) -> str:
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace")
    raw = content.encode("utf-8")
    if len(raw) > max_bytes:
        return raw[:max_bytes].decode("utf-8", errors="ignore") + "\n...[truncated]"
    return content


def _response(path: Path | None, *, report_type: str, report_date: str, max_bytes: int) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "found": False,
            "report_type": report_type,
            "report_date": report_date,
            "report_name": None,
            "content": "",
            "generated_at": None,
            "completeness": "missing",
            "reason": f"No {report_type} report for {report_date}",
            "source": "daily_pipeline",
        }
    return {
        "found": True,
        "report_type": report_type,
        "report_date": report_date,
        "report_name": path.name,
        "content": _read_md(path, max_bytes=max_bytes),
        "generated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "completeness": "complete",
        "reason": None,
        "source": "daily_pipeline",
    }


def get_daily_prediction_report(*, report_date: str, max_bytes: int = 200_000) -> dict[str, Any]:
    path = DAILY_REPORTS_DIR / f"{report_date}_DAILY_PREDICTIONS.md"
    return _response(path, report_type="DAILY_PREDICTIONS", report_date=report_date, max_bytes=max_bytes)


def get_daily_evaluation_report(*, report_date: str, max_bytes: int = 200_000) -> dict[str, Any]:
    path = DAILY_REPORTS_DIR / f"{report_date}_DAILY_EVALUATION.md"
    return _response(path, report_type="DAILY_EVALUATION", report_date=report_date, max_bytes=max_bytes)


def get_latest_daily_prediction_report(*, max_bytes: int = 200_000) -> dict[str, Any]:
    if REPORT_INDEX_PATH.is_file():
        try:
            index = json.loads(REPORT_INDEX_PATH.read_text(encoding="utf-8"))
            if index and isinstance(index, list):
                d = str(index[0].get("report_date") or "")
                if d:
                    return get_daily_prediction_report(report_date=d, max_bytes=max_bytes)
        except json.JSONDecodeError:
            pass
    files = sorted(DAILY_REPORTS_DIR.glob("*_DAILY_PREDICTIONS.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return _response(None, report_type="DAILY_PREDICTIONS", report_date="", max_bytes=max_bytes)
    stem = files[0].stem.replace("_DAILY_PREDICTIONS", "")
    return get_daily_prediction_report(report_date=stem, max_bytes=max_bytes)


def get_latest_daily_evaluation_report(*, max_bytes: int = 200_000) -> dict[str, Any]:
    files = sorted(DAILY_REPORTS_DIR.glob("*_DAILY_EVALUATION.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return _response(None, report_type="DAILY_EVALUATION", report_date="", max_bytes=max_bytes)
    stem = files[0].stem.replace("_DAILY_EVALUATION", "")
    return get_daily_evaluation_report(report_date=stem, max_bytes=max_bytes)


def get_fixture_frozen_evaluation(*, fixture_id: int, max_bytes: int = 100_000) -> dict[str, Any]:
    from worldcup_predictor.config.env_loading import project_root
    from worldcup_predictor.forward_evaluation.db import connect_eval_db

    ev = connect_eval_db(project_root())
    try:
        row = ev.execute(
            """
            SELECT fp.*, me.*
            FROM frozen_predictions fp
            LEFT JOIN market_evaluations me ON me.prediction_id = fp.prediction_id
            WHERE fp.fixture_id = ?
            ORDER BY fp.frozen_at DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        if not row:
            return {"found": False, "fixture_id": fixture_id, "reason": "NO_FROZEN_PREDICTION"}
        return {"found": True, "fixture_id": fixture_id, "evaluation": dict(row)}
    finally:
        ev.close()


def get_monthly_accuracy_summary(*, year: int, month: int) -> dict[str, Any]:
    prefix = f"{year:04d}-{month:02d}"
    rows = []
    if REPORT_INDEX_PATH.is_file():
        try:
            index = json.loads(REPORT_INDEX_PATH.read_text(encoding="utf-8"))
            rows = [r for r in index if str(r.get("report_date", "")).startswith(prefix)]
        except json.JSONDecodeError:
            pass
    return {"year": year, "month": month, "days": len(rows), "entries": rows}


def get_weekly_frozen_evaluation_report(*, end_date: date | None = None) -> dict[str, Any]:
    end = end_date or date.today()
    start = end.fromordinal(end.toordinal() - 6)
    entries = []
    if REPORT_INDEX_PATH.is_file():
        try:
            index = json.loads(REPORT_INDEX_PATH.read_text(encoding="utf-8"))
            for row in index:
                d = str(row.get("report_date") or "")
                try:
                    rd = date.fromisoformat(d)
                except ValueError:
                    continue
                if start <= rd <= end:
                    entries.append(row)
        except json.JSONDecodeError:
            pass
    return {"start": start.isoformat(), "end": end.isoformat(), "entries": entries}
