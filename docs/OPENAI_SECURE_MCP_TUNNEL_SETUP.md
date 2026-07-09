# OpenAI Secure MCP Tunnel Setup (preparation only)

**Status:** PREPARED — do not install until owner explicitly approves.

## Architecture

```
ChatGPT (Custom MCP App)
    ↓ HTTPS (OpenAI-managed)
OpenAI Secure MCP Tunnel endpoint
    ↓ outbound tunnel (Hetzner client)
127.0.0.1:8765 (worldcup-mcp streamable-http)
    ↓
canonical WDE + ECSE pipeline
```

## Prerequisites

1. Phase 3 merged to `main` and production aligned to `origin/main`
2. `worldcup-mcp` active on `127.0.0.1:8765` only
3. `MCP_AUTH_TOKEN` set in `/opt/worldcup-predictor/.env.production` (not in git)
4. ChatGPT plan supporting **action-capable** custom MCP apps (see plan gate)
5. OpenAI Secure MCP Tunnel client package from official OpenAI documentation

## Supported account plan

Custom MCP with write/action tools (`refresh_stale_odds`, `run_fixture_prediction`, `run_batch_predictions`) requires a plan that supports connector actions — not read-only MCP.

Classify separately as `CHATGPT_FULL_MCP_PLAN_SUPPORTED` or `CHATGPT_FULL_MCP_PLAN_NOT_SUPPORTED`.

## Tunnel client placement

- Run on Hetzner alongside `worldcup-mcp`
- **Outbound-only** connection to OpenAI
- No inbound public firewall rule for port 8765

## Environment configuration

Add to `.env.production` (server only):

```bash
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8765
MCP_AUTH_TOKEN=<long-random-secret>
MCP_AUDIT_LOG_PATH=/var/log/worldcup-mcp/audit.jsonl
MCP_CALLER_MODE=openai_tunnel
# OPENAI_MCP_TUNNEL_TOKEN=<from OpenAI connector setup>
```

## Proposed systemd unit (tunnel client)

Create `/etc/systemd/system/worldcup-mcp-tunnel.service` when approved:

```ini
[Unit]
Description=OpenAI Secure MCP Tunnel client for WorldCup Predictor
After=network-online.target worldcup-mcp.service
Requires=worldcup-mcp.service

[Service]
Type=simple
User=worldcup-mcp
Group=worldcup-mcp
EnvironmentFile=/opt/worldcup-predictor/.env.production
ExecStart=/opt/worldcup-predictor/.venv/bin/openai-mcp-tunnel-client --target http://127.0.0.1:8765/mcp
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Replace `openai-mcp-tunnel-client` with the exact binary/command from OpenAI's current Secure MCP Tunnel documentation.

## Secret storage strategy

- `MCP_AUTH_TOKEN` and tunnel credentials only in `.env.production` (`chmod 640`, owner `www-data` or `worldcup-mcp`)
- Never commit tokens to git
- Never pass tokens in query strings
- Rotate on tunnel disable

## Localhost target

- **URL:** `http://127.0.0.1:8765/mcp` (streamable-http path from FastMCP)
- Verify with: `ss -ltnp | grep 8765` → must show `127.0.0.1:8765` only

## Health verification (post-install)

1. `systemctl is-active worldcup-mcp`
2. `curl -sS -H "Authorization: Bearer $MCP_AUTH_TOKEN" http://127.0.0.1:8765/mcp` (if supported)
3. MCP `server_health` via tunnel test client
4. Audit log receives entries without secrets

## Audit verification

Confirm `/var/log/worldcup-mcp/audit.jsonl` records tunnel-mode calls with `caller_mode=openai_tunnel`.

## Disable / rollback

```bash
systemctl disable --now worldcup-mcp-tunnel.service
# Revoke MCP_AUTH_TOKEN in .env.production and restart worldcup-mcp
systemctl restart worldcup-mcp
# Remove OpenAI Custom MCP App in ChatGPT settings
```

## Do not use

- ngrok or ad-hoc public reverse proxies for production ChatGPT MCP
- Binding MCP to `0.0.0.0`
- Unauthenticated public port exposure
