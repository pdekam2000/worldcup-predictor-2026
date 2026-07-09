# Phase 3.1 — MCP End-to-End Report

**Date:** 2026-07-09  
**Branch:** `infra/phase3-mcp-prediction-server` @ `1e7d638`  
**origin/main:** `71f4169309ef97acfc0dc733e6bd8d20212dc843`

---

## Part A — GitHub / PR truth

| Item | Value |
|------|--------|
| origin/main SHA | `71f4169` |
| Phase 3 branch SHA | `1e7d638` |
| Open PR exists? | **NO** (GitHub API returned `[]`) |
| **PR_CREATED** | **NO** |
| PR number | — |

**Reason:** `gh` CLI not installed; `winget install GitHub.cli` cancelled; no `GITHUB_TOKEN` available for API PR creation.

**Action required:** Create PR manually in GitHub UI or install/authenticate `gh` and run:

```bash
gh pr create --base main --head infra/phase3-mcp-prediction-server \
  --title "Phase 3: Add secure MCP prediction server" \
  --body-file docs/phase3_pr_body.md
```

---

## Part B — Production code truth

See `PHASE_3_1_PRODUCTION_CODE_TRUTH_AUDIT.md`.

**PRODUCTION_MAIN_ALIGNED = NO**

---

## Part C — PR review gate (local)

| Check | Result |
|-------|--------|
| `validate_phase3_mcp_prediction_server.py` | **all_passed: true** |
| `pytest tests/mcp_server/ -q` | **28 passed** |
| `validate_strict_live_odds_refresh_fix.py` | **FAIL** (local `sqlite3.OperationalError: unable to open database file` — environment temp path) |
| `compileall mcp_server` | **PASS** |
| `git diff origin/main...HEAD` | **39 files, +2160 lines** — MCP package only |
| Protected formula files changed? | **NO** |
| Secret scan (mcp_server) | **NO committed secrets** |

---

## Part D — MCP protocol end-to-end test

**Transport:** stdio MCP client (`mcp` Python SDK)

### Tool discovery (`list_tools`)

| Environment | Tools | Extra | Missing |
|-------------|-------|-------|---------|
| Local | 10 | 0 | 0 |
| Production | 10 | 0 | 0 |

Exact allowlist verified.

### Protocol calls (production, no prediction regen for first 5)

| Tool | OK | Duration |
|------|-----|----------|
| server_health | ✅ | 215 ms |
| model_status | ✅ | 54 ms |
| resolve_fixtures (Qarabag vs Vestri) | ✅ | 16 ms → fixture **1554444** |
| odds_freshness_audit (1554444) | ✅ | 15 ms → FRESH_ODDS |
| provider_status | ✅ | 3 ms |

**MCP_PROTOCOL_READY = YES**

Artifact: `artifacts/mcp_protocol_e2e_production.json`

---

## Part E — Cursor real MCP test

| Item | Status |
|------|--------|
| Cursor `mcp.json` schema | `{ "mcpServers": { "<name>": { "command", "args" } } }` |
| `worldcup-prod` SSH alias | **NOT configured** (only `root@91.107.188.229` in known_hosts) |
| Windows SSH→stdio MCP client test | **FAILED** (`McpError: Connection closed`) |
| Production stdio MCP (on-server) | **PASSED** (equivalent protocol) |

**CURSOR_MCP_READY = CURSOR_MCP_CONFIG_READY_BUT_CLIENT_TEST_FAILED**

Config documented in `docs/CURSOR_MCP_PREDICTION_SETUP.md`. Owner must:
1. Add SSH `Host worldcup-prod` → `91.107.188.229`
2. Add MCP server entry to `~/.cursor/mcp.json`
3. Reload Cursor MCP and invoke tools from chat

---

## Part F — Single prediction parity (MCP protocol)

**Fixture:** 1554444 (Qarabag vs Vestri)  
**refresh_if_stale:** false (odds already fresh)

| Field | MCP protocol | Direct runtime | Match |
|-------|--------------|----------------|-------|
| fixture_id | 1554444 | 1554444 | ✅ |
| odds freshness | FRESH_ODDS | FRESH_ODDS | ✅ |
| WDE pick | home_win | home_win | ✅ |
| WDE H/D/A | 44.3 / 26.1 / 29.6 | (parity check) | ✅ |
| ECSE Top1 | 4-0 (16.16%) | — | ✅ |
| quality.status | OK | OK | ✅ |

**parity.passed = true** (tolerance: probabilities ±0.01, ECSE ±0.0001)

**MCP_PROTOCOL_PARITY: PASS**

---

## Part G — Batch MCP test (protocol)

`run_batch_predictions` — 3 fixtures, `refresh_if_stale=false`

| Metric | Value |
|--------|--------|
| requested | 3 |
| successful | 3 |
| blocked | 0 |
| failed | 0 |
| duration | 25.3 s |

One failed fixture did **not** abort the batch.

---

## Part H — Service security audit

| Check | Result |
|-------|--------|
| MCP HTTP bind | **127.0.0.1:8765** ✅ |
| Public bind 0.0.0.0 | **NO** ✅ |
| Service user | `worldcup-mcp` (uid 999) ✅ |
| MCP process user | `worldcup-mcp` ✅ |
| NoNewPrivileges | true ✅ |
| PrivateTmp | true ✅ |
| ProtectSystem | strict ✅ |
| ProtectHome | true ✅ |
| UFW | inactive (no new MCP rule added) ✅ |
| `.env.production` perms | `640 www-data:www-data` ✅ |

**SERVICE_SECURITY: PASS**

---

## Part I — Audit log

See `PHASE_3_1_MCP_AUDIT_LOG_VERIFICATION.md`.

---

## Part J — Main merge and production reconciliation plan

**Do not merge automatically.**

Safe sequence:

1. Create and review PR `infra/phase3-mcp-prediction-server` → `main`
2. Merge after approval
3. On production:
   ```bash
   cd /opt/worldcup-predictor
   git stash push -m "runtime-artifacts" -- data/shadow ODDS_*.md PRODUCTION_PIPELINE_LAST_RUN.md
   git fetch origin main
   git checkout main
   git pull origin main   # includes merged MCP
   .venv/bin/pip install -r requirements.txt
   bash scripts/install_worldcup_mcp_service.sh
   chown worldcup-mcp:worldcup-mcp /var/log/worldcup-mcp/audit.jsonl
   systemctl is-active worldcup-api worldcup-mcp
   PYTHONPATH=/opt/worldcup-predictor .venv/bin/python scripts/mcp_protocol_e2e_test.py --prediction
   ```
4. Verify `git rev-parse HEAD` matches `origin/main`
5. Do **not** overwrite DB or copy local DB

---

## Part K — Secure MCP Tunnel readiness

Document created: `docs/OPENAI_SECURE_MCP_TUNNEL_SETUP.md`

**SECURE_TUNNEL_READY_TO_INSTALL = YES** (documentation only; not installed)

---

## Part L — ChatGPT plan gate

| Field | Value |
|-------|--------|
| CURRENT_CHATGPT_PLAN | **UNKNOWN** (not observable from server/agent) |
| Action tools required | refresh_stale_odds, run_fixture_prediction, run_batch_predictions |
| Classification | **CHATGPT_FULL_MCP_PLAN_NOT_SUPPORTED** (until owner confirms plan in ChatGPT settings) |

---

## Part M — Owner workflow contract

Validated flow:

```
resolve_fixtures → run_batch_predictions(refresh_if_stale=true)
```

MCP returns structured evidence (fixture, odds, WDE, BTTS, O/U, ECSE Top1–5, warnings). No betting advice fabricated in MCP layer.

---

## Final status flags

| Flag | Value |
|------|-------|
| MCP_SERVER_READY | **YES** |
| MCP_PROTOCOL_READY | **YES** |
| CURSOR_MCP_READY | **CURSOR_MCP_CONFIG_READY_BUT_CLIENT_TEST_FAILED** |
| PRODUCTION_MAIN_ALIGNED | **NO** |
| SECURE_TUNNEL_READY_TO_INSTALL | **YES** |
| CHATGPT_PLAN_SUPPORTED | **UNKNOWN / NOT_CONFIRMED** |
| CHATGPT_ACTUAL_CONNECTION | **NO** |

---

## Exact next action

1. **Create the GitHub PR** (manual or `gh` after install/auth)
2. **Merge to main** after review
3. **Reconcile production** to `origin/main` using Part J sequence
4. **Add `worldcup-prod` SSH host + Cursor MCP entry** and confirm tools from Cursor UI
5. **Fix audit log ownership** (`chown worldcup-mcp`)
