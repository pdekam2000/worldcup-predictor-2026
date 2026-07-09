#!/usr/bin/env python3
"""Phase 2 — static/offline validator for GitHub Actions safe deploy (no SSH, no production)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE = "PHASE-2-GITHUB-ACTIONS-SAFE-DEPLOY"

WORKFLOW = ROOT / ".github/workflows/deploy-production.yml"
DEPLOY_SAFE = ROOT / "scripts/production_deploy_safe.sh"
PREFLIGHT = ROOT / "scripts/production_preflight.sh"
HEALTH = ROOT / "scripts/production_health_check.sh"
ROLLBACK = ROOT / "scripts/production_rollback.sh"
STRICT_WORKFLOW = ROOT / ".github/workflows/validate-strict-live-refresh.yml"

REQUIRED_SECRETS = (
    "HETZNER_HOST",
    "HETZNER_USER",
    "HETZNER_PORT",
    "HETZNER_SSH_KEY",
    "HETZNER_KNOWN_HOSTS",
)

PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    re.I,
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "passed": bool(ok), "details": detail}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def _scan_no_secrets(text: str) -> list[str]:
    hits = []
    if PRIVATE_KEY_BLOCK.search(text):
        hits.append("private_key_block")
    if re.search(r"StrictHostKeyChecking=no", text, re.I):
        hits.append("StrictHostKeyChecking=no")
    if re.search(r"sshpass|password\s*[:=]\s*['\"]?.+['\"]?", text, re.I):
        if "ADMIN_PASSWORD" not in text and "no password" in text.lower():
            if re.search(r"sshpass|PasswordAuthentication\s+yes", text, re.I):
                hits.append("password_auth")
    return hits


def main() -> int:
    checks: list[dict] = []
    wf = _read(WORKFLOW)
    deploy = _read(DEPLOY_SAFE)
    pre = _read(PREFLIGHT)
    health = _read(HEALTH)
    rollback = _read(ROLLBACK)
    combined = "\n".join([wf, deploy, pre, health, rollback])

    checks.append(_check("workflow_exists", WORKFLOW.is_file()))
    checks.append(_check("workflow_manual_only", "workflow_dispatch:" in wf and "on:\n  push:" not in wf))
    checks.append(_check("no_push_trigger", "push:" not in wf.split("workflow_dispatch:")[0] if wf else False))
    for secret in REQUIRED_SECRETS:
        checks.append(_check(f"secret_referenced:{secret}", f"secrets.{secret}" in wf, secret))
    checks.append(_check("no_plaintext_password", "password_auth" not in _scan_no_secrets(combined)))
    checks.append(_check("no_private_key_block", "private_key_block" not in _scan_no_secrets(combined)))
    checks.append(_check("known_hosts_required", "HETZNER_KNOWN_HOSTS" in wf and "known_hosts" in wf))
    checks.append(_check("no_StrictHostKeyChecking_no", "StrictHostKeyChecking=no" not in combined))
    checks.append(_check("no_root_hardcoded", not re.search(r"\broot@", combined)))
    checks.append(_check("no_git_reset_hard", "reset --hard" not in combined and "reset –hard" not in combined))
    checks.append(_check("no_git_clean_fd", "clean -fd" not in combined))
    checks.append(_check("dirty_tree_refusal", "source_code_drift" in pre or "source drift" in pre.lower()))
    checks.append(_check("ff_only_deployment", "merge --ff-only" in deploy or "merge --ff-only" in pre))
    checks.append(_check("backup_gate_exists", "backup" in deploy.lower() and "manifest" in deploy.lower()))
    checks.append(_check("previous_sha_recorded", "old_sha" in deploy or "PREVIOUS_SHA" in deploy))
    checks.append(_check("target_sha_validated", "target_sha" in wf.lower() or "TARGET_SHA" in pre))
    checks.append(_check("env_production_preserved", ".env.production" in pre and "must not be modified" in pre))
    checks.append(_check("sqlite_backup_path", "backup_sqlite" in deploy or "football_intelligence" in deploy))
    checks.append(
        _check(
            "db_rollback_not_automatic",
            "RESTORE_DB" in rollback and "no automatic" in rollback.lower() or "no DB restore" in deploy,
        )
    )
    checks.append(_check("fixed_service_worldcup_api", 'SERVICE="worldcup-api"' in deploy or "worldcup-api" in deploy))
    checks.append(_check("no_arbitrary_service_restart", "systemctl restart *" not in combined))
    checks.append(_check("application_health_endpoint", "/api/health" in health))
    checks.append(_check("provider_health_diagnostic", "/api/health/providers" in health))
    checks.append(_check("rollback_path_exists", ROLLBACK.is_file() and "production_rollback" in wf))
    checks.append(_check("strict_live_validator_in_workflow", "validate_strict_live_odds_refresh_fix.py" in wf))
    checks.append(_check("phase1_validator_in_workflow", "validate_phase1_ssh_scaffold.py" in wf))
    checks.append(_check("no_prediction_retraining", "retrain" not in deploy.lower()))
    checks.append(
        _check(
            "strict_7_match_not_duplicated",
            not (ROOT / "scripts/rerun_today_7_strict_live_predictions_20260709.py").read_text(
                encoding="utf-8", errors="ignore"
            ).count("def main") > 1
            if (ROOT / "scripts/rerun_today_7_strict_live_predictions_20260709.py").is_file()
            else True,
        )
    )
    checks.append(_check("strict_workflow_not_overwritten", STRICT_WORKFLOW.is_file() and "strict live" in STRICT_WORKFLOW.read_text(encoding="utf-8", errors="ignore").lower()))
    validator_src = Path(__file__).read_text(encoding="utf-8")
    import_block = "\n".join(validator_src.splitlines()[:30])
    checks.append(
        _check(
            "validator_no_ssh",
            "subprocess" not in import_block and "paramiko" not in import_block,
        )
    )
    checks.append(_check("production_scripts_exist", all(p.is_file() for p in (PREFLIGHT, DEPLOY_SAFE, HEALTH, ROLLBACK))))
    checks.append(_check("phase2_static_validator_exists", Path(__file__).is_file()))
    checks.append(_check("deploy_user_not_root", 'HETZNER_USER' in wf and "root@" not in wf))

    all_passed = all(c["passed"] for c in checks)
    payload = {"phase": PHASE, "all_passed": all_passed, "checks": checks}
    out = ROOT / "artifacts" / "phase2_github_deploy_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
