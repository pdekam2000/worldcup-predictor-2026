# Phase 3.3 — Secure MCP Tunnel Readiness Report

**Date (UTC):** 2026-07-09  
**Production HEAD:** `741271ab5c3231be03df82e29e06ee56f7e9166a`  
**GitHub PR:** #5 (squash-merged)  
**Phase 3.3 branch:** `infra/phase3-3-secure-mcp-tunnel-readiness`  
**Stale job 495404:** **IGNORED** (SSH reset during earlier backup; superseded by successful reconciliation)

---

## Part A — Production MCP Health Audit

| Check | Result |
|-------|--------|
| Branch | `main` aligned with `origin/main` |
| HEAD | `741271ab5c3231be03df82e29e06ee56f7e9166a` |
| Tracked source drift | Runtime JSONL/MD only (preserved) |
| `worldcup-api` | **active** |
| `worldcup-mcp` | **active** |
| MCP bind | `127.0.0.1:8765` only |
| Public `0.0.0.0:8765` | **NOT present** |

---

## Part B — Pre-Tunnel MCP Owner Workflow

Executed via live Cursor MCP client (`user-worldcup-predictor`).

| Step | Result |
|------|--------|
| `server_health` | PASS — SHA `741271a`, `git_sha_source=git_head` |
| `model_status` | PASS |
| `provider_status` | PASS |
| `resolve_fixtures` (Qarabag FK vs IF Vestri, 2026-07-09) | PASS → `1554444` |
| `run_fixture_prediction` (1554444, `refresh_if_stale=false`) | PASS — full WDE/ECSE/quality |
| `run_batch_predictions` [1554444, 1554441, 1554406] | **3/3 PASS** |

All required evidence fields present per fixture.

**`PRE_TUNNEL_MCP_PARITY` = PASS**

---

## Part C — Official OpenAI Secure MCP Tunnel Audit

**Authoritative sources (2026-07-09):**

| Topic | Official reference |
|-------|-------------------|
| Guide | https://developers.openai.com/api/docs/guides/secure-mcp-tunnels |
| Client repo | https://github.com/openai/tunnel-client |
| Onboarding | `tunnel-client` docs/onboarding.md |
| Latest release | **v0.0.10** (2026-07-02) — use `releases/latest` |
| Platform Tunnels | https://platform.openai.com/settings/organization/tunnels |
| Runtime API keys | https://platform.openai.com/settings/organization/api-keys |
| Admin API keys | https://platform.openai.com/settings/organization/admin-keys |
| ChatGPT Connectors | https://chatgpt.com/#settings/Connectors |

| Requirement | Official answer |
|-------------|-----------------|
| Installation | Download from Platform Tunnels page or GitHub release zip; `SHA256SUMS.txt` verification |
| Supported OS | Linux, macOS (release zips per arch) |
| Supported arch | `amd64`, `arm64` |
| Tunnel creation | Platform UI or `tunnel-client admin tunnels create` (admin key) |
| Tunnel ID format | `tunnel_` + 32 lowercase hex |
| Runtime key | `CONTROL_PLANE_API_KEY` — Tunnels Read + Use |
| Admin key | `OPENAI_ADMIN_KEY` — tunnel CRUD only |
| Profile init | `tunnel-client init --sample sample_mcp_remote_no_auth --profile <name> --tunnel-id <id> --mcp-server-url <url>` |
| Doctor | `tunnel-client doctor --profile <name> --explain` |
| Run (foreground) | `tunnel-client run --profile <name> --log.level=info --log.format=struct-text` |
| Health | `curl http://127.0.0.1:8081/healthz` / `readyz` (configurable) |
| Outbound only | `api.openai.com:443` `/v1/tunnels/*` — no inbound MCP port |
| MCP binding | `MCP_SERVER_URL` (HTTP) or `--mcp-command` (stdio) |
| ChatGPT | Custom connector with Tunnel transport; Developer Mode; per-conversation enable |

---

## Part D — Hetzner Network Readiness

| Test | Result |
|------|--------|
| Outbound HTTPS (api.openai.com) | **PASS** (HTTP 401 without key — connectivity OK) |
| DNS resolution | **PASS** |
| Local MCP endpoint | **REACHABLE** (HTTP 406 without MCP session — expected) |
| Inbound MCP firewall | **NONE** (UFW inactive; no 8765 public rule) |
| nginx MCP route | **NONE** |

**`HETZNER_TUNNEL_NETWORK_READY` = YES**

---

## Part E — Tunnel Service User

| Field | Value |
|-------|-------|
| User | `worldcup-mcp-tunnel` |
| Group | `worldcup-mcp-tunnel` |
| Home | `/var/lib/worldcup-mcp-tunnel` |
| Shell | `/usr/sbin/nologin` |

**Denied:** sudo, DB write, repo write, `.env.production`, SSH keys, provider tokens.

**Allowed:** outbound HTTPS, localhost `127.0.0.1:8765`, tunnel config in `/etc/worldcup-mcp-tunnel/`.

---

## Part F — Secret Storage Design

| Path | Owner | Group | Mode |
|------|-------|-------|------|
| `/etc/worldcup-mcp-tunnel/` | root | worldcup-mcp-tunnel | 0750 |
| `environment` | root | worldcup-mcp-tunnel | 0640 |
| `environment.example` | root | worldcup-mcp-tunnel | 0640 |

No secrets in git, reports, systemd `ExecStart`, or Cursor config.

---

## Part G–H — Install Script + Systemd

| Artifact | Path |
|----------|------|
| Installer | `scripts/install_worldcup_mcp_tunnel.sh` |
| Systemd unit | `deployment/systemd/worldcup-mcp-tunnel.service` |
| Validator | `scripts/validate_phase3_3_secure_mcp_tunnel_readiness.py` |

Installer: official GitHub release + SHA256 verify, architecture detection, idempotent, **no auto-start without credentials**.

Systemd: non-root, `NoNewPrivileges`, `ProtectSystem=strict`, env file outside repo, fixed profile `worldcup-predictor`, target `http://127.0.0.1:8765/mcp`.

---

## Part I — Rollback Plan

```bash
systemctl stop worldcup-mcp-tunnel
systemctl disable worldcup-mcp-tunnel
```

`worldcup-api` and `worldcup-mcp` remain active; MCP stays localhost-only. No DB/prediction changes.

---

## Part J — ChatGPT Capability Gate

| Gate | Value |
|------|-------|
| `CURRENT_CHATGPT_PLAN` | **UNKNOWN** (owner account not audited) |
| `CHATGPT_CUSTOM_MCP_SUPPORTED` | **YES** |
| `CHATGPT_REQUIRED_ACTION_TOOLS_SUPPORTED` | **CONDITIONAL** (workspace write-action permission required) |
| `CHATGPT_WORKSPACE_REQUIREMENT_MET` | **UNKNOWN** |
| `CHATGPT_CONNECTION_BLOCKED_BY_ACCOUNT_OR_WORKSPACE` | **POSSIBLE** — verify Business workspace write-action toggles |

---

## Part K — Owner Use Case

Documented in `docs/CHATGPT_WORLDCUP_MCP_CONNECTION_RUNBOOK.md`.

Flow: `resolve_fixtures` → `odds_freshness_audit` → `refresh_stale_odds` (if needed) → `run_batch_predictions`.

---

## Part L — Tool Security Review

Exact 10-tool allowlist unchanged. No shell/SQL/file/git/systemd tools. Tunnel exposes same MCP server — no extra tools.

---

## Part M — Validator

`scripts/validate_phase3_3_secure_mcp_tunnel_readiness.py` — run on branch; all checks **PASS**.

---

## Documentation

| Doc | Path |
|-----|------|
| Tunnel runbook | `docs/OPENAI_SECURE_MCP_TUNNEL_RUNBOOK.md` |
| ChatGPT runbook | `docs/CHATGPT_WORLDCUP_MCP_CONNECTION_RUNBOOK.md` |
| Legacy prep doc | `docs/OPENAI_SECURE_MCP_TUNNEL_SETUP.md` (superseded by runbook for ops) |

---

## Final Statuses

| Status | Value |
|--------|-------|
| `PHASE_3_3_TUNNEL_READINESS` | **YES** |
| `HETZNER_TUNNEL_NETWORK_READY` | **YES** |
| `TUNNEL_CLIENT_INSTALL_READY` | **YES** (script + unit prepared; not executed on production) |
| `TUNNEL_CREDENTIALS_AVAILABLE` | **NO** |
| `TUNNEL_ACTUALLY_CONNECTED` | **NO** |
| `CHATGPT_ACCOUNT_WORKSPACE_READY` | **NO** (owner verification required) |
| `CHATGPT_ACTUAL_CONNECTION` | **NO** |
| `MCP_SERVER_READY` | **YES** |
| `CURSOR_MCP_READY` | **YES** |
| `CURSOR_OWNER_FLOW_TEST` | **PASS** |
| `PRODUCTION_MAIN_ALIGNED` | **YES** |
| `PRE_TUNNEL_MCP_PARITY` | **PASS** |

---

**Stopped after preparation, validation, report, and PR. No public port opened. No tunnel activated. No prediction logic changed.**
