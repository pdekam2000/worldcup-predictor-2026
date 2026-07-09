# ChatGPT MCP Prediction Connection (preparation only)

**Status:** preparation document — do not expose a public MCP endpoint without explicit owner approval.

## Target architecture

```
ChatGPT (Custom MCP App)
    ↓
Secure MCP Tunnel (outbound from Hetzner)
    ↓
localhost MCP server (127.0.0.1)
    ↓
canonical WDE + ECSE pipeline
```

## Requirements

| Item | Value |
|------|--------|
| MCP bind | `127.0.0.1` only |
| Transport | `streamable-http` or `sse` behind tunnel |
| Auth | `MCP_AUTH_TOKEN` (Bearer), set only in server env |
| Firewall | no new inbound public port |
| Tunnel | outbound client on Hetzner (e.g. Secure MCP Tunnel / Cloudflare Tunnel) |

## Environment variables (server)

- `MCP_TRANSPORT=streamable-http`
- `MCP_HOST=127.0.0.1`
- `MCP_PORT=8765`
- `MCP_AUTH_TOKEN` — long random secret (not in git)
- `MCP_AUDIT_LOG_PATH=/var/log/worldcup-mcp/audit.jsonl`
- `MCP_CALLER_MODE=chatgpt_tunnel`

## Validation checklist (when approved)

1. Tunnel connects to `127.0.0.1:8765/mcp`
2. Unauthorized requests rejected (no token)
3. `server_health` and `model_status` succeed
4. `resolve_fixtures` + `run_batch_predictions` (max 3) parity with canonical pipeline
5. Audit log receives JSONL entries without secrets

## Rollback / disable

```bash
systemctl disable --now worldcup-mcp.service
# remove tunnel unit
# revoke MCP_AUTH_TOKEN in .env.production
```

## Plan capability note

Custom MCP Apps in ChatGPT require a plan that supports connector/MCP actions. If your account cannot add custom MCP servers:

**CHATGPT_CONNECTION_BLOCKED_BY_PLAN**

MCP server and Cursor SSH stdio can still be **MCP_SERVER_READY** and **CURSOR_MCP_READY** without ChatGPT connectivity.

## Current connection status

- **MCP_SERVER_READY:** after Phase 3 install + validator pass
- **CURSOR_MCP_READY:** after Cursor stdio smoke tests
- **CHATGPT_ACTUAL_CONNECTION:** not configured (stopped before public exposure per Phase 3.8)
