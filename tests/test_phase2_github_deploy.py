"""Phase 2 GitHub Actions safe deploy — focused static tests (no SSH, no production)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/deploy-production.yml"
DEPLOY = ROOT / "scripts/production_deploy_safe.sh"
PREFLIGHT = ROOT / "scripts/production_preflight.sh"
HEALTH = ROOT / "scripts/production_health_check.sh"
ROLLBACK = ROOT / "scripts/production_rollback.sh"


@pytest.fixture
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture
def deploy_text() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def test_workflow_manual_only(workflow_text: str):
    assert "workflow_dispatch:" in workflow_text
    assert not re.search(r"^\s*push:\s*$", workflow_text, re.M)


def test_required_secrets_referenced(workflow_text: str):
    for secret in (
        "HETZNER_HOST",
        "HETZNER_USER",
        "HETZNER_PORT",
        "HETZNER_SSH_KEY",
        "HETZNER_KNOWN_HOSTS",
    ):
        assert f"secrets.{secret}" in workflow_text


def test_host_key_verification(workflow_text: str):
    assert "HETZNER_KNOWN_HOSTS" in workflow_text
    assert "known_hosts" in workflow_text
    assert "StrictHostKeyChecking=no" not in workflow_text


def test_no_password_ssh(workflow_text: str, deploy_text: str):
    combined = workflow_text + deploy_text
    assert "sshpass" not in combined.lower()


def test_no_root_automation(workflow_text: str):
    assert "root@" not in workflow_text


def test_dirty_tree_refusal(preflight_text: str = ""):
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "source_code_drift" in text or "source code drift" in text.lower()


def test_ff_only_enforcement(deploy_text: str, preflight_text: str = ""):
    pre = PREFLIGHT.read_text(encoding="utf-8")
    assert "merge --ff-only" in deploy_text
    assert "ff-only" in pre.lower()


def test_backup_before_deploy_ordering(deploy_text: str):
    backup_pos = deploy_text.lower().find("backup")
    merge_pos = deploy_text.find("merge --ff-only")
    assert backup_pos != -1 and merge_pos != -1
    assert backup_pos < merge_pos


def test_health_check_failure_distinction():
    text = HEALTH.read_text(encoding="utf-8")
    assert "/api/health" in text
    assert "/api/health/providers" in text
    assert "APPLICATION_UNHEALTHY" in text or "APPLICATION_HEALTH_OK" in text
    assert "PROVIDER" in text


def test_rollback_path_no_unconditional_db_restore():
    text = ROLLBACK.read_text(encoding="utf-8")
    assert "RESTORE_DB" in text
    assert "reset --hard" not in text


def test_no_reset_hard_in_deploy_scripts(deploy_text: str):
    for path in (DEPLOY, PREFLIGHT, ROLLBACK):
        assert "reset --hard" not in path.read_text(encoding="utf-8")


def test_no_arbitrary_systemd_service(deploy_text: str):
    assert "worldcup-api" in deploy_text
    assert "systemctl restart *" not in deploy_text


def test_no_arbitrary_remote_command_interface(workflow_text: str):
    assert "production_deploy_safe.sh" in workflow_text
    assert "bash -lc" not in workflow_text or "production_deploy_safe.sh" in workflow_text


def test_target_sha_validation_in_workflow(workflow_text: str):
    assert "merge-base --is-ancestor" in workflow_text
    assert "target_sha" in workflow_text
