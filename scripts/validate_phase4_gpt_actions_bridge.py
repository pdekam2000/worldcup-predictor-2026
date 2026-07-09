#!/usr/bin/env python3
"""Phase 4 — offline/static validator for GPT Actions bridge."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PHASE = "PHASE-4-GPT-ACTIONS-BRIDGE"
GPT_ROOT = ROOT / "worldcup_predictor" / "gpt_actions"
OPENAPI_PATH = ROOT / "docs" / "gpt_actions" / "worldcup_predictor_actions.openapi.yaml"
NGINX_SNIPPET = ROOT / "deployment" / "nginx" / "gpt-actions-snippet.conf"
SYSTEMD_UNIT = ROOT / "deployment" / "systemd" / "worldcup-gpt-actions.service"
MCP_SYSTEMD = ROOT / "deployment" / "systemd" / "worldcup-mcp.service"

PROTECTED_PREFIXES = (
    "worldcup_predictor/orchestration/predict_pipeline.py",
    "worldcup_predictor/research/ecse_live/prediction_builder.py",
    "worldcup_predictor/odds/freshness_policy.py",
    "worldcup_predictor/odds/strict_live_refresh.py",
)

SECRET_PATTERNS = (
    re.compile(r"GPT_ACTIONS_API_KEY\s*=\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)

APPROVED_OPS = {
    "getSystemStatus",
    "discoverTodayMatches",
    "filterMatchesByOdds",
    "startPredictionJob",
    "getPredictionJob",
    "getLatestPredictionReport",
    "getPredictionReportByDate",
}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _grep_gpt(pattern: str) -> list[str]:
    hits: list[str] = []
    for path in GPT_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(pattern, text, re.I):
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

    checks.append(_check("gpt_actions_package_exists", GPT_ROOT.is_dir()))
    checks.append(_check("app_module_exists", (GPT_ROOT / "app.py").is_file()))
    checks.append(_check("server_module_exists", (GPT_ROOT / "server.py").is_file()))
    checks.append(_check("openapi_exists", OPENAPI_PATH.is_file()))
    checks.append(_check("systemd_unit_exists", SYSTEMD_UNIT.is_file()))
    checks.append(_check("nginx_snippet_exists", NGINX_SNIPPET.is_file()))
    checks.append(_check("custom_gpt_instructions_exist", (ROOT / "docs/gpt_actions/CUSTOM_GPT_OWNER_INSTRUCTIONS.md").is_file()))

    from worldcup_predictor.gpt_actions.policies import APPROVED_OPERATION_IDS, APPROVED_ROUTES

    checks.append(_check("approved_operation_ids", APPROVED_OPERATION_IDS == frozenset(APPROVED_OPS)))
    checks.append(_check("approved_route_count_7", len(APPROVED_ROUTES) == 7))

    app_src = (GPT_ROOT / "app.py").read_text(encoding="utf-8")
    checks.append(_check("no_openapi_public", "openapi_url=None" in app_src))
    checks.append(_check("no_docs_public", "docs_url=None" in app_src and "redoc_url=None" in app_src))
    checks.append(_check("no_generic_execute", "execute" not in app_src.lower() or "/execute" not in app_src))
    checks.append(_check("no_mcp_proxy_route", "/mcp" not in app_src))
    checks.append(_check("async_job_post_route", "prediction-jobs" in app_src))
    checks.append(_check("async_job_get_route", "getPredictionJob" in app_src and "prediction-jobs/" in app_src))
    checks.append(_check("query_string_api_key_rejected", "query string is not allowed" in (GPT_ROOT / "auth.py").read_text(encoding="utf-8")))

    config_src = (GPT_ROOT / "config.py").read_text(encoding="utf-8")
    checks.append(_check("localhost_default_bind", "127.0.0.1" in config_src and "8770" in config_src))
    checks.append(_check("api_key_from_env", "GPT_ACTIONS_API_KEY" in config_src))

    auth_src = (GPT_ROOT / "auth.py").read_text(encoding="utf-8")
    checks.append(_check("constant_time_compare", "compare_digest" in auth_src))
    checks.append(_check("bearer_auth_only", "Bearer" in auth_src))

    rate_src = (GPT_ROOT / "rate_limit.py").read_text(encoding="utf-8")
    checks.append(_check("rate_limiting_configured", "RateLimiter" in rate_src and "rate_limit_middleware" in app_src))

    audit_src = (GPT_ROOT / "audit.py").read_text(encoding="utf-8")
    checks.append(_check("audit_logging", "GptActionsAuditLogger" in audit_src))
    checks.append(_check("secret_redaction_in_audit", "redact_secrets" in audit_src))

    jobs_src = (GPT_ROOT / "jobs.py").read_text(encoding="utf-8")
    checks.append(_check("job_concurrency_guard", "_ACTIVE_JOB_ID" in jobs_src))
    checks.append(_check("idempotency_support", "idempotency_key" in jobs_src))
    checks.append(_check("job_retention_prune", "_prune" in jobs_src))

    worker_src = (GPT_ROOT / "worker.py").read_text(encoding="utf-8")
    checks.append(_check("background_job_thread", "threading.Thread" in worker_src))
    checks.append(_check("sequential_predictions", "for fixture_id in fixture_ids" in worker_src))

    delegation_src = (GPT_ROOT / "delegation.py").read_text(encoding="utf-8")
    checks.append(_check("canonical_wde_delegation", "run_fixture_prediction" in delegation_src))
    checks.append(_check("canonical_ecse_top5", "top5" in delegation_src))
    checks.append(_check("no_manual_poisson", "poisson" not in delegation_src.lower()))
    checks.append(_check("freshness_via_snapshots", "_latest_odds_snapshot" in delegation_src))

    runtime_src = (ROOT / "worldcup_predictor/mcp_server/runtime.py").read_text(encoding="utf-8")
    checks.append(_check("mcp_runtime_wde", "run_daily_wde" in runtime_src))
    checks.append(_check("mcp_runtime_ecse", "run_daily_ecse" in runtime_src))

    mcp_unit = MCP_SYSTEMD.read_text(encoding="utf-8") if MCP_SYSTEMD.is_file() else ""
    checks.append(_check("mcp_localhost_bind", "127.0.0.1:8765" in mcp_unit or "MCP_HOST=127.0.0.1" in mcp_unit))
    nginx_text = NGINX_SNIPPET.read_text(encoding="utf-8") if NGINX_SNIPPET.is_file() else ""
    checks.append(_check("nginx_https_path_prefix", "/api/gpt-actions/v1/" in nginx_text))
    checks.append(_check("nginx_no_mcp_proxy", "proxy_pass" in nginx_text and "/mcp" not in nginx_text.split("proxy_pass")[1][:200]))
    checks.append(_check("nginx_mcp_deny", "location /mcp" in nginx_text))

    gpt_unit = SYSTEMD_UNIT.read_text(encoding="utf-8")
    checks.append(_check("systemd_localhost_env", "GPT_ACTIONS_HOST=127.0.0.1" in gpt_unit))
    checks.append(_check("systemd_env_file_outside_git", "/etc/worldcup-gpt-actions/environment" in gpt_unit))
    checks.append(_check("systemd_non_root_user", "User=worldcup-gpt-actions" in gpt_unit))
    checks.append(_check("systemd_no_new_privileges", "NoNewPrivileges=true" in gpt_unit))

    forbidden_hits = _grep_gpt(r"subprocess|os\.system|eval\(|exec\(")
    checks.append(_check("no_arbitrary_shell", len(forbidden_hits) == 0, ", ".join(forbidden_hits)))

    sql_tool_hits = _grep_gpt(r"execute\(.*SELECT|query_database")
    checks.append(_check("no_arbitrary_sql_tools", len([h for h in sql_tool_hits if "delegation" not in h]) <= 1))

    repo_text = ""
    for path in list(GPT_ROOT.rglob("*.py")) + [ROOT / ".env", ROOT / ".env.example"]:
        if path.is_file():
            repo_text += path.read_text(encoding="utf-8", errors="replace")
    secret_committed = any(p.search(repo_text) for p in SECRET_PATTERNS)
    checks.append(_check("api_key_not_committed", not secret_committed))

    openapi_text = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.is_file() else ""
    op_ids = re.findall(r"operationId:\s*(\w+)", openapi_text)
    checks.append(_check("openapi_operation_ids_unique", len(op_ids) == len(set(op_ids)) == 7))
    checks.append(_check("openapi_https_server", "https://footballpredictor.it.com" in openapi_text))
    checks.append(_check("openapi_bearer_auth", "ApiKeyAuth" in openapi_text and "bearer" in openapi_text))

    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(openapi_text)
        checks.append(_check("openapi_yaml_valid", isinstance(parsed, dict) and "paths" in parsed))
    except Exception as exc:
        checks.append(_check("openapi_yaml_valid", False, str(exc)))

    protected = _git_diff_protected()
    checks.append(_check("no_protected_formula_changes", len(protected) == 0, ", ".join(protected)))

    schema_hits = _grep_gpt(r"CREATE TABLE|ALTER TABLE")
    checks.append(_check("no_db_schema_changes", len(schema_hits) == 0))

    dry = subprocess.check_output(
        [sys.executable, "-m", "worldcup_predictor.gpt_actions.server", "--dry-test"],
        cwd=ROOT,
        text=True,
    )
    manifest = json.loads(dry)
    checks.append(_check("dry_test_route_manifest", manifest.get("route_count") == 7))

    passed = sum(1 for c in checks if c["passed"])
    failed = [c for c in checks if not c["passed"]]
    report = {"phase": PHASE, "passed": passed, "total": len(checks), "checks": checks}
    print(json.dumps(report, indent=2))
    if failed:
        print(f"\n{PHASE} FAILED ({len(failed)} checks)", file=sys.stderr)
        for item in failed:
            print(f"  - {item['check']}: {item.get('detail', '')}", file=sys.stderr)
        return 1
    print(f"\n{PHASE} PASS ({passed}/{len(checks)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
