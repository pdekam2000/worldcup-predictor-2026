## Summary

- Adds a secure MCP prediction server with a **10-tool allowlist** and deny-by-default architecture (no shell, SQL, or arbitrary file access).
- Delegates to **canonical** paths: WDE (`run_daily_wde` / `PredictPipeline`), ECSE (`run_daily_ecse`), odds freshness (`build_fixture_freshness_metadata`), strict live refresh (`refresh_fixture_odds_live`).
- Supports **stdio** transport (Cursor over SSH) and **localhost-only HTTP** (`127.0.0.1:8765`) for future Secure MCP Tunnel.
- Includes JSONL **audit logging** with secret redaction, `worldcup-mcp` systemd unit, validators, and 28 security tests.
- **Parity verified** on production fixture 1554444 via MCP protocol (MCP output = direct runtime).
- **No model formula changes**, no DB schema changes, no public port exposure.

## Test plan

- [x] `python scripts/validate_phase3_mcp_prediction_server.py`
- [x] `pytest tests/mcp_server/`
- [x] Production MCP protocol e2e (`scripts/mcp_protocol_e2e_test.py`)
- [ ] Merge + production reconciliation to `origin/main`
- [ ] Cursor MCP client test from IDE after SSH host configured
