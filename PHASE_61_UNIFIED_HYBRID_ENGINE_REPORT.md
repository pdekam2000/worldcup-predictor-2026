# PHASE 61 — Unified Hybrid Prediction Engine + Final UI/UX Rebuild

**Date:** 2026-06-20  
**Mode:** Analyze → Design → Implement → Validate → Backtest → Report  
**Deploy status:** **NOT DEPLOYED** — public unified engine **disabled by default**  

---

## Final recommendation

### `ADMIN_PREVIEW_READY`

The unified hybrid orchestration layer is implemented, validated (35/35), and available for **admin preview only**. Public users continue receiving **production Classic/WDE output** unchanged.

**Not yet:** `READY_FOR_PUBLIC_ROLLOUT` — comparative backtest on local dev showed EGIE/Unified arms at 0 coverage (PostgreSQL unreachable for goal_timing cache). Re-run backtest on production/staging with live PG before enabling `UNIFIED_ENGINE_PUBLIC=true`.

---

## Architecture

```
Provider Feature Store (cache/DB only)
  → ClassicSpecialist      (reads worldcup_stored_predictions — no PredictPipeline)
  → EGIESpecialist         (reads goal_timing_predictions — no engine re-run)
  → OddsMarketSpecialist   (SQLite odds snapshots)
  → LineupInjurySpecialist (EgieProviderFeatureStore fields)
  → HybridDecisionLayer    (market-weighted fusion, disagreement handling)
  → UnifiedConfidenceEngine (A/B/C/D tiers)
  → UnifiedPredictionOutput
```

**Preserved unchanged:**
- `ScoringEngine` / `PredictPipeline`
- `WeightedDecisionEngine` (WDE)
- `EliteGoalTimingEngine`
- Auth, Stripe, subscription limits

---

## Part A — Engine audit

See [`PHASE_61A_ENGINE_AUDIT.md`](PHASE_61A_ENGINE_AUDIT.md) for full market ownership matrix, duplicated logic, and staged merge plan.

---

## Part B–G — Backend implementation

### New package: `worldcup_predictor/unified_hybrid/`

| Module | Responsibility |
|--------|----------------|
| `engine.py` | `UnifiedHybridPredictionEngine` orchestrator |
| `specialists.py` | Read-only Classic / EGIE / odds / lineup adapters |
| `feature_store.py` | `UnifiedFixtureFeatureStore` per fixture |
| `decision_layer.py` | Market-weighted hybrid fusion |
| `confidence.py` | Unified confidence + tier A–D |
| `models.py` | `UnifiedPredictionOutput`, `UnifiedMarketPick` |
| `backtest.py` | Comparative backtest (Classic / EGIE / Production / Unified) |

### Markets in unified response

Classic: 1X2, BTTS, O/U 2.5, Double Chance, Correct Score, HT Result  
Goal intelligence: First Goal Team, Time Range, Approx Minute, Goalscorer markets  
Betting intelligence: Best Tip, combo candidates (safe / balanced / high-risk)

### Hybrid decision rules (examples)

- **1X2:** Classic 70%, odds agreement check  
- **First goal team:** EGIE 75%, Classic 25% — disagreement lowers confidence 15%  
- **Goal timing:** EGIE 90% weight  
- **Disagreement:** visible in `engine_agreement`, never hidden  

### Feature flags (`config/settings.py`)

| Flag | Default | Behavior |
|------|---------|----------|
| `UNIFIED_ENGINE_ENABLED` | `false` | Master switch |
| `UNIFIED_ENGINE_ADMIN_PREVIEW` | `true` | Admin API + UI preview |
| `UNIFIED_ENGINE_PUBLIC` | `false` | Replace public production output |
| `UNIFIED_ENGINE_COMPARE_MODE` | `true` | Classic vs EGIE vs Unified compare block |

### API routes (`/api/unified/*`)

| Endpoint | Access |
|----------|--------|
| `GET /api/unified/status` | Authenticated (shows flag state) |
| `GET /api/unified/predict/{fixture_id}` | Admin preview / public when enabled |
| `GET /api/unified/compare/{fixture_id}` | Admin only |
| `GET /api/unified/backtest/summary` | Admin only |

---

## Part H–J — UI rebuild (OddAlerts-inspired)

### Design

- Dark navy shell (`#070b14` / `#0c1222`)
- Green accents, gold tier badges
- Professional analytics dashboard feel (inspiration only — no copied branding)

### Navigation (Phase 61)

**Main:** Hub, Match Center, Best Tips, Combo Builder  
**Predictions:** Unified Predictions, Goal Intelligence, Odds Movement, Value Bets, Archive, Accuracy  
**Data:** Teams, Players, Referees, Standings, Leagues, API Health  
**Account:** Subscription, Profile, Settings  
**Admin:** Admin Dashboard, Elite Shadow Preview, Learning Center, System Health  

### New page

- `/unified-predictions` → `UnifiedPredictionsPage.jsx`  
  - Admin fixture lookup  
  - Compare mode panel  
  - All markets with tier/confidence labels  
  - Clear disclaimer: production unchanged until public flag enabled  

### Match Center

- Retains Phase 60A match cards and filters  
- Production predictions still from `/api/predict` cache  
- Unified panel available via Unified Predictions page (admin) until Match Center wired to unified API on approval  

---

## Part K — Backtest results (local sample)

**Sample:** 48 `world_cup_2026` stored predictions  

| Arm | Evaluated | Settled correct/wrong | Accuracy | Coverage |
|-----|-----------|----------------------|----------|----------|
| Classic | 48 | 10 / 9 | **52.6%** | 100% |
| Production | 48 | 10 / 9 | **52.6%** | 100% |
| EGIE | 0 | — | — | 0% (PG cache unavailable locally) |
| Unified | 0 | — | — | 0% (sample; PG timeout on EGIE reads) |

**Interpretation:** Classic/production baseline on 1X2 settled picks is ~52.6% (19 settled, 29 pending). Unified/EGIE arms require production PostgreSQL goal_timing data for meaningful comparison.

**Gate for public rollout:**
- Unified accuracy ≥ production on core markets OR equal with better coverage  
- Confidence calibration not worse  
- No auth/subscription regression  

→ **Re-run on server:** `GET /api/unified/backtest/summary?limit=500`

---

## Validation

```
python scripts/validate_phase61_unified_hybrid_engine.py
Phase 61 validation: 35/35 passed
npm run build — SUCCESS
```

Checks: package structure, safe flags, WDE/EGIE/Classic files untouched, read-only specialists, admin preview defaults, frontend routes, build.

---

## Files changed

### Backend (new)

- `worldcup_predictor/unified_hybrid/*` (8 modules)
- `worldcup_predictor/api/routes/unified_hybrid.py`
- `PHASE_61A_ENGINE_AUDIT.md`
- `scripts/validate_phase61_unified_hybrid_engine.py`

### Backend (modified)

- `worldcup_predictor/config/settings.py` — Phase 61 flags
- `worldcup_predictor/api/main.py` — router registration

### Frontend (new/modified)

- `base44-d/src/pages/UnifiedPredictionsPage.jsx`
- `base44-d/src/lib/navConfig.js` — Phase 61 nav
- `base44-d/src/components/dashboard/DashboardLayout.jsx` — navy pro theme
- `base44-d/src/api/saasApi.js` — unified API helpers
- `base44-d/src/App.jsx` — `/unified-predictions` route
- `base44-d/src/index.css` — `theme-pro-analytics` overrides

### Not modified

- `weighted_decision_engine.py`, `scoring_engine.py`, `goal_timing/engine.py` internals
- Stripe, auth, subscription quota logic

---

## Engine preservation proof

| Engine | Evidence |
|--------|----------|
| Classic/WDE | `specialists.py` reads cache only; validation confirms WDE/ScoringEngine classes intact |
| EGIE | `EGIESpecialist` reads `goal_timing_predictions`; `EliteGoalTimingEngine` file unmodified |
| Shadow | No public routes; elite shadow remains `/admin/elite-shadow` |

---

## Unified output example (shape)

```json
{
  "fixture_id": 12345,
  "home_team": "Team A",
  "away_team": "Team B",
  "best_tip": {
    "market_label": "1X2",
    "selection": "home",
    "confidence": 72.4,
    "tier": "B",
    "engine_agreement": "agree",
    "explanation": "Models and provider data are broadly aligned."
  },
  "markets": { "1x2": { ... }, "first_goal_team": { ... } },
  "compare_mode": {
    "classic_best": { "selection": "home" },
    "egie_best": { "selection": "home" }
  },
  "data_quality_score": 0.75,
  "missing_data_warnings": ["lineups"]
}
```

---

## Risks

1. **PG dependency** — EGIE cache reads require PostgreSQL; timeouts if unreachable  
2. **Backtest sample size** — local run insufficient for public promotion decision  
3. **UI not fully unified** — Match Center still shows production cache; unified is separate page  
4. **EGIE league scope** — PL-focused EGIE may not cover all Classic leagues  

---

## Rollback plan

1. Set env: `UNIFIED_ENGINE_ENABLED=false`, `UNIFIED_ENGINE_ADMIN_PREVIEW=false`  
2. Remove unified router from `api/main.py` (optional; flags sufficient)  
3. Revert frontend nav + `UnifiedPredictionsPage` if needed  
4. No migration required — orchestration is read-only overlay  

Instant rollback: flags only, no production prediction path mutation today.

---

## Deploy steps (when approved)

1. Deploy backend with new package + flags **OFF**  
2. Verify `/api/unified/status` returns `unified_engine_public: false`  
3. Enable `UNIFIED_ENGINE_ADMIN_PREVIEW=true` for admin testing  
4. Run production backtest: `/api/unified/backtest/summary?limit=500`  
5. Owner reviews Unified Predictions UI + compare mode  
6. Only then consider `UNIFIED_ENGINE_ENABLED=true` and eventually `UNIFIED_ENGINE_PUBLIC=true`  

---

## Owner sign-off

- [ ] Admin preview reviewed  
- [ ] Production backtest completed  
- [ ] Match Center unified panel wiring approved  
- [ ] Public rollout authorized  

**STOP — public unified engine NOT enabled. Awaiting owner approval.**
