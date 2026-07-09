"""Phase 1 SSH scaffold unit tests (no server, no SSH)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from phase1_ssh_scaffold import (  # noqa: E402
    append_authorized_key_if_missing,
    build_ssh_host_block,
    merge_ssh_config,
    normalize_log_lines,
    scan_text_for_secrets,
    validate_sudoers_content,
)

SUDOERS = (ROOT / "deployment" / "sudoers" / "worldcup-deploy").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "scripts" / "bootstrap_hetzner_deploy_user.sh").read_text(encoding="utf-8")
WINDOWS_PS1 = (ROOT / "scripts" / "setup_hetzner_ssh_windows.ps1").read_text(encoding="utf-8")


def test_build_ssh_host_block_no_hardcoded_ip():
    block = build_ssh_host_block("example.com")
    assert "HostName example.com" in block
    assert "worldcup-prod" in block
    assert "worldcup_hetzner_ed25519" in block


def test_merge_ssh_config_idempotent_managed_block():
    first = merge_ssh_config("", "host1.example")
    second = merge_ssh_config(first, "host2.example")
    assert second.count("Host worldcup-prod") == 1
    assert "HostName host2.example" in second
    assert "HostName host1.example" not in second


def test_merge_ssh_config_does_not_duplicate_host():
    base = "Host other\n  HostName x\n"
    out = merge_ssh_config(base, "prod.example")
    assert out.count("Host worldcup-prod") == 1
    assert "Host other" in out


def test_append_authorized_key_no_duplicate():
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyComment comment"
    existing = key + "\n"
    out, added = append_authorized_key_if_missing(existing, key)
    assert added is False
    assert out.strip().count("ssh-ed25519") == 1


def test_append_authorized_key_appends_new():
    key1 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeyOne comment"
    key2 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeyTwo comment"
    out, added = append_authorized_key_if_missing(key1 + "\n", key2)
    assert added is True
    assert "KeyTwo" in out


def test_normalize_log_lines_default_and_max():
    assert normalize_log_lines(100) == 100
    assert normalize_log_lines("50") == 50
    with pytest.raises(ValueError):
        normalize_log_lines(501)
    with pytest.raises(ValueError):
        normalize_log_lines("abc")
    with pytest.raises(ValueError):
        normalize_log_lines(0)


def test_sudoers_has_no_unrestricted_nopasswd():
    violations = validate_sudoers_content(SUDOERS)
    assert violations == []
    active = "\n".join(ln for ln in SUDOERS.splitlines() if ln.strip() and not ln.strip().startswith("#"))
    assert "NOPASSWD: ALL" not in active


def test_bootstrap_script_no_password_storage():
    assert "DEPLOY_PUBLIC_KEY" in BOOTSTRAP
    assert "password" not in BOOTSTRAP.lower() or "password authentication" in BOOTSTRAP.lower()


def test_windows_script_preserves_existing_key_message():
    assert "Existing private key preserved" in WINDOWS_PS1
    assert "ed25519" in WINDOWS_PS1


def test_no_private_key_block_in_scaffold_files():
    for rel in (
        "scripts/setup_hetzner_ssh_windows.ps1",
        "scripts/bootstrap_hetzner_deploy_user.sh",
        "deployment/sudoers/worldcup-deploy",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not scan_text_for_secrets(text), rel


def test_logs_wrapper_script_enforces_max_in_source():
    logs = (ROOT / "scripts/ops/worldcup_logs.sh").read_text(encoding="utf-8")
    assert "MAX_LINES=500" in logs
    assert 'SERVICE="worldcup-api"' in logs


def test_status_wrapper_no_service_argument():
    status = (ROOT / "scripts/ops/worldcup_service_status.sh").read_text(encoding="utf-8")
    assert "$1" not in status
    assert 'SERVICE="worldcup-api"' in status
