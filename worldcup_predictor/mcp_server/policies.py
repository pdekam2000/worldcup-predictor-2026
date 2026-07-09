"""MCP policy limits and allowlists — deny by default."""

from __future__ import annotations

import re
from datetime import date

MCP_VERSION = "phase3-mcp-v1"

MAX_RESOLVE_MATCHES = 20
MAX_AUDIT_FIXTURES = 20
MAX_REFRESH_FIXTURES = 10
MAX_PREDICTION_FIXTURES = 10
MAX_REPORT_BYTES = 256_000
REQUEST_TIMEOUT_SECONDS = 120
TOOL_TIMEOUT_SECONDS = 90
MAX_CONCURRENT_PREDICTIONS = 1

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

APPROVED_TOOLS: frozenset[str] = frozenset(
    {
        "server_health",
        "model_status",
        "resolve_fixtures",
        "odds_freshness_audit",
        "refresh_stale_odds",
        "run_fixture_prediction",
        "run_batch_predictions",
        "latest_prediction_report",
        "prediction_report_by_date",
        "provider_status",
    }
)

FORBIDDEN_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "shell",
        "run_command",
        "execute",
        "execute_bash",
        "ssh",
        "sql",
        "query_database",
        "read_file",
        "write_file",
        "delete_file",
        "restart_service",
        "systemctl",
        "git_command",
        "sudo",
    }
)

APPROVED_REPORT_ROOTS: tuple[str, ...] = ("reports/owner",)


def validate_iso_date(value: str) -> date:
    text = str(value or "").strip()
    if not ISO_DATE_RE.match(text):
        raise ValueError("date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def validate_positive_fixture_id(value: object) -> int:
    try:
        fid = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("fixture_id must be a positive integer") from exc
    if fid <= 0:
        raise ValueError("fixture_id must be a positive integer")
    return fid


def validate_fixture_id_list(values: list[object], *, max_count: int, label: str) -> list[int]:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list of integers")
    if len(values) > max_count:
        raise ValueError(f"{label} exceeds maximum of {max_count}")
    return [validate_positive_fixture_id(v) for v in values]


def validate_team_name(value: str, *, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 120:
        raise ValueError(f"{field} must be a non-empty string up to 120 characters")
    if any(c in text for c in ("\x00", "/", "\\", "..")):
        raise ValueError(f"{field} contains invalid characters")
    return text
