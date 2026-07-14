# Phase 2E — Forward Evaluation Systemd Security Audit

**Generated:** 2026-07-14

## Service: `worldcup-forward-evaluation.service`

| Check | Status | Notes |
|-------|--------|-------|
| Binds public ports | **No** | Type=oneshot CLI only |
| Exposes HTTP | **No** | No uvicorn/gunicorn |
| Embeds API keys | **No** | Uses EnvironmentFile only |
| Prints secrets in ExecStart | **No** | Python script only |
| Runtime user | `www-data` | Matches API pattern |
| WorkingDirectory | `/opt/worldcup-predictor` | Required for DB paths |
| EnvironmentFile | `.env.production` | Standard production pattern |
| Writable paths narrowed | **Yes** | `ReadWritePaths=` data, artifacts, reports |
| ProtectSystem | `strict` | Compatible with ReadWritePaths |
| Timeout | 900s | Matches 15-minute cycle bound |
| Bounded arguments | **Yes** | `--fixture-limit 25 --lookback-hours 72` |

## Timer: `worldcup-forward-evaluation.timer`

| Check | Status |
|-------|--------|
| Shipped enabled | **No** — docs require manual approval |
| High-frequency cadence | **No** — 30-minute proposal only |
| RandomizedDelaySec | 120s | Reduces thundering herd |

## CLI security

- Default mode: **dry-run** (no writes)
- Apply requires explicit `--apply`
- Ledger JSON excludes secrets
- Provider errors sanitized via existing client patterns

## Recommendations

1. Do **not** `enable --now` timer until owner approval
2. Keep `fixture_limit` and `lookback_hours` in unit file bounded
3. Ensure `data/evaluation/` owned by `www-data` for ledger writes
