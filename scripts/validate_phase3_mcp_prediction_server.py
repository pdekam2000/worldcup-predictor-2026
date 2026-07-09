#!/usr/bin/env python3
"""Phase 3 — offline/static validator for MCP prediction server."""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PHASE = "PHASE-3-MCP-PREDICTION-SERVER"

MCP_ROOT = ROOT / "worldcup_predictor" / "mcp_server"
PROTECTED_PREFIXES = (
    "worldcup_predictor/orchestration/predict_pipeline.py",
    "worldcup_predictor/research/ecse_live/prediction_builder.py",
    "worldcup_predictor/odds/freshness_policy.py",
    "worldcup_predictor/odds/strict_live_refresh.py",
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"API_FOOTBALL_KEY\s*=\s*['\"][^'\"]+['\"]"),
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _grep_mcp(pattern: str) -> list[str]:
    hits: list[str] = []
    for path in MCP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(pattern, text):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def _git_diff_protected() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    touched = []
    for prefix in PROTECTED_PREFIXES:
        if any(c == prefix or c.startswith(prefix) for c in changed):
            touched.append(prefix)
    return touched


def main() -> int:
    checks: list[dict] = []

    checks.append(_check("mcp_package_exists", MCP_ROOT.is_dir(), str(MCP_ROOT)))
    checks.append(_check("server_module_exists", (MCP_ROOT / "server.py").is_file()))

    from worldcup_predictor.mcp_server.policies import APPROVED_TOOLS, FORBIDDEN_TOOL_NAMES

    checks.append(
        _check(
            "approved_tool_allowlist",
            APPROVED_TOOLS
            == frozenset(
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
            ),
            f"count={len(APPROVED_TOOLS)}",
        )
    )

    server_src = (MCP_ROOT / "server.py").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_TOOL_NAMES:
        checks.append(
            _check(
                f"forbidden_tool_absent:{forbidden}",
                f'name="{forbidden}"' not in server_src and f"name='{forbidden}'" not in server_src,
            )
        )

    checks.append(_check("no_shell_tool", not _grep_mcp(r"@mcp\.tool\(name=[\"']shell")))
    server_py = MCP_ROOT / "server.py"
    tools_dir = MCP_ROOT / "tools"
    scan_paths = [server_py, *tools_dir.rglob("*.py")]
    sql_hits = [
        str(p.relative_to(ROOT))
        for p in scan_paths
        if p.is_file() and re.search(r"query_database|execute\(.*sql", p.read_text(encoding="utf-8", errors="replace"), re.I)
    ]
    checks.append(_check("no_sql_tool", len(sql_hits) == 0, ", ".join(sql_hits)))
    file_tool_hits = [
        str(p.relative_to(ROOT))
        for p in scan_paths
        if p.is_file()
        and re.search(
            r"@mcp\.tool\(name=[\"'](read_file|write_file|delete_file)",
            p.read_text(encoding="utf-8", errors="replace"),
        )
    ]
    checks.append(_check("no_arbitrary_file_tool", len(file_tool_hits) == 0))
    restart_hits = [
        str(p.relative_to(ROOT))
        for p in scan_paths
        if p.is_file()
        and re.search(
            r"@mcp\.tool\(name=[\"'](restart_service|systemctl)",
            p.read_text(encoding="utf-8", errors="replace"),
        )
    ]
    checks.append(_check("no_service_restart_tool", len(restart_hits) == 0))

    runtime_src = (MCP_ROOT / "runtime.py").read_text(encoding="utf-8")
    checks.append(_check("wde_delegates_predict_pipeline", "run_daily_wde" in runtime_src))
    checks.append(_check("ecse_delegates_live_builder", "run_daily_ecse" in runtime_src))
    checks.append(_check("freshness_uses_canonical", "build_fixture_freshness_metadata" in runtime_src))
    checks.append(_check("refresh_uses_strict_live", "refresh_fixture_odds_live" in runtime_src))
    checks.append(_check("oddalerts_crosswalk_in_strict_module", (ROOT / "worldcup_predictor/odds/strict_live_refresh.py").is_file()))

    from worldcup_predictor.mcp_server.policies import (
        MAX_AUDIT_FIXTURES,
        MAX_PREDICTION_FIXTURES,
        MAX_REFRESH_FIXTURES,
        MAX_RESOLVE_MATCHES,
    )

    checks.append(_check("batch_limits_defined", MAX_RESOLVE_MATCHES == 20 and MAX_REFRESH_FIXTURES == 10))
    checks.append(_check("prediction_limit_10", MAX_PREDICTION_FIXTURES == 10 and MAX_AUDIT_FIXTURES == 20))

    policies = importlib.import_module("worldcup_predictor.mcp_server.policies")
    try:
        policies.validate_positive_fixture_id(-1)
        checks.append(_check("fixture_integer_validation", False, "accepted negative"))
    except ValueError:
        checks.append(_check("fixture_integer_validation", True))
    try:
        policies.validate_iso_date("07/09/2026")
        checks.append(_check("date_validation", False))
    except ValueError:
        checks.append(_check("date_validation", True))

    checks.append(_check("report_path_restriction", "REPORTS_DIR" in (MCP_ROOT / "runtime.py").read_text(encoding="utf-8")))
    checks.append(_check("audit_logging_module", (MCP_ROOT / "audit.py").is_file()))
    checks.append(_check("secret_redaction", "redact_secrets" in (MCP_ROOT / "audit.py").read_text(encoding="utf-8")))
    checks.append(_check("git_sha_module_exists", (MCP_ROOT / "git_sha.py").is_file()))
    health_src = (MCP_ROOT / "tools/health.py").read_text(encoding="utf-8")
    checks.append(_check("health_uses_git_sha_resolver", "resolve_current_git_sha" in health_src))
    checks.append(
        _check(
            "health_does_not_use_stale_manifest_commit",
            "build_version_payload" not in health_src,
        )
    )
    install_src = (ROOT / "scripts/install_worldcup_mcp_service.sh").read_text(encoding="utf-8")
    checks.append(_check("installer_audit_dir_mode_0750", "chmod 0750" in install_src and '0750 -o' in install_src))
    checks.append(_check("installer_audit_file_mode_0640", "chmod 0640" in install_src))
    checks.append(_check("installer_audit_append_check", "test -w" in install_src))

    from worldcup_predictor.mcp_server.config import load_mcp_config

    cfg = load_mcp_config()
    checks.append(_check("default_bind_localhost", cfg.host == "127.0.0.1"))
    checks.append(_check("no_public_bind_default", cfg.host != "0.0.0.0"))

    secret_hits: list[str] = []
    for path in MCP_ROOT.rglob("*.py"):
        for pat in SECRET_PATTERNS:
            if pat.search(path.read_text(encoding="utf-8", errors="replace")):
                secret_hits.append(str(path))
    checks.append(_check("no_committed_tokens", len(secret_hits) == 0, ", ".join(secret_hits[:5])))

    touched = _git_diff_protected()
    checks.append(_check("no_wde_formula_modification", "predict_pipeline.py" not in touched))
    checks.append(_check("no_ecse_formula_modification", "ecse_live/prediction_builder.py" not in touched))
    checks.append(_check("no_freshness_threshold_modification", "freshness_policy.py" not in touched))
    checks.append(_check("no_provider_priority_modification", "strict_live_refresh.py" not in touched))
    checks.append(_check("no_db_schema_modification_in_mcp", not _grep_mcp(r"CREATE TABLE|ALTER TABLE")))
    checks.append(_check("no_model_retraining", not _grep_mcp(r"fit\(|train\(|retrain")))

    poisson_hits = _grep_mcp(r"simplified.*poisson|poisson.*fallback")
    checks.append(_check("no_simplified_poisson_fallback", len(poisson_hits) == 0))

    proc = subprocess.run(
        [sys.executable, "-m", "worldcup_predictor.mcp_server.server", "--dry-test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    checks.append(
        _check(
            "stdio_dry_test_mode",
            proc.returncode == 0 and "approved_tools" in proc.stdout,
            proc.stderr[:200] if proc.returncode != 0 else "",
        )
    )

    all_passed = all(c["passed"] for c in checks)
    payload = {"phase": PHASE, "all_passed": all_passed, "checks": checks}
    print(json.dumps(payload, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
