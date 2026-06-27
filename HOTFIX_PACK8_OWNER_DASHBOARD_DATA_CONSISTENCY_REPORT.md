# HOTFIX PACK 8 — Owner Dashboard Data Consistency Report

**Date:** 2026-06-26  
**Final status:** `OWNER_DASHBOARD_DATA_FIXED`  
**Validation:** `scripts/validate_hotfix_pack8_owner_dashboard.py` — **28/28 PASS** (local + production)

---

## Root causes

| Part | Issue | Root cause |
|------|-------|------------|
| A | 81 → 8100% | UI always multiplied confidence by 100 even when already stored as 0–100 scale |
| B | `range(NaN%)` | Goal timing artifacts / pick objects rendered without NaN guard |
| C | Model Center zeros | Counted only cert-report nested metrics; ignored shadow JSONL (108 preds) |
| D | False disagreements | String compare `away` vs `away_team` without semantic normalization |
| E | Research Lab JSON | Raw `JSON.stringify` dumps for buckets / timing |
| F | EV UNKNOWN=100% | All 102 rows lack computable EV — `odds_decimal` null → `ev=None` |
| G | Value=0 | Same: **missing odds** after enrichment; not threshold |
| H | Placeholders | Monitoring / Autonomous pages still dumped raw JSON |

---

## Fixes applied

### Part A — Confidence scaling
- New `base44-d/src/lib/formatPercent.js` — scales only when value ≤ 1
- Applied across Owner Betting, Model Center, Performance, Promotion, Elite Shadow Preview

### Part B — Goal Timing NaN
- `format_goal_timing_token()` / `format_first_goal_timing_ui()` in `dashboard_metrics.py`
- Research Lab shows **N/A**, **Pending**, **Unknown** instead of NaN

### Part C — Model Center data sources
- `load_shadow_jsonl_stats()` reads `elite_orchestrator_predictions.jsonl`
- Elite market rows use max(autonomous, shadow JSONL) predictions
- **Data sources** panel: autonomous / shadow / predops / stored counts

### Part D — Shadow vs production comparison
- `elite_shadow_comparison.py` uses `semantic_pick()` 
- Aliases: `home_team`, `away_team` ≡ `home`, `away`
- Validation: **0 alias false disagreements**

### Part E — Research Lab UI cards
- Removed all `JSON.stringify` blocks
- Cards for value, EV, odds buckets, goal timing ranges

### Part F — EV pipeline audit
- `_build_ev_pipeline_audit()` — root cause `missing_odds` when UNKNOWN=100%

### Part G — Betting intelligence audit
- `_build_betting_audit()` — explicit detail when Analyzed=102, Value=0

### Part H — Owner page crawl
- `OwnerMonitoringPage` — structured cards (no JSON dump)
- `OwnerAutonomousPage` — summary grid only (no raw report JSON)

---

## Constraints honored
WDE, EGIE scoring, models, calibration, billing, subscriptions — **unchanged**

---

## Production deploy

```bash
tar czf /tmp/hotfix_pack8_deploy.tar.gz \
  base44-d/src/lib/formatPercent.js \
  base44-d/src/pages/owner/ \
  base44-d/src/pages/EliteShadowPreview.jsx \
  worldcup_predictor/owner/dashboard_metrics.py \
  worldcup_predictor/owner/platform_service.py \
  worldcup_predictor/admin/elite_shadow_comparison.py \
  worldcup_predictor/admin/disagreement_quality_analysis.py \
  worldcup_predictor/research/betting_intelligence.py \
  scripts/validate_hotfix_pack8_owner_dashboard.py

scp /tmp/hotfix_pack8_deploy.tar.gz root@91.107.188.229:/tmp/
ssh root@91.107.188.229 "bash /tmp/_server_unpack_hotfix_pack8.sh"
```

### Production smoke (2026-06-26)
- Validation: **28/28 PASS**
- Shadow JSONL: **108** predictions
- Backup: `/opt/worldcup-predictor/backups/hotfix-pack8-20260626-123217`

---

## Validation checklist

| Check | Status |
|-------|--------|
| Confidence 81 → 81% | PASS |
| Goal timing NaN → N/A/Pending | PASS |
| Model Center shadow JSONL | PASS (108) |
| Semantic disagreement fix | PASS |
| Research Lab cards (no JSON) | PASS |
| EV pipeline audit | PASS |
| Betting audit | PASS |
| Owner pages cleaned | PASS |

**Final status: `OWNER_DASHBOARD_DATA_FIXED`**
