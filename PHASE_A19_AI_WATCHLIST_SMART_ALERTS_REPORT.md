# PHASE A19 — AI Watchlist, Smart Alerts & Daily Assistant

**Date:** 2026-06-25  
**Environment:** Production `https://footballpredictor.it.com`  
**Pre-deploy commit:** `ee762edc1a224c81fa0e87f5e713c47dc27ec823`  
**Backup:** `/opt/worldcup-predictor/backups/deploy-phase-a19-20260625-155254`

---

## Final Status

**`AI_ASSISTANT_DEPLOYED_OK`**

---

## Summary

Phase A19 transforms WorldCup Predictor into a proactive daily AI assistant. Users follow competitions, teams, players, fixtures, and markets via **My Watchlist**, receive **smart in-app alerts** when meaningful changes occur, and view a **Daily AI Briefing** summarizing singles, combos, paper betting, and archive accuracy. Notification architecture is channel-ready (email/push/Telegram/Discord later). No changes to WDE, EGIE, models, calibration, scoring, or billing logic.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend                                                        │
│  /watchlist          WatchlistPage                               │
│  /daily-briefing     DailyBriefingPage                           │
│  /notifications      Notifications (merged legacy + AI)          │
│  NotificationBell    Unread badge (legacy + assistant)           │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  API  worldcup_predictor/api/routes/ai_assistant.py            │
│  GET/POST/DELETE /api/watchlist                                 │
│  GET/PATCH/POST  /api/assistant/notifications                   │
│  GET/POST        /api/preferences                               │
│  GET             /api/daily-briefing                            │
│  GET             /api/assistant/weekly-insights               │
│  POST            /api/admin/assistant/scan-alerts               │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  worldcup_predictor/ai_assistant/                               │
│  store.py        watchlist, notifications, preferences, state    │
│  channels.py     InApp + Email/Push/Telegram/Discord stubs       │
│  rules.py        dedup, quiet hours, meaningful-change gates     │
│  detectors.py    PredOps / betting plan / paper betting alerts   │
│  briefing.py     daily summary builder                           │
│  insights.py     weekly performance trends                       │
│  scheduler.py    run_alert_scan()                                │
│  service.py      orchestration                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  Read-only sources                                               │
│  predops_snapshots · betting_plan · paper_betting · archive eval │
└─────────────────────────────────────────────────────────────────┘
```

**Note:** AI notifications use `/api/assistant/notifications` to avoid conflicting with legacy SaaS `/api/notifications`. The UI merges both streams.

---

## Files Changed / Added

### Backend (new)

| Path | Role |
|------|------|
| `worldcup_predictor/ai_assistant/` | Full assistant module |
| `worldcup_predictor/api/routes/ai_assistant.py` | REST APIs |
| `worldcup_predictor/database/migrations.py` | `PHASE_A19_DDL` |
| `worldcup_predictor/api/main.py` | Router registration |

### Frontend (new/updated)

| Path | Role |
|------|------|
| `base44-d/src/pages/WatchlistPage.jsx` | Watchlist dashboard |
| `base44-d/src/pages/DailyBriefingPage.jsx` | Daily briefing |
| `base44-d/src/api/assistantApi.js` | API client |
| `base44-d/src/pages/Notifications.jsx` | Category filters + AI merge |
| `base44-d/src/components/layout/NotificationBell.jsx` | Combined unread count |
| `base44-d/src/lib/navConfig.js` | Watchlist, Briefing, Notifications nav |
| `base44-d/src/App.jsx` | Routes |

### Scripts

| Path | Role |
|------|------|
| `scripts/validate_phase_a19_ai_watchlist.py` | Validation (34 checks) |
| `scripts/deploy_phase_a19_production.sh` | Full deploy with backups |
| `scripts/deploy_phase_a19_quick.sh` | Streamlined deploy |
| `scripts/deploy_phase_a19_smoke.sh` | HTTP smoke |

---

## Database Changes

Additive SQLite tables via `PHASE_A19_DDL`:

| Table | Purpose |
|-------|---------|
| `assistant_watchlist` | User follows (competition/team/player/fixture/market) |
| `assistant_notifications` | In-app alerts with dedup_key |
| `assistant_preferences` | Alert frequency, quality filters, quiet hours, timezone |
| `assistant_alert_state` | Per-scope tracking for meaningful-change detection |

---

## Alert Types

| alert_type | Category | Trigger |
|------------|----------|---------|
| `quality_increase` | quality | Bet quality rises ≥5 pts (PredOps overlay) |
| `quality_decrease` | quality | Bet quality drops ≥5 pts |
| `best_pick_change` | prediction | Top market changes |
| `lineup_published` | prediction | PredOps lineup delta |
| `odds_movement` | quality | Significant odds shift (detector-ready) |
| `egie_prediction_change` | prediction | PredOps snapshot market deltas |
| `safe_combo_available` | combo | Safe combo in daily plan |
| `prediction_ready` | prediction | Coverage state completed |
| `match_final_hours` | system | Kickoff within 3 hours |
| `paper_bet_settled` | paper_betting | Virtual bet settled |
| `portfolio_updated` | paper_betting | Portfolio change (via settlement scan) |
| `roi_milestone` | paper_betting | ROI hits 5/10/20/50% |
| `drawdown_warning` | paper_betting | Bankroll drawdown ≥15% |
| `archive_accuracy_update` | archive | Archive aggregate in briefing |

Each alert stores: `alert_type`, `fixture_id`, `old_value`, `new_value`, `created_at`, `reason`, plus `title`/`message` for display.

---

## Smart Alert Rules

- **Deduplication:** `dedup_key` + 6-hour window prevents repeat alerts
- **Meaningful changes only:** Quality delta ≥5, odds movement ≥8%
- **Watchlist-scoped:** Snapshot alerts only for watched fixtures/competitions/teams
- **Quiet hours:** User-configurable; urgent types (settlement, final hours) still notify
- **Min bet quality:** User preference filters low-quality noise
- **No fake results:** Settlement alerts use real paper betting settlement only

---

## Scheduler Behavior

`run_alert_scan()` (triggered on deploy + `POST /api/admin/assistant/scan-alerts`):

1. Load users with watchlist items
2. For each user: scan latest PredOps snapshots for watched fixtures
3. Run detectors (quality, pick change, EGIE delta, lineups, final hours)
4. Pull today's betting plan for safe combo alerts
5. Settle paper bets and emit portfolio/ROI/drawdown alerts
6. Return `{ users_scanned, notifications_created, per_user }`

**Cron:** Admin API ready; add systemd timer as needed.

---

## Daily Briefing Contents

- Today's best singles (watchlist + quality filtered)
- Best combos (safe/balanced/value)
- Matches to avoid
- Highest quality fixtures
- Lineup news
- Quality changes overnight
- Paper betting month summary
- Archive accuracy snippet
- Weekly performance insights (when data available)

---

## Notification Channels (Email-Ready)

`channels.py` defines `NotificationChannel` ABC with:

- `InAppChannel` — active (SQLite persistence)
- `EmailChannel`, `PushChannel`, `TelegramChannel`, `DiscordChannel` — stubs for future wiring

User preferences store `channels: ["in_app"]` by default.

---

## User Preferences

`GET/POST /api/preferences`:

- `alert_frequency` (low/normal/high)
- `favorite_leagues`, `favorite_teams`
- `min_bet_quality`, `min_combo_type`
- `quiet_hours_start`, `quiet_hours_end`
- `timezone`
- `channels`

---

## Validation Result

| Environment | Result |
|-------------|--------|
| Local | **34/34 PASS** |
| Production | **34/34 PASS** |

Checks: watchlist CRUD, alerts, dedup, briefing, paper betting integration, preferences, user isolation, no bookmaker refs, WDE/scoring unchanged, frontend build.

Output: `data/validation/phase_a19_ai_watchlist_validation.json`

---

## Deployment Result

```
watchlist=200
notifications=200
briefing=200
paper=200
betting_plan=200
matches=200
api_watchlist=401
api_briefing=401
SMOKE_OK
DEPLOY_OK
```

`401` on authenticated APIs without token is expected.

---

## Rollback Plan

1. `systemctl stop worldcup-api`
2. Restore SQLite: `cp backups/deploy-phase-a19-*/football_intelligence.db data/`
3. Restore frontend: `rsync -a backups/deploy-phase-a19-*/frontend_dist/ /var/www/worldcup/frontend/dist/`
4. Restore repo tarball if captured
5. `systemctl start worldcup-api && systemctl reload nginx`

Assistant tables are additive; rollback does not require dropping them.

---

## Safety Confirmation

- No WDE / EGIE / model / calibration / scoring changes (validated)
- No billing logic changes
- No real betting or bookmaker integration
- Read-only use of PredOps, betting plan, paper betting, archive
- Educational disclaimer on daily briefing page

---

## Known Gaps (Non-blocking)

| Item | Status |
|------|--------|
| Automated cron for `scan-alerts` | Admin API only; manual/on-demand |
| Email/push delivery | Architecture stubs only |
| Preferences UI in Settings | API + watchlist page; full settings panel optional |
| `GET /api/notifications` spec path | Uses `/api/assistant/notifications` + UI merge to preserve legacy SaaS notifications |
