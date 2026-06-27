# PHASE A17 — AI PORTFOLIO, BANKROLL & COMBO BETTING MANAGER REPORT

**Status:** `AI_BETTING_MANAGER_DEPLOYED_OK`  
**Date:** 2026-06-25  
**Commit:** `d8fd1ab755865076bd8b99c22fab58e2b6e5ebae`  
**Production:** https://footballpredictor.it.com (`91.107.188.229`)

---

## Executive summary

Phase A17 delivers an **AI Betting Assistant** that builds daily betting plans from existing PredOps snapshots, Bet Quality overlay (A16), and read-only archive performance data. It adds singles ranking, combo manager, bankroll stake sizing, three portfolio profiles, and subscription display gating — **without** changing WDE, EGIE, scoring, calibration, prediction generation, or billing.

**Live routes:**
- UI: `/betting-plan`
- API: `/api/betting-plan/today`, `/date`, `/portfolio`, `/combo`

---

## Architecture

```
PredOps snapshots (latest per fixture)
        ↓
Bet Quality overlay (A16 market_quality)
        ↓
betting_plan/legs.py  → market-level legs for plan date
        ↓
┌───────────────────┬────────────────────┬─────────────────────┐
│ singles categorize│ combos.py          │ bankroll.py         │
│ elite/strong/...  │ safe/balanced/...  │ stake % by profile  │
└───────────────────┴────────────────────┴─────────────────────┘
        ↓
engine.py → daily plan + portfolios + day quality
        ↓
gating.py → plan-tier display (free/starter/pro/owner)
        ↓
API routes + BettingPlanPage.jsx
```

**Read-only inputs:** PredOps store, `build_publication_overlay`, `collect_upcoming_fixtures`, `build_performance_summary`.

**No writes** to predictions, WDE, or billing tables.

---

## Plan generation logic

1. Select fixtures whose kickoff **date** matches plan day (today/tomorrow or `YYYY-MM-DD`).
2. Load latest PredOps snapshot per fixture; skip stale payloads.
3. Expand `publication_overlay.market_quality` into ranked legs (fixture, league, market, prediction, quality, reason, snapshot_id, last_updated).
4. Categorize singles:
   - Elite ≥90, Strong ≥80, Good ≥70, Risky ≥45, **Avoid <45** (never hidden).
5. Build combos with conflict/correlation rules (ported from A16 combo logic).
6. Assess **day quality** (Excellent / Good / Risky / Poor) from elite count, strong count, average quality, combo readiness, avoid load.
7. Optionally attach bankroll stakes and portfolios when `bankroll` query param provided.

---

## Combo logic

| Type | Legs | Min quality | Risk |
|------|------|-------------|------|
| Safe | 2–4 | 90 | Low |
| Balanced | 3–5 | 75 | Medium |
| Value | 3–6 | 60 | Medium (value/odds sort) |
| High Odds | 4–8 | 45 | High |

Empty combo reasons: `not_enough_eligible_legs`, `too_many_conflicts`, `too_many_correlated_legs`, `quality_too_low`.

Odds: use snapshot odds when present; otherwise estimate from probability with `odds_estimated: true`. Missing odds trigger `missing_odds_warning`.

---

## Bankroll formula

| Profile | Single stake % | Combo max % |
|---------|----------------|-------------|
| Conservative | 0.5–1% | up to 2% |
| Balanced | 1–2% | up to 4% |
| Aggressive | 2–4% | up to 8% |

Stake % scales linearly with bet quality within profile range:

`stake_pct = min_pct + (quality/100) * (max_pct - min_pct)`  
`recommended_stake = bankroll * stake_pct`

Portfolio exposure sums singles + combo stakes; flags high exposure >15%.

**Planning only** — no bet execution.

---

## Subscription display gating (no billing changes)

| Plan | Visibility |
|------|------------|
| Free | One `best_single`; combo preview labels only; no bankroll/portfolios/performance |
| Starter | Full singles; safe + balanced combos; bankroll on request |
| Pro | All combos, portfolios, performance insights |
| Owner/Admin | Debug: `score_inputs`, `snapshot_id`, WDE caution, `fixture_no_bet` |

---

## Performance feedback

`performance_insights.py` calls `build_performance_summary()` read-only.

- If `total_evaluated <= 0`: message *"Performance history will appear after evaluated bets."*
- Otherwise: per-market winrates with sample sizes (no fabricated combo history).

---

## Files changed

### Backend (new)

- `worldcup_predictor/betting_plan/__init__.py`
- `worldcup_predictor/betting_plan/constants.py`
- `worldcup_predictor/betting_plan/legs.py`
- `worldcup_predictor/betting_plan/combos.py`
- `worldcup_predictor/betting_plan/bankroll.py`
- `worldcup_predictor/betting_plan/day_quality.py`
- `worldcup_predictor/betting_plan/performance_insights.py`
- `worldcup_predictor/betting_plan/gating.py`
- `worldcup_predictor/betting_plan/engine.py`
- `worldcup_predictor/api/routes/betting_plan.py`

### Backend (wired)

- `worldcup_predictor/api/main.py` — register betting-plan router

### Frontend (new)

- `base44-d/src/api/bettingPlanApi.js`
- `base44-d/src/lib/bankrollCalculator.js`
- `base44-d/src/pages/BettingPlanPage.jsx`

### Frontend (updated)

- `base44-d/src/App.jsx` — `/betting-plan` route
- `base44-d/src/lib/navConfig.js` — **AI Betting Plan** nav link

### Ops

- `scripts/validate_phase_a17_ai_betting_manager.py`
- `scripts/deploy_phase_a17_production.sh`
- `scripts/deploy_phase_a17_smoke.sh`

### Unchanged

- WDE, EGIE, scoring, calibration, prediction pipeline, Stripe/billing

---

## Validation

| Environment | Result |
|-------------|--------|
| Local | **31/31 PASS** |
| Production (venv) | **31/31 PASS** |

Artifact: `data/validation/phase_a17_betting_manager_validation.json`

---

## Deployment

### Backups (production)

- SQLite, frontend dist, repo tarball, pre-deploy commit under `backups/deploy-phase-a17-*`
- PostgreSQL dump when `DATABASE_URL` available

### Smoke (production)

| Endpoint | HTTP |
|----------|------|
| `/betting-plan` | 200 |
| `/api/betting-plan/today` | 200 |
| `/api/betting-plan/portfolio?date=today&bankroll=100&profile=balanced` | 200 |
| `/combo-tips` | 200 |
| `/api/matches` | 200 |
| `/api/predops/combo-readiness` | 200 |

Sample production plan (2026-06-25): day quality **Poor**, 15 market legs, free-tier `best_single` surfaced (Japan vs Sweden BTTS, quality 65.1).

---

## Rollback plan

1. Restore `backups/deploy-phase-a17-*/frontend_dist` → `/var/www/worldcup/frontend/dist`
2. Extract `repo_pre_deploy.tar.gz` over `/opt/worldcup-predictor`
3. Restore SQLite if needed
4. `systemctl restart worldcup-api && systemctl reload nginx`
5. Verify `/api/betting-plan/today` returns 404 or prior behavior

Module is additive; rollback removes router + UI only.

---

## Final status

**`AI_BETTING_MANAGER_DEPLOYED_OK`**
