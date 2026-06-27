# PHASE A18 — Paper Betting Simulator & Monthly ROI Tracker

**Date:** 2026-06-25  
**Environment:** Production `https://footballpredictor.it.com`  
**Pre-deploy commit:** `ee762edc1a224c81fa0e87f5e713c47dc27ec823`  
**Backup:** `/opt/worldcup-predictor/backups/deploy-phase-a18-20260625-150901`

---

## Final Status

**`PAPER_BETTING_DEPLOYED_OK`**

---

## Summary

Phase A18 adds a **simulation-only** virtual betting layer. Users create a virtual bankroll, add singles/combos from AI Betting Plan, Combo Tips, and Match Center, and track profit/loss, ROI, win rate, and monthly performance. Bets settle automatically from the same archive evaluation source used by `/archive` and `/accuracy`. No real betting, bookmaker integration, payments, or changes to WDE, EGIE, models, calibration, or billing logic.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (base44-d)                                            │
│  /paper-betting          PaperBettingPage                       │
│  AddToPaperBetButton     BettingPlan, ComboTips, EliteMatchCard │
│  paperBettingApi.js      Auth-gated REST client                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  API  worldcup_predictor/api/routes/paper_betting.py            │
│  POST/GET /api/paper-betting/account                            │
│  POST     /api/paper-betting/bets | /bets/combo               │
│  GET      /api/paper-betting/bets | /summary                    │
│  GET      /api/paper-betting/monthly-report                     │
│  GET      /api/paper-betting/strategy-comparison                │
│  POST     /api/paper-betting/settle                             │
│  POST     /api/admin/paper-betting/settle-pending               │
│  GET      /api/admin/paper-betting/aggregate                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  Service layer  paper_betting/                                  │
│  service.py      place bet, account CRUD, plan gating           │
│  store.py        SQLite CRUD + aggregates                         │
│  settlement.py   settle from worldcup_prediction_evaluations    │
│  analytics.py    summary, strategy comparison, monthly report     │
│  gating.py       display-only subscription gates (no billing)   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  SQLite (football_intelligence.db)                              │
│  paper_betting_accounts | paper_betting_bets                    │
│  paper_betting_settlements | paper_betting_monthly_reports      │
└─────────────────────────────────────────────────────────────────┘
```

**Integration points (read-only):**

- AI Betting Plan (`betting_plan/`) — stake recommendations via `recommend_stake`
- Archive evaluations (`worldcup_prediction_evaluations` + `archive_evaluation_join`)
- Bet Quality overlay scores passed from frontend at bet placement
- PredOps `snapshot_id` stored on each bet for traceability

**Explicitly untouched:**

- `weighted_decision_engine.py` (WDE)
- EGIE / scoring / calibration pipelines
- Subscription billing and quota enforcement (only display gating added)

---

## Database Changes

Non-destructive DDL added to `ensure_schema_compat()` in `worldcup_predictor/database/migrations.py` (`PHASE_A18_DDL`):

| Table | Purpose |
|-------|---------|
| `paper_betting_accounts` | Virtual bankroll per user per month (`UNIQUE(user_id, month)`) |
| `paper_betting_bets` | Individual virtual bets with status, P/L, settlement metadata |
| `paper_betting_settlements` | Audit trail per settlement event |
| `paper_betting_monthly_reports` | Cached monthly report JSON per user/month |

**Account fields:** `starting_bankroll`, `current_bankroll`, `currency`, `risk_profile` (conservative/balanced/aggressive), `month`, `created_at`, `updated_at`

**Bet fields:** `fixture_id`, `market`, `prediction`, `stake`, `odds_decimal`, `bet_quality_score`, `combo_type`, `combo_group_id`, `source_page`, `snapshot_id`, `status`, `settlement_reason`, `profit_loss`, `settled_at`

Indexes on `(user_id, month)`, `(user_id, status, created_at)`, `fixture_id`, and `bet_id` for settlements.

---

## Virtual Bankroll Logic

1. **Create account** — `POST /api/paper-betting/account` with `starting_bankroll`, `currency`, `risk_profile`.
2. **One account per user per calendar month** — `UNIQUE(user_id, month)`.
3. **Place bet** — stake deducted from `current_bankroll` immediately.
4. **Default stake** — if not provided, uses `recommend_stake()` from AI Betting Plan bankroll module based on account risk profile and bet quality score.
5. **Reset month** — `reset_month: true` creates a fresh account row for the current month with new starting bankroll.
6. **Free plan limit** — max 5 paper bets per day (`FREE_DAILY_BET_LIMIT`); Starter+ unlimited.

---

## Settlement Logic

Settlement runs on:

- User visit to `/paper-betting` (frontend calls `POST /api/paper-betting/settle`)
- Manual admin/cron: `POST /api/admin/paper-betting/settle-pending`

**Source of truth:** `worldcup_prediction_evaluations` via the same column mapping as Archive/Accuracy (`MARKET_EVAL_COLUMN` → `market_1x2_status`, `market_ou_status`, etc.). Quarantined evaluations are skipped (bet stays pending).

| Evaluation status | Bet status |
|-------------------|------------|
| `correct` | `won` |
| `wrong` | `lost` |
| `partial` | `partial` |
| missing / quarantined | `pending` (no fake results) |

**P/L on settlement:**

| Status | Profit | Bankroll change |
|--------|--------|-----------------|
| Won (with odds) | `stake × (odds − 1)` | + payout |
| Won (no odds) | `null` (tracked as win, reason: `won_profit_unavailable_no_odds`) | stake returned only |
| Lost | `−stake` | no payout |
| Partial (with odds) | `stake × 0.5 × (odds − 1)` | half profit |
| Void | `0` | stake returned |

Each settlement writes to `paper_betting_settlements` with `evaluation_source`, `odds_used`, and `reason`.

---

## ROI Formula

```
profit_loss = current_bankroll − starting_bankroll
ROI %       = (profit_loss / starting_bankroll) × 100
winrate %   = (won / (won + lost + partial)) × 100   [settled bets only]
```

Period filters (`today`, `week`, `month`, `all`) filter bets by `created_at` for counts; bankroll ROI uses live account balance for the active month.

---

## Strategy Comparison

`GET /api/paper-betting/strategy-comparison?bankroll=100`

Replays the user's **settled** bet history (≥3 required) with three virtual stake profiles:

- **Conservative** — lower % of bankroll per bet
- **Balanced** — default AI plan sizing
- **Aggressive** — higher % of bankroll per bet

For each profile, simulates chronological replay using `recommend_stake()` and computes:

- profit/loss, ROI %, winrate, max drawdown %, average stake, average quality, bet count
- `best_profile` = highest ROI among the three

**Pro plan gate** — Free/Starter see `available: false` with upgrade message. Empty state when &lt;3 settled bets (no fabricated performance).

---

## Monthly Report

`GET /api/paper-betting/monthly-report?month=YYYY-MM`

Generates narrative headline:

> "If you followed AI tips with virtual bankroll X EUR, net result was +Y.YY"

Includes: net P/L, ROI, winrate, best/worst market, best/worst quality tier (elite/strong/good/risky), best combo type, recommendation for next month, disclaimer.

Cached in `paper_betting_monthly_reports`. **Starter+** required (display gate only).

---

## Subscription Display (No Billing Changes)

| Plan | Paper Betting access |
|------|---------------------|
| Free | 1 bankroll, 5 bets/day, basic summary |
| Starter | Unlimited bets, monthly report |
| Pro | Strategy comparison, advanced analytics fields |
| Owner/Admin | Anonymized aggregate via admin API |

---

## Frontend

| Route | Component |
|-------|-----------|
| `/paper-betting` | `PaperBettingPage.jsx` |

**Navigation:** "Paper Betting" in `navConfig.js`

**Add bet buttons:** `AddToPaperBetButton` on:

- `/betting-plan` — singles and combos
- `/combo-tips` — combo track
- `/matches` (Match Center) — `EliteMatchCard`

**Disclaimer (visible on page):**

> Virtual betting is for analysis and education only. It does not guarantee real-money results.

---

## API Reference

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/paper-betting/account` | User |
| GET | `/api/paper-betting/account` | User |
| POST | `/api/paper-betting/bets` | User |
| POST | `/api/paper-betting/bets/combo` | User |
| GET | `/api/paper-betting/bets` | User |
| GET | `/api/paper-betting/summary?period=` | User |
| POST | `/api/paper-betting/settle` | User |
| GET | `/api/paper-betting/monthly-report` | User |
| GET | `/api/paper-betting/strategy-comparison` | User |
| POST | `/api/admin/paper-betting/settle-pending` | Admin |
| GET | `/api/admin/paper-betting/aggregate` | Admin |

---

## Validation Result

**Script:** `scripts/validate_phase_a18_paper_betting.py`

| Environment | Result |
|-------------|--------|
| Local | **33/33 PASS** |
| Production server | **33/33 PASS** |

Checks include: account creation, single/combo bets, bankroll deduction, won/lost settlement math, ROI summary, monthly report, strategy comparison shape, user isolation, pending settlement, no bookmaker refs, WDE/scoring unchanged, frontend build.

Output: `data/validation/phase_a18_paper_betting_validation.json`

---

## Deployment Result

**Scripts:**

- `scripts/deploy_phase_a18_production.sh` — backup, extract, migrate, build, restart, smoke
- `scripts/deploy_phase_a18_smoke.sh` — HTTP smoke checks

**Pre-deploy backups recorded:**

- PostgreSQL dump (if `DATABASE_URL` set)
- SQLite `football_intelligence.db`
- Frontend dist snapshot
- Repo tarball
- Pre-deploy commit hash

**Deploy output:**

```
=== Phase A18 Deploy ===
=== Extract tarball ===
=== Run migrations (SQLite schema compat) ===
=== Frontend build ===
=== Restart API ===
=== Reload nginx ===
=== Smoke ===
paper=200
api_account=401
api_summary=401
betting_plan=200
archive=200
accuracy=200
SMOKE_OK
DEPLOY_OK
```

`401` on account/summary is expected without auth token.

---

## Rollback Plan

1. Stop API: `systemctl stop worldcup-api`
2. Restore SQLite: `cp backups/deploy-phase-a18-*/football_intelligence.db data/`
3. Restore frontend: `rsync -a backups/deploy-phase-a18-*/frontend_dist/ /var/www/worldcup/frontend/dist/`
4. Restore repo: `tar xzf backups/deploy-phase-a18-*/repo_pre_deploy.tar.gz -C /opt/worldcup-predictor`
5. Restart: `systemctl start worldcup-api && systemctl reload nginx`
6. Verify: `/archive`, `/accuracy`, `/betting-plan` return 200

Paper betting tables are additive; rollback does not require dropping them. Old code simply ignores them.

---

## Known Gaps (Non-blocking)

| Item | Status |
|------|--------|
| Batch "Follow Today's Plan Virtually" button | Per-leg `AddToPaperBetButton` only |
| `AddToPaperBet` on `/matches/{fixtureId}` detail page | Match Center card only |
| Pro CSV export | Not implemented |
| Scheduled cron for `settle-pending` | Admin API exists; manual/on-page settle works |

---

## Safety Confirmation

- No real bet placement or bookmaker APIs
- No payment processing
- No WDE / EGIE / model / calibration changes (validated)
- No billing logic changes (display gating only)
- Settlement uses real archive evaluations only; pending when unavailable
- No guaranteed-profit wording; disclaimer shown on UI
