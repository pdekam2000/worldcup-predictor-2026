# OpenAI Secure MCP Tunnel Runbook (WorldCup Predictor)

**Status:** PREPARATION ONLY — do not enable tunnel until owner supplies Platform credentials and approves ChatGPT workspace gates.

**Official documentation (authoritative):**

- Secure MCP Tunnel guide: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- `tunnel-client` repository: https://github.com/openai/tunnel-client
- Onboarding: https://github.com/openai/tunnel-client/blob/master/docs/onboarding.md
- Platform Tunnels UI: https://platform.openai.com/settings/organization/tunnels
- Runtime API keys: https://platform.openai.com/settings/organization/api-keys
- Admin API keys: https://platform.openai.com/settings/organization/admin-keys

**Documented release reference:** `tunnel-client` **v0.0.10** (2026-07-02) — use latest release from Platform download or GitHub `releases/latest` (do not hard-code stale URLs).

---

## Architecture

```
ChatGPT / Responses API / Codex
        ↓ HTTPS (OpenAI-managed)
OpenAI tunnel control plane (api.openai.com:443 /v1/tunnels/*)
        ↓ outbound long-poll only
tunnel-client (worldcup-mcp-tunnel user on Hetzner)
        ↓ localhost HTTP
http://127.0.0.1:8765/mcp  (worldcup-mcp streamable-http)
        ↓
canonical WDE + ECSE (unchanged)
```

**No inbound firewall port. No public MCP listener. No nginx proxy. No ngrok.**

---

## Prerequisites

| Requirement | Source |
|-------------|--------|
| Production MCP on `127.0.0.1:8765` | `worldcup-mcp.service` |
| `worldcup-mcp` active | `systemctl is-active worldcup-mcp` |
| Outbound HTTPS to OpenAI | `curl -sS -o /dev/null -w '%{http_code}' https://api.openai.com` (401 without key is OK) |
| `CONTROL_PLANE_TUNNEL_ID` | Platform → Tunnels (`tunnel_` + 32 hex) |
| `CONTROL_PLANE_API_KEY` | Platform → Runtime API keys (Tunnels Read + Use) |
| `OPENAI_ADMIN_KEY` | Only for `tunnel-client admin tunnels *` (optional) |
| ChatGPT app / connector setup | https://chatgpt.com/#settings/Connectors |

---

## Service identity (least privilege)

| User | Purpose | Must NOT have |
|------|---------|---------------|
| `worldcup-mcp-tunnel` | Runs `tunnel-client` | sudo, DB write, repo write, provider API keys, SSH keys |

**Permissions:**

- Read `/etc/worldcup-mcp-tunnel/environment` (group `worldcup-mcp-tunnel`, mode `0640`)
- Write `/var/lib/worldcup-mcp-tunnel` (profiles, state)
- Outbound HTTPS (`api.openai.com:443`)
- Local TCP to `127.0.0.1:8765` only

**Does NOT read** `/opt/worldcup-predictor/.env.production` (provider secrets isolated).

---

## Secret storage

Path: `/etc/worldcup-mcp-tunnel/environment`

| Field | Owner | Group | Mode |
|-------|-------|-------|------|
| `/etc/worldcup-mcp-tunnel/` | root | worldcup-mcp-tunnel | 0750 |
| `environment` | root | worldcup-mcp-tunnel | 0640 |
| `environment.example` | root | worldcup-mcp-tunnel | 0640 |

Template installed by `scripts/install_worldcup_mcp_tunnel.sh`. **Never commit real values.**

If `worldcup-mcp` requires `MCP_AUTH_TOKEN` for streamable-http, set only the Bearer value needed for localhost tunnel→MCP calls in the tunnel environment file (not in git, not in `ExecStart`).

---

## Installation (prepare only)

On Hetzner as root:

```bash
cd /opt/worldcup-predictor
git pull --ff-only origin main   # after Phase 3.3 merge
bash scripts/install_worldcup_mcp_tunnel.sh
```

The installer:

1. Detects `linux-amd64` or `linux-arm64`
2. Downloads latest official `tunnel-client` release + verifies `SHA256SUMS.txt`
3. Installs to `/usr/local/bin/tunnel-client`
4. Creates `worldcup-mcp-tunnel` user
5. Installs systemd unit (disabled until credentials present)
6. Runs `tunnel-client init` + `doctor` **only when** `/etc/worldcup-mcp-tunnel/environment` has credentials

**Does not:** open firewall, modify nginx, change MCP bind, auto-start without credentials.

---

## Official CLI workflow (current)

```bash
# Shortest path reference
tunnel-client help quickstart

# Profile init (remote HTTP MCP — our case)
tunnel-client init \
  --sample sample_mcp_remote_no_auth \
  --profile worldcup-predictor \
  --tunnel-id "${CONTROL_PLANE_TUNNEL_ID}" \
  --mcp-server-url http://127.0.0.1:8765/mcp

# Verify before run
tunnel-client doctor --profile worldcup-predictor --explain

# Foreground daemon (operator test)
tunnel-client run --profile worldcup-predictor --log.level=info --log.format=struct-text

# Health (tunnel-client local, default 127.0.0.1:8081 if configured)
curl -fsS http://127.0.0.1:8081/healthz
curl -fsS http://127.0.0.1:8081/readyz
```

**Supported OS (official releases):** Linux (`amd64`, `arm64`), macOS (`amd64`, `arm64`). Hetzner production: **Linux amd64**.

---

## Systemd operation (after owner approval)

```bash
# Only after environment file populated and doctor passes
systemctl enable --now worldcup-mcp-tunnel.service
systemctl status worldcup-mcp-tunnel
journalctl -u worldcup-mcp-tunnel -n 50 --no-pager
```

Verify `worldcup-mcp` still on `127.0.0.1:8765` only:

```bash
ss -ltnp | grep 8765
```

---

## Rollback (exact)

```bash
systemctl disable --now worldcup-mcp-tunnel
```

Verify core services unchanged:

```bash
systemctl is-active worldcup-api    # must stay active
systemctl is-active worldcup-mcp    # must stay active
ss -ltnp | grep 8765               # must stay 127.0.0.1 only
```

Optional: revoke `CONTROL_PLANE_API_KEY` in Platform, remove ChatGPT connector, rotate `MCP_AUTH_TOKEN` on `worldcup-mcp` if used.

**Do not:** delete DB, rollback predictions, or stop `worldcup-api` unless separately required.

---

## Audit verification (post-connect)

Confirm `/var/log/worldcup-mcp/audit.jsonl` records tunnel calls with `caller_mode=openai_tunnel` (once `MCP_CALLER_MODE` configured for tunnel path). No secrets in audit tail.

---

## Do not use

- ngrok / Cloudflare Tunnel / ad-hoc public reverse proxy for production MCP
- Binding `worldcup-mcp` to `0.0.0.0`
- Inbound firewall rule on 8765
- Embedding API keys in systemd `ExecStart` or git
