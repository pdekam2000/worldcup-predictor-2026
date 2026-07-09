# Phase 4 — GPT Actions Bridge Production Web Audit

**Date:** 2026-07-09  
**Mode:** Read-only audit (no production changes)  
**Host:** Hetzner `91.107.188.229` — `/opt/worldcup-predictor`

## Executive summary

Production is ready for a **narrow HTTPS route** to a new localhost-only GPT Actions bridge. MCP remains correctly bound to `127.0.0.1:8765` with no public proxy. A dedicated prefix `https://footballpredictor.it.com/api/gpt-actions/v1/` can be added without affecting the SPA frontend or existing `worldcup-api` `/api/` traffic.

## Production domain

| Item | Value |
|------|-------|
| Primary domain | `footballpredictor.it.com` |
| HTTP | Port 80 — Certbot redirect to HTTPS |
| HTTPS | Port 443 — TLS 1.2+ (Let's Encrypt) |
| Certificate | `/etc/letsencrypt/live/footballpredictor.it.com/fullchain.pem` |
| Certificate key | `/etc/letsencrypt/live/footballpredictor.it.com/privkey.pem` |

Certbot-managed SSL includes `options-ssl-nginx.conf` and modern protocol restrictions (`TLSv1.2 TLSv1.3` in global nginx.conf).

## HTTPS listeners

- `listen 443 ssl` (IPv4)
- `listen [::]:443 ssl ipv6only=on` (IPv6)
- No public listener on MCP port 8765
- No listener on GPT Actions port 8770 (not deployed yet)

## Current upstream routing

| Public path | Upstream | Service |
|-------------|----------|---------|
| `/api/` | `http://127.0.0.1:8000/api/` | `worldcup-api` (uvicorn) |
| `/` (SPA) | `/var/www/worldcup/frontend/dist` | Static React frontend |
| `/api/gpt-actions/v1/` | **Not configured** | Planned: `127.0.0.1:8770` |

## Service bind audit

| Service | Bind | Status |
|---------|------|--------|
| `worldcup-api` | `127.0.0.1:8000` | active |
| `worldcup-mcp` | `127.0.0.1:8765` | active |
| `worldcup-gpt-actions` | `127.0.0.1:8770` | **not installed** |
| `worldcup-mcp-tunnel` | n/a | inactive (by design) |

## Auth boundaries today

- **Frontend:** Public static assets; owner UI uses existing API auth/session as implemented in `worldcup-api`.
- **API (`/api/`):** Existing FastAPI auth/session boundaries unchanged.
- **MCP (`8765`):** Localhost-only; no Nginx route; not reachable from the public internet.
- **GPT Actions (planned):** Owner-only Bearer API key via `Authorization` header; secrets in `/etc/worldcup-gpt-actions/environment` (outside Git).

## Safe dedicated route assessment

**YES** — a narrowly scoped route is safe to add:

1. Exact prefix match `/api/gpt-actions/v1/` before or as a more-specific location than `/api/`.
2. Proxy only to `127.0.0.1:8770` (dedicated bridge, not MCP).
3. Short proxy timeouts (30s) compatible with job create/poll — not long-running predictions.
4. Request size limit (64k) under GPT Action payload constraints.
5. Rate limiting via `limit_req_zone`.
6. Explicit deny for `/mcp` if ever attempted.

## MCP public exposure

| Check | Result |
|-------|--------|
| Public Nginx MCP route | **NO** |
| Port 8765 public bind | **NO** |
| Tunnel service active | **NO** |

## Risks noted (pre-deploy)

- Broad `/api/` wildcard currently catches all `/api/*` to port 8000 — GPT Actions location must be **more specific** and placed appropriately in the server block.
- FastAPI docs on bridge service disabled in code (`docs_url=None`, `openapi_url=None`).
- API key must be provisioned on server before Custom GPT connection.

## Audit conclusion

| Question | Answer |
|----------|--------|
| Valid public TLS certificate? | YES |
| HTTPS 443 ready? | YES |
| Safe route available? | YES |
| MCP remains private? | YES |
| Ready for Phase 4 code deploy (not activated)? | YES |

**PRODUCTION_MODIFIED_DURING_AUDIT = NO**
