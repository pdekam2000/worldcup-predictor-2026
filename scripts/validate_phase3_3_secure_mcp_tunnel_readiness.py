#!/usr/bin/env python3
"""Phase 3.3 — static readiness validator for OpenAI Secure MCP Tunnel preparation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PHASE = "PHASE-3-3-SECURE-MCP-TUNNEL-READINESS"
MCP_ROOT = ROOT / "worldcup_predictor" / "mcp_server"
TUNNEL_UNIT = ROOT / "deployment/systemd/worldcup-mcp-tunnel.service"
INSTALL_SCRIPT = ROOT / "scripts/install_worldcup_mcp_tunnel.sh"
RUNBOOK = ROOT / "docs/OPENAI_SECURE_MCP_TUNNEL_RUNBOOK.md"
CHATGPT_RUNBOOK = ROOT / "docs/CHATGPT_WORLDCUP_MCP_CONNECTION_RUNBOOK.md"
REPORT = ROOT / "reports/owner/PHASE_3_3_SECURE_MCP_TUNNEL_READINESS_REPORT.md"

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"CONTROL_PLANE_API_KEY\s*=\s*sk-"),
)

LOCALHOST_MCP = "127.0.0.1:8765"
APPROVED_TOOLS = frozenset(
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


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks: list[dict] = []

    mcp_unit = (ROOT / "deployment/systemd/worldcup-mcp.service").read_text(encoding="utf-8")
    checks.append(_check("mcp_bind_localhost_only", "MCP_HOST=127.0.0.1" in mcp_unit and "0.0.0.0" not in mcp_unit))

    from worldcup_predictor.mcp_server.policies import APPROVED_TOOLS as tools

    checks.append(_check("exact_10_tool_allowlist", tools == APPROVED_TOOLS, f"count={len(tools)}"))

    tunnel_unit = TUNNEL_UNIT.read_text(encoding="utf-8")
    checks.append(_check("tunnel_service_exists", TUNNEL_UNIT.is_file()))
    checks.append(_check("tunnel_user_non_root", "User=worldcup-mcp-tunnel" in tunnel_unit))
    checks.append(_check("tunnel_no_repo_env", ".env.production" not in tunnel_unit))
    checks.append(_check("tunnel_env_outside_git", "EnvironmentFile=/etc/worldcup-mcp-tunnel/environment" in tunnel_unit))
    checks.append(_check("tunnel_no_secrets_in_execstart", "sk-" not in tunnel_unit and "Bearer " not in tunnel_unit))
    checks.append(_check("tunnel_nonewprivileges", "NoNewPrivileges=true" in tunnel_unit))
    checks.append(_check("tunnel_independent_of_api", "Requires=worldcup-api" not in tunnel_unit))
    checks.append(_check("tunnel_wants_mcp_only", "Wants=worldcup-mcp.service" in tunnel_unit))

    install_src = INSTALL_SCRIPT.read_text(encoding="utf-8")
    checks.append(_check("install_script_exists", INSTALL_SCRIPT.is_file()))
    checks.append(_check("official_openai_source_documented", "developers.openai.com/api/docs/guides/secure-mcp-tunnels" in install_src))
    checks.append(_check("official_github_release_source", "openai/tunnel-client/releases" in install_src))
    checks.append(_check("install_checksum_verification", "sha256sum -c" in install_src))
    checks.append(_check("install_no_embedded_secrets", not any(p.search(install_src) for p in SECRET_PATTERNS)))
    checks.append(_check("install_no_firewall_modification", "ufw allow" not in install_src and "iptables" not in install_src))
    checks.append(_check("install_no_nginx_modification", "nginx" not in install_src))
    checks.append(_check("install_no_ngrok", "ngrok" not in install_src.lower()))
    checks.append(_check("install_no_auto_enable_without_credentials", "CONTROL_PLANE_API_KEY" in install_src and "not be enabled" in install_src.lower() or "not started" in install_src.lower() or "deferred" in install_src.lower()))
    checks.append(_check("install_localhost_mcp_target", LOCALHOST_MCP in install_src or "127.0.0.1:8765" in install_src))

    checks.append(_check("runbook_exists", RUNBOOK.is_file()))
    checks.append(_check("chatgpt_runbook_exists", CHATGPT_RUNBOOK.is_file()))
    checks.append(_check("readiness_report_exists", REPORT.is_file()))
    checks.append(_check("rollback_documented", "systemctl disable --now worldcup-mcp-tunnel" in RUNBOOK.read_text(encoding="utf-8") if RUNBOOK.is_file() else False))
    checks.append(_check("chatgpt_workspace_gate_documented", "CHATGPT" in CHATGPT_RUNBOOK.read_text(encoding="utf-8") if CHATGPT_RUNBOOK.is_file() else False))

    checks.append(_check("no_public_mcp_proxy_in_repo", "0.0.0.0:8765" not in mcp_unit))
    checks.append(_check("no_model_changes_in_tunnel_files", "predict_pipeline" not in tunnel_unit and "ecse_live" not in tunnel_unit))

    protected = (
        "worldcup_predictor/orchestration/predict_pipeline.py",
        "worldcup_predictor/research/ecse_live/prediction_builder.py",
        "worldcup_predictor/odds/freshness_policy.py",
    )
    try:
        changed = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        changed = ""
    touched = [p for p in protected if p in changed]
    checks.append(_check("no_wde_ecse_formula_changes", len(touched) == 0, ", ".join(touched)))

    server_src = (MCP_ROOT / "server.py").read_text(encoding="utf-8")
    checks.append(_check("no_shell_tool", 'name="shell"' not in server_src))
    checks.append(_check("no_sql_tool", "query_database" not in server_src))

    all_passed = all(c["passed"] for c in checks)
    payload = {"phase": PHASE, "all_passed": all_passed, "checks": checks}
    print(json.dumps(payload, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
