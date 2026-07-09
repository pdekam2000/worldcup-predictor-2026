# Cursor MCP — WorldCup Predictor (SSH stdio)

Connect Cursor to the production MCP server over your existing SSH session. Authentication is inherited from SSH; no API keys belong in this file.

## Prerequisites

- SSH host alias configured (example: `worldcup-prod`)
- Phase 3 MCP code deployed to `/opt/worldcup-predictor`
- `mcp>=1.27,<2` installed in production venv
- `.env.production` present on server (not committed)

## Cursor MCP configuration

Add to Cursor **Settings → MCP** (or `.cursor/mcp.json` in your user config):

```json
{
  "mcpServers": {
    "worldcup-predictor": {
      "command": "ssh",
      "args": [
        "-T",
        "worldcup-prod",
        "cd /opt/worldcup-predictor && set -a && source .env.production && set +a && PYTHONPATH=/opt/worldcup-predictor /opt/worldcup-predictor/.venv/bin/python -m worldcup_predictor.mcp_server.server --stdio"
      ]
    }
  }
}
```

Replace `worldcup-prod` with your SSH host alias.

## Smoke test order

1. `server_health`
2. `model_status`
3. `resolve_fixtures` with one known match (`home_team`, `away_team`, `date`)
4. `odds_freshness_audit` for resolved `fixture_id`
5. `run_fixture_prediction` for one safe fixture (single fixture only initially)

## Notes

- Default transport is **stdio**; the MCP process does not bind a public port.
- Remote SSE/HTTP requires `MCP_HOST=127.0.0.1` and a secure tunnel (see `CHATGPT_MCP_PREDICTION_CONNECTION.md`).
- Do not embed passwords, private keys, or tokens in MCP config.
