#!/usr/bin/env python3
"""Phase 1 — local static validator for SSH scaffold (no SSH, no production)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from phase1_ssh_scaffold import (  # noqa: E402
    scan_text_for_secrets,
    validate_sudoers_content,
)

PHASE = "PHASE-1-SSH-SCAFFOLD"

REQUIRED_FILES = [
    "scripts/setup_hetzner_ssh_windows.ps1",
    "scripts/bootstrap_hetzner_deploy_user.sh",
    "deployment/sudoers/worldcup-deploy",
    "docs/HETZNER_SSH_SETUP.md",
    "scripts/ops/worldcup_service_status.sh",
    "scripts/ops/worldcup_service_restart.sh",
    "scripts/ops/worldcup_logs.sh",
    "scripts/lib/phase1_ssh_scaffold.py",
    "scripts/validate_phase1_ssh_scaffold.py",
]

FORBIDDEN_IN_SCRIPTS = (
    "git reset --hard",
)

FORBIDDEN_IN_SUDOERS_ACTIVE = (
    "NOPASSWD: ALL",
    "NOPASSWD:ALL",
)

REMOTE_MAIN_FILES = [
    ".github/workflows/validate-strict-live-refresh.yml",
    "scripts/rerun_today_7_strict_live_predictions_20260709.py",
    "worldcup_predictor/odds/strict_live_refresh.py",
    "worldcup_predictor/odds/freshness_refresh.py",
    "scripts/validate_strict_live_odds_refresh_fix.py",
]

PROTECTED_UNCHANGED_PREFIXES = (
    "worldcup_predictor/orchestration/predict_pipeline.py",
    "worldcup_predictor/research/ecse_live/",
    "worldcup_predictor/odds/freshness_policy.py",
    "deployment/systemd/worldcup-api.service",
    "deployment/nginx/",
    ".env.production",
)


def _git(args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks: list[dict] = []

    for rel in REQUIRED_FILES:
        checks.append(_check(f"file_exists:{rel}", (ROOT / rel).is_file(), rel))

    # Secret / password scan on new scaffold files only
    scaffold_paths = [ROOT / p for p in REQUIRED_FILES if (ROOT / p).is_file()]
    for path in scaffold_paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = scan_text_for_secrets(text)
        checks.append(_check(f"no_secrets:{path.name}", not hits, ", ".join(hits) if hits else ""))
        if path.suffix in {".ps1", ".sh"} and path.name != "validate_phase1_ssh_scaffold.py":
            for bad in FORBIDDEN_IN_SCRIPTS:
                if bad in text:
                    checks.append(_check(f"forbidden_pattern:{path.name}", False, bad))
        if path.name == "worldcup-deploy":
            active = "\n".join(
                ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")
            )
            for bad in FORBIDDEN_IN_SUDOERS_ACTIVE:
                if bad in active:
                    checks.append(_check(f"forbidden_sudoers_active:{path.name}", False, bad))

    ps1 = (ROOT / "scripts/setup_hetzner_ssh_windows.ps1").read_text(encoding="utf-8")
    checks.append(_check("windows_ed25519_key", "ed25519" in ps1))
    checks.append(_check("windows_no_overwrite_private_key", "never overwrite" in ps1.lower() or "Existing private key preserved" in ps1))
    checks.append(_check("windows_ssh_config_backup", ".bak." in ps1))
    checks.append(_check("windows_idempotent_host_block", "BEGIN worldcup-prod" in ps1))
    checks.append(_check("windows_no_hardcoded_ip", not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", ps1)))
    checks.append(_check("windows_dry_run", "DryRun" in ps1))
    checks.append(_check("windows_no_auto_ssh_connect", "ssh worldcup-prod" in ps1 and "ssh @" not in ps1.lower()))

    bootstrap = (ROOT / "scripts/bootstrap_hetzner_deploy_user.sh").read_text(encoding="utf-8")
    checks.append(_check("bootstrap_requires_root", "EUID" in bootstrap or "id -u" in bootstrap))
    checks.append(_check("bootstrap_idempotent_key", "already present" in bootstrap))
    checks.append(_check("bootstrap_no_sshd_change", "sshd_config" not in bootstrap.lower() or "does not modify sshd" in bootstrap.lower()))
    checks.append(_check("bootstrap_env_public_key", "DEPLOY_PUBLIC_KEY" in bootstrap))

    sudoers = (ROOT / "deployment/sudoers/worldcup-deploy").read_text(encoding="utf-8")
    violations = validate_sudoers_content(sudoers)
    checks.append(_check("sudoers_no_unrestricted", not violations, "; ".join(violations)))
    checks.append(_check("sudoers_scoped_worldcup_api", "worldcup-api" in sudoers))
    checks.append(_check("sudoers_uses_wrappers", "scripts/ops/worldcup_logs.sh" in sudoers))

    logs_sh = (ROOT / "scripts/ops/worldcup_logs.sh").read_text(encoding="utf-8")
    checks.append(_check("logs_wrapper_max_500", "MAX_LINES=500" in logs_sh))
    checks.append(_check("logs_wrapper_fixed_service", 'SERVICE="worldcup-api"' in logs_sh))
    checks.append(_check("logs_wrapper_rejects_non_numeric", "must be a positive integer" in logs_sh))

    status_sh = (ROOT / "scripts/ops/worldcup_service_status.sh").read_text(encoding="utf-8")
    checks.append(_check("status_wrapper_fixed_service", 'SERVICE="worldcup-api"' in status_sh))
    checks.append(_check("status_wrapper_no_args", "$1" not in status_sh and "$@" not in status_sh))

    # Protected files — ensure not modified in current branch diff vs HEAD (local branch base)
    diff_names = _git(["diff", "--name-only", "HEAD"])
    modified = [ln.strip() for ln in diff_names.splitlines() if ln.strip()]
    touched_protected = []
    for m in modified:
        for pref in PROTECTED_UNCHANGED_PREFIXES:
            if m == pref or m.startswith(pref):
                touched_protected.append(m)
    checks.append(_check("no_protected_prediction_files_modified", not touched_protected, ", ".join(touched_protected)))

    # Remote/main drift reconciliation report
    local_sha = _git(["rev-parse", "HEAD"])
    origin_main = _git(["rev-parse", "origin/main"])
    behind_ahead = _git(["rev-list", "--left-right", "--count", f"{local_sha}...{origin_main}"]) if local_sha and origin_main else ""
    drift_note = ""
    if behind_ahead:
        parts = behind_ahead.split()
        if len(parts) == 2 and parts[1] != "0":
            drift_note = f"local behind origin/main by {parts[1]} commits"
    remote_presence = {}
    for rel in REMOTE_MAIN_FILES:
        if (ROOT / rel).is_file():
            remote_presence[rel] = "local"
        else:
            code = subprocess.run(
                ["git", "cat-file", "-e", f"origin/main:{rel}"],
                cwd=ROOT,
                capture_output=True,
            ).returncode
            remote_presence[rel] = "origin/main" if code == 0 else "missing"
    missing_local = [k for k, v in remote_presence.items() if v != "local"]
    checks.append(
        _check(
            "remote_main_drift_documented",
            True,
            f"local_sha={local_sha} origin/main={origin_main} {drift_note} missing_local={missing_local}",
        )
    )

    all_passed = all(c["passed"] for c in checks)
    payload = {"phase": PHASE, "all_passed": all_passed, "checks": checks}
    out_path = ROOT / "artifacts" / "phase1_ssh_scaffold_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
