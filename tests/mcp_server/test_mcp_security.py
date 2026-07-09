"""MCP server security and policy tests."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from worldcup_predictor.mcp_server.audit import redact_secrets
from worldcup_predictor.mcp_server.policies import (
    APPROVED_TOOLS,
    FORBIDDEN_TOOL_NAMES,
    MAX_PREDICTION_FIXTURES,
    MAX_REFRESH_FIXTURES,
    MAX_RESOLVE_MATCHES,
    validate_iso_date,
    validate_positive_fixture_id,
    validate_team_name,
)
from worldcup_predictor.mcp_server import runtime
from worldcup_predictor.mcp_server.server import dry_test


def test_tool_allowlist_matches_dry_test():
    manifest = dry_test()
    assert set(manifest["approved_tools"]) == set(APPROVED_TOOLS)
    assert manifest["tool_count"] == 10


def test_forbidden_shell_tool_names_not_registered():
    server_src = (Path(__file__).resolve().parents[2] / "worldcup_predictor/mcp_server/server.py").read_text(
        encoding="utf-8"
    )
    for name in FORBIDDEN_TOOL_NAMES:
        assert f'name="{name}"' not in server_src


def test_forbidden_sql_not_in_runtime():
    src = inspect.getsource(runtime)
    assert "execute(" not in src or "SELECT fixture_id" in src
    assert "query_database" not in src


def test_fixture_validation_rejects_invalid():
    with pytest.raises(ValueError):
        validate_positive_fixture_id(0)
    with pytest.raises(ValueError):
        validate_iso_date("2026/07/09")
    with pytest.raises(ValueError):
        validate_team_name("../etc", field="home_team")


def test_batch_limits_constants():
    assert MAX_RESOLVE_MATCHES == 20
    assert MAX_REFRESH_FIXTURES == 10
    assert MAX_PREDICTION_FIXTURES == 10


def test_freshness_gate_delegates_canonical():
    src = inspect.getsource(runtime._freshness_record)
    assert "build_fixture_freshness_metadata" in src


def test_report_path_restriction():
    src = inspect.getsource(runtime._approved_report_files)
    assert "REPORTS_DIR" in src


def test_provider_fallback_contract():
    src = inspect.getsource(runtime.refresh_stale_odds)
    assert "refresh_fixture_odds_live" in src


def test_oddalerts_crosswalk_safety_module_exists():
    path = Path(__file__).resolve().parents[2] / "worldcup_predictor/odds/strict_live_refresh.py"
    text = path.read_text(encoding="utf-8")
    assert "oddalerts" in text.lower()
    assert "crosswalk" in text.lower()


def test_prediction_blocked_structure():
    # Offline: fixture 999999999 should not exist
    result = runtime.run_fixture_prediction(999999999, refresh_if_stale=False)
    assert result["quality"]["status"] in ("FAILED", "BLOCKED")


def test_prediction_pipeline_delegation():
    src = inspect.getsource(runtime.run_fixture_prediction)
    assert "run_daily_wde" in src
    assert "run_daily_ecse" in src
    assert "strict_fresh_odds=True" in src


def test_report_path_restriction():
    src = inspect.getsource(runtime._approved_report_files)
    assert "REPORTS_DIR" in src


def test_secret_redaction():
    dirty = "Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz"
    assert "[REDACTED]" in redact_secrets(dirty)


def test_audit_logging_module_writes(tmp_path):
    from worldcup_predictor.mcp_server.audit import AuditLogger

    log = tmp_path / "audit.jsonl"
    logger = AuditLogger(str(log))
    logger.write(tool_name="server_health", caller_mode="test", duration_ms=1, success=True)
    assert log.read_text(encoding="utf-8").strip()


def test_transport_bind_policy():
    from worldcup_predictor.mcp_server.config import load_mcp_config

    cfg = load_mcp_config()
    assert cfg.host == "127.0.0.1"
    assert cfg.bind_localhost_only
