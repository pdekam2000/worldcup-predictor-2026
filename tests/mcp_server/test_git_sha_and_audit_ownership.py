"""Tests for MCP Git SHA reporting and audit ownership contracts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from worldcup_predictor.mcp_server.audit import redact_secrets
from worldcup_predictor.mcp_server.git_sha import resolve_current_git_sha
from worldcup_predictor.mcp_server.tools.health import server_health


def test_resolve_git_sha_from_repo_head(monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    for key in ("DEPLOY_COMMIT", "GIT_COMMIT", "DEPLOYMENT_SHA"):
        monkeypatch.delenv(key, raising=False)
    result = resolve_current_git_sha(repo_root=repo_root)
    assert result["git_sha_source"] == "git_head"
    sha = result["current_git_sha"]
    assert isinstance(sha, str)
    assert len(sha) == 40
    assert sha == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
    ).strip().lower()


def test_stale_build_manifest_not_used_for_mcp_health(monkeypatch):
    monkeypatch.setattr(
        "worldcup_predictor.mcp_server.tools.health.resolve_current_git_sha",
        lambda **_: {"current_git_sha": "1422629d1bc163fa9d855e3996bd0940918e4162", "git_sha_source": "git_head"},
    )
    payload = server_health()
    assert payload["current_git_sha"] == "1422629d1bc163fa9d855e3996bd0940918e4162"
    assert payload["git_sha_source"] == "git_head"
    assert payload["current_git_sha"] != "d8fd1ab"


def test_invalid_env_sha_rejected(tmp_path: Path):
    with mock.patch.dict(os.environ, {"DEPLOY_COMMIT": "not-a-sha"}, clear=True):
        result = resolve_current_git_sha(repo_root=tmp_path)
    assert result["git_sha_source"] == "unavailable"
    assert result["current_git_sha"] is None


def test_valid_deployment_env_sha_accepted(tmp_path: Path):
    full = "1422629d1bc163fa9d855e3996bd0940918e4162"
    with mock.patch.dict(os.environ, {"DEPLOY_COMMIT": full}, clear=True):
        result = resolve_current_git_sha(repo_root=tmp_path)
    assert result == {"current_git_sha": full, "git_sha_source": "deployment_env"}


def test_missing_git_repo_returns_unavailable(tmp_path: Path):
    with mock.patch.dict(os.environ, {}, clear=True):
        result = resolve_current_git_sha(repo_root=tmp_path)
    assert result == {"current_git_sha": None, "git_sha_source": "unavailable"}


def test_no_mcp_input_controls_git_execution():
    import inspect

    sig = inspect.signature(resolve_current_git_sha)
    assert "repo_root" in sig.parameters
    src = Path(__file__).resolve().parents[2] / "worldcup_predictor/mcp_server/git_sha.py"
    text = src.read_text(encoding="utf-8")
    assert '["git", "rev-parse", "HEAD"]' in text


def test_full_sha_preferred_from_env(tmp_path: Path):
    short = "1422629"
    with mock.patch.dict(os.environ, {"GIT_COMMIT": short}, clear=True):
        result = resolve_current_git_sha(repo_root=tmp_path)
    assert result["current_git_sha"] == short
    assert result["git_sha_source"] == "deployment_env"


def test_install_script_audit_ownership_contract():
    script = Path(__file__).resolve().parents[2] / "scripts/install_worldcup_mcp_service.sh"
    text = script.read_text(encoding="utf-8")
    assert 'chmod 0640 "${AUDIT_FILE}"' in text
    assert 'chmod 0750 "${AUDIT_DIR}"' in text
    assert 'chown "${SERVICE_USER}:${SERVICE_USER}" "${AUDIT_FILE}"' in text
    assert "sudo -u" in text and "test -w" in text


def test_audit_secret_redaction():
    raw = "Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz"
    assert "[REDACTED]" in redact_secrets(raw)
    assert "sk-abc" not in redact_secrets(raw)


def test_server_health_includes_git_sha_fields(monkeypatch):
    monkeypatch.setattr(
        "worldcup_predictor.mcp_server.tools.health.resolve_current_git_sha",
        lambda **_: {"current_git_sha": "abc1234", "git_sha_source": "git_head"},
    )
    payload = server_health()
    assert "current_git_sha" in payload
    assert "git_sha_source" in payload
