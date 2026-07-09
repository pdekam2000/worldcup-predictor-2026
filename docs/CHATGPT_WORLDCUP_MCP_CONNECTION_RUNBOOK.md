# ChatGPT WorldCup MCP Connection Runbook

**Status:** PREPARATION ONLY — tunnel infrastructure ready; actual ChatGPT connection requires owner Platform + workspace setup.

---

## Intended owner workflow

User prompt example:

> "Predict today's matches with my model"

**Canonical MCP tool chain (action-capable, not disguised as read-only):**

1. `resolve_fixtures` — map team names + date → fixture IDs
2. `odds_freshness_audit` — check staleness
3. `refresh_stale_odds` — **only when** freshness gate requires it
4. `run_batch_predictions` — canonical WDE + ECSE evidence per fixture

**MCP returns model evidence only** (H/D/A, picks, ECSE top scores, warnings). ChatGPT may summarize/rank/explain — it must not fabricate odds or scores.

---

## Connection path

```
ChatGPT (Custom MCP App / Connector)
    ↓ Secure MCP Tunnel (OpenAI-managed)
tunnel-client on Hetzner (outbound only)
    ↓ http://127.0.0.1:8765/mcp
worldcup-mcp (10 approved tools)
```

See: [OPENAI_SECURE_MCP_TUNNEL_RUNBOOK.md](./OPENAI_SECURE_MCP_TUNNEL_RUNBOOK.md)

---

## ChatGPT setup (official, current)

**References:**

- Connect from ChatGPT (Apps SDK): https://developers.openai.com/apps-sdk/deploy/connect-chatgpt
- MCP overview: https://developers.openai.com/api/docs/mcp
- ChatGPT Connectors: https://chatgpt.com/#settings/Connectors

### Steps (owner)

1. Enable **Developer Mode** (user): Settings → Apps → Advanced settings
2. Ensure workspace allows custom MCP / write actions (admin may need to enable for Business/Enterprise)
3. Create tunnel in Platform → Tunnels; obtain `tunnel_id`
4. Create Runtime API key with Tunnels **Read** + **Use**
5. Install and verify `tunnel-client` on Hetzner (runbook)
6. In ChatGPT: Settings → Connectors → Create
   - For private MCP: select **Tunnel** transport (Secure MCP Tunnel), not public URL
7. Enable connector per conversation: **+** → More → enable app

---

## Tool allowlist (exactly 10)

| Tool | Type | Owner use |
|------|------|-----------|
| `server_health` | read | diagnostics |
| `model_status` | read | WDE/ECSE availability |
| `provider_status` | read | provider config state |
| `resolve_fixtures` | read | fixture ID resolution |
| `odds_freshness_audit` | read | staleness gate |
| `refresh_stale_odds` | **action** | refresh when stale |
| `run_fixture_prediction` | **action** | single-fixture evidence |
| `run_batch_predictions` | **action** | batch evidence (max 10) |
| `latest_prediction_report` | read | report access |
| `prediction_report_by_date` | read | report access |

No shell, SQL, file, git, or systemd tools.

---

## Expected evidence per fixture

Every successful prediction response must include:

- Match metadata (teams, competition, kickoff, fixture ID)
- Odds provider + freshness status
- WDE H / D / A probabilities
- WDE pick + confidence
- BTTS + O/U 2.5
- ECSE Top1–Top5 scores + probabilities
- Quality status + warnings

---

## Account / workspace capability gate

| Gate | Assessment |
|------|------------|
| `CHATGPT_CUSTOM_MCP_SUPPORTED` | **YES** — custom MCP connectors documented for ChatGPT with Developer Mode |
| `CHATGPT_REQUIRED_ACTION_TOOLS_SUPPORTED` | **CONDITIONAL** — `refresh_stale_odds`, `run_fixture_prediction`, `run_batch_predictions` are write/action tools; require workspace permission for write actions |
| `CHATGPT_WORKSPACE_REQUIREMENT_MET` | **UNKNOWN** — owner must verify plan (Plus/Pro/Business/Enterprise) and workspace admin settings |

**Known Business workspace caveat (community reports, 2026):** workspace-level Developer Mode / write-action toggles may be restricted compared to documentation. If write tools are blocked before reaching MCP server (no audit log entry), set:

`CHATGPT_CONNECTION_BLOCKED_BY_ACCOUNT_OR_WORKSPACE = YES`

**Do not** create duplicate read-only tool aliases to bypass product restrictions.

---

## Verification checklist (post-connect)

1. `tunnel-client doctor --profile worldcup-predictor --explain` → pass
2. `curl http://127.0.0.1:8081/readyz` → OK (tunnel health)
3. ChatGPT connector lists exactly 10 tools
4. `server_health` via ChatGPT → `current_git_sha` matches production HEAD
5. Controlled `run_batch_predictions` (≤3 fixtures) → full evidence payload
6. Audit log appends without secrets

---

## Current connection status

| Field | Value |
|-------|-------|
| `TUNNEL_ACTUALLY_CONNECTED` | **NO** (credentials not provisioned in this phase) |
| `CHATGPT_ACTUAL_CONNECTION` | **NO** |
| Cursor MCP | **YES** (SSH stdio — separate path, already validated) |

---

## Rollback

Disable tunnel service only. See tunnel runbook. Remove ChatGPT connector in UI. Core prediction stack unaffected.
