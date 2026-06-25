# PHASE 42B-FIX CONFIG HARDENING — Consistency Guard Thresholds Report

**Date:** 2026-06-21  
**Phase:** 42B-FIX Config Hardening  
**Status:** **IMPLEMENTED & VALIDATED (NOT DEPLOYED)**

---

## Executive summary

All numeric thresholds from the Market Consistency Guard were moved into a dedicated config module. Guard rule behavior is unchanged. Validation passes for both the new config-hardening suite and the original Phase 42B-FIX suite.

**Not deployed** — awaiting approval (can ship together with Phase 42B-FIX guard).

---

## Thresholds moved

| Constant | Default | Used for |
|----------|---------|----------|
| `CONSISTENCY_BTTS_NO_THRESHOLD` | `0.70` | Rule 1 & 5 — BTTS No vs goalscorer / correct score |
| `CONSISTENCY_BTTS_YES_THRESHOLD` | `0.70` | Rule 5 — BTTS Yes vs clean-sheet correct scores |
| `CONSISTENCY_UNDER25_THRESHOLD` | `0.70` | Rule 2 — Under 2.5 vs aggressive goal timing |
| `CONSISTENCY_UNDER15_THRESHOLD` | `0.70` | Reserved (not wired in guard yet; same as pre-hardening) |
| `CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD` | `0.35` | Rules 1 & 6 — low team scoring probability |
| `CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE` | `0.72` | Rules 1 & 6 — minimum confidence when xG unavailable |
| `CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD` | `0.25` | Rule 5 — withhold high-prob clean-sheet scores under BTTS Yes |
| `CONSISTENCY_DRAW_SCORING_SHARE` | `0.45` | Fallback team scoring from 1X2 draw mass |
| `CONSISTENCY_POISSON_LAMBDA_FLOOR` | `0.05` | Poisson xG → scoring probability floor |
| `CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX` | `35` | Rule 2 — early expected minute cutoff |
| `CONSISTENCY_EARLY_MINUTE_BANDS` | `0-15`, `16-30` (+ `_` variants) | Rule 2 — aggressive timing bands |

**Note:** User spec suggested `CONSISTENCY_MIN_GOALSCORER_CONFIDENCE = 0.50`; existing behavior used **0.72** (`CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE`). Preserved at **0.72** to avoid weakening the guard.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/prediction/market_consistency_config.py` | **Added** — centralized thresholds + `get_consistency_thresholds()` |
| `worldcup_predictor/prediction/market_consistency_guard.py` | **Updated** — imports config constants; no inline rule thresholds |
| `scripts/validate_phase42b_consistency_guard_config_hardening.py` | **Added** — 16-check config validation |

**Untouched:** prediction engine, WDE, frontend, `display_helpers.py` wiring, raw audit behavior.

---

## Environment override

**Added** — simple optional overrides via env vars (invalid values fall back to defaults):

| Env var | Maps to |
|---------|---------|
| `WCP_CONSISTENCY_BTTS_NO_THRESHOLD` | `CONSISTENCY_BTTS_NO_THRESHOLD` |
| `WCP_CONSISTENCY_BTTS_YES_THRESHOLD` | `CONSISTENCY_BTTS_YES_THRESHOLD` |
| `WCP_CONSISTENCY_UNDER25_THRESHOLD` | `CONSISTENCY_UNDER25_THRESHOLD` |
| `WCP_CONSISTENCY_UNDER15_THRESHOLD` | `CONSISTENCY_UNDER15_THRESHOLD` |
| `WCP_CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD` | `CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD` |
| `WCP_CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE` | `CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE` |
| `WCP_CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD` | `CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD` |
| `WCP_CONSISTENCY_DRAW_SCORING_SHARE` | `CONSISTENCY_DRAW_SCORING_SHARE` |
| `WCP_CONSISTENCY_POISSON_LAMBDA_FLOOR` | `CONSISTENCY_POISSON_LAMBDA_FLOOR` |
| `WCP_CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX` | `CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX` |

`CONSISTENCY_EARLY_MINUTE_BANDS` remains a fixed frozenset (not env-overridable).

Guard audit now includes active threshold snapshot:

```json
"consistency_guard": {
  "rules_version": "42b-fix-config-v1",
  "thresholds": { "...": "..." }
}
```

---

## Validation results

### Config hardening

```
Phase 42B-FIX config hardening: 16/16 PASS
```

### Original Phase 42B-FIX (regression)

```
Phase 42B-FIX validation: 19/19 PASS
```

Run locally:

```bash
python scripts/validate_phase42b_consistency_guard_config_hardening.py
python scripts/validate_phase42b_global_market_consistency_guard.py
```

---

## Deploy steps (when approved)

Bundle with Phase 42B-FIX guard deploy:

1. `worldcup_predictor/prediction/market_consistency_config.py`
2. `worldcup_predictor/prediction/market_consistency_guard.py`
3. `worldcup_predictor/api/display_helpers.py` (if not already deployed)
4. `scripts/validate_phase42b_*.py` (both validation scripts)
5. Frontend dist (if 42B-FIX UI not yet deployed)

```bash
systemctl restart worldcup-api
sudo -u www-data env PYTHONPATH=/opt/worldcup-predictor APP_ENV=production bash -lc \
  'cd /opt/worldcup-predictor && set -a && source .env.production && set +a && \
   .venv/bin/python scripts/validate_phase42b_consistency_guard_config_hardening.py && \
   .venv/bin/python scripts/validate_phase42b_global_market_consistency_guard.py'
```

Optional production tuning (requires API restart to reload module):

```bash
# Example — stricter BTTS No threshold
WCP_CONSISTENCY_BTTS_NO_THRESHOLD=0.75
```

---

## Rollback plan

1. Restore previous `market_consistency_guard.py` (with inline constants).
2. Remove `market_consistency_config.py` (optional).
3. `systemctl restart worldcup-api`.

No database or cache migration required. Cached predictions unaffected; guard runs at API read time.

---

**STOP — awaiting deploy approval.**
