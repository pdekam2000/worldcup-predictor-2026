"""MCP owner report tools."""

from __future__ import annotations

from worldcup_predictor.mcp_server.policies import MAX_REPORT_BYTES, validate_iso_date
from worldcup_predictor.mcp_server import runtime


def latest_prediction_report() -> dict[str, object]:
    return runtime.latest_prediction_report(max_bytes=MAX_REPORT_BYTES)


def prediction_report_by_date(date: str) -> dict[str, object]:
    target = validate_iso_date(date)
    return runtime.prediction_report_by_date(target, max_bytes=MAX_REPORT_BYTES)
