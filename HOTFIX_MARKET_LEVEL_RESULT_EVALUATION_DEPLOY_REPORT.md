# HOTFIX — Market-Level Result Evaluation + Best Bet Winrate — Deploy Report

**Date:** 2026-06-26  
**Production:** https://footballpredictor.it.com (`91.107.188.229`)  
**Mode:** Backup → Deploy → Refresh Evaluations → Smoke Test → Report  
**Approval:** APPROVED FOR DEPLOY  
**Source spec:** `HOTFIX_MARKET_LEVEL_RESULT_EVALUATION_REPORT.md`

---

## Executive summary

| Item | Status |
|------|--------|
| Pre-deploy backup | **Complete** |
| Backend deploy | **Complete** |
| Frontend build + deploy | **Complete** |
| Evaluation refresh | **36 rows updated**, 0 errors |
| API / SPA smoke tests | **All functional checks PASS** |
| Local validation (pre-deploy) | **31/31 PASS** |
| Production validation (post-deploy) | **30/31 PASS** (see limitations) |
| Auth / subscription / archive regression | **PASS** (no new regressions) |
| Prediction engine / WDE / EGIE / Stripe | **Unchanged** |

### Final status: **DEPLOYED_WITH_LIMITATIONS**

Hotfix is live. Market-level evaluation, market filters, Best Bet Winrate, and UI breakdown are active. One non-functional validation sentinel (`flags:unchanged`) fails on production because `settings.py` on the server predates `UNIFIED_ENGINE_PUBLIC` alias strings in repo — **not modified by this hotfix**.

---

## Part A — Pre-deploy backup

| Artifact | Path |
|----------|------|
| **Backup root** | `/opt/worldcup-predictor/backups/deploy-hotfix-market-level-20260626-205016` |
| **Size** | ~552 MB |
| **Pre-deploy git commit** | `ee762edc1a224c81fa0e87f5e713c47dc27ec823` |
| **SQLite snapshot** | `football_intelligence.db` |
| **PostgreSQL dump** | `postgres_pre.sql` (~158 MB) |
| **Frontend dist tarball** | `frontend_dist_pre.tar.gz` |
| **nginx config copy** | `nginx_worldcup.conf` |
| **Env copy** | `env.production` |
| **Repo file snapshot** | `repo_snapshot_pre.tar.gz` |
| **Service status (pre)** | `worldcup-api=active`, `nginx=active` |

Local repository state was preserved in git working tree; deploy tarball built from validated local files.

---

## Part B — Deploy (backend + frontend)

### Deploy method

1. Packed tarball locally → `/tmp/hotfix_market_level_deploy.tar.gz`
2. `scp` to production `/tmp/`
3. Extracted to `/opt/worldcup-predictor`
4. Ran `scripts/deploy_hotfix_market_level_production.sh`

### Files deployed

| File | Role |
|------|------|
| `worldcup_predictor/api/market_level_evaluation.py` | **NEW** — per-market eval + best bet winrate |
| `worldcup_predictor/automation/worldcup_background/pick_evaluator.py` | Unified picks + `market_evaluations` |
| `worldcup_predictor/api/archive_evaluation_join.py` | Aggregate card status, unavailable preserved |
| `worldcup_predictor/api/evaluated_results.py` | Breakdown, filters, winrate |
| `worldcup_predictor/api/global_prediction_archive.py` | Archive rows + best-bet stats |
| `worldcup_predictor/api/routes/results.py` | `market` query param |
| `base44-d/src/lib/archiveFilters.js` | Market filter options + view helpers |
| `base44-d/src/lib/archiveStatus.js` | Yellow/white status colors |
| `base44-d/src/components/archive/MarketBreakdownPanel.jsx` | **NEW** expandable breakdown |
| `base44-d/src/components/archive/ArchiveCard.jsx` | Filter-aware cards |
| `base44-d/src/pages/PredictionResultsPage.jsx` | Results page + default best bets |
| `base44-d/src/pages/ArchivePage.jsx` | Best Bet Winrate header |
| `base44-d/src/api/saasApi.js` | `market` param on evaluated API |
| `scripts/validate_hotfix_market_level_result_evaluation.py` | Validation |
| `scripts/refresh_market_level_evaluations.py` | **NEW** one-time refresh |
| `scripts/deploy_hotfix_market_level_production.sh` | Deploy orchestration |
| `scripts/deploy_hotfix_market_level_smoke.sh` | Smoke tests |

### Build + restart

- `npm run build` in `base44-d` — **SUCCESS**
- Frontend synced to `/var/www/worldcup/frontend/dist/`
- `systemctl restart worldcup-api` — **active**
- `nginx -t && systemctl reload nginx` — **OK**

### Deploy script fix applied locally

Smoke step failed on first run because cwd remained in `base44-d` after build. Fixed deploy script to `cd "${APP}"` before smoke (patched in repo for future deploys).

---

## Part C — Refresh existing evaluations

Script: `scripts/refresh_market_level_evaluations.py`

### Dry-run

```json
{"errors": 0, "limited_historical_payload": 2, "scanned": 56, "skipped_no_payload": 0, "skipped_pending": 18, "skipped_quarantined": 2, "skipped_unchanged": 0, "updated": 36}
```

### Apply

```json
{"errors": 0, "limited_historical_payload": 2, "scanned": 56, "skipped_no_payload": 0, "skipped_pending": 18, "skipped_quarantined": 2, "skipped_unchanged": 0, "updated": 36}
```

| Count | Value | Notes |
|-------|-------|-------|
| scanned | 56 | Stored World Cup predictions |
| updated | 36 | `detail_json` refreshed with `market_evaluations` |
| skipped_pending | 18 | Fixtures not finished |
| skipped_quarantined | 2 | Excluded per rules |
| limited_historical_payload | 2 | Old 1X2-only rows flagged, not fabricated |
| skipped_no_payload | 0 | — |
| errors | 0 | — |

**Stored prediction payloads were not modified** — only evaluation `detail_json` / evaluation columns via existing upsert path.

---

## Part D — Smoke test results

| # | Test | Result |
|---|------|--------|
| 1 | `GET /api/health` | **200 PASS** |
| 2 | Default evaluated view (`market=best_bets`) | **200 PASS** — `winrate.best_bet_winrate` present |
| 3a | `market=over_2_5` | **200 PASS** |
| 3b | `market=1x2` | **200 PASS** |
| 3c | `market=btts` | **200 PASS** |
| 4 | Detail / breakdown | **PASS** (validation + API returns `market_breakdown`) |
| 5 | Fixture `1489409` predict | **200 PASS**, `no_bet: true` confirmed |
| 6 | Frontend `/results`, `/archive` | **200 PASS** (SPA shells) |
| 6b | Homepage | **200 PASS** |

### Notes on archive history API

`GET /api/history?scope=global` returns **401** without auth (expected — route requires login). Public winrate + market filters for the Results page are served via **`GET /api/results/evaluated`** (no auth). Authenticated Archive page uses `/api/history` client-side after login.

Sample public API response (default best bets):

```json
"winrate": {
  "best_bet_winrate": {"total": 1, "correct": 0, "accuracy": 0.0},
  "market_research_accuracy": {"total": 7, "correct": 3, "accuracy": 42.9}
}
```

Fixture `1489409`: `no_bet true` — excluded from public Best Bet Winrate (confirmed).

---

## Part E — Validation after deploy

| Script | Environment | Result |
|--------|-------------|--------|
| `validate_hotfix_market_level_result_evaluation.py` | Local (pre-deploy) | **31/31 PASS** |
| `validate_hotfix_market_level_result_evaluation.py` | Production | **30/31 PASS** |
| `validate_phase41b_auth_hardening.py` | Production | **PASS** (38A regression 40/40) |
| `validate_phase38a_subscription_system.py` | Production | **PASS** |
| `validate_hotfix_archive_status_evaluation_join.py` | Production | **PASS** |
| Frontend build (post-deploy re-check) | Production | **SUCCESS** |

### Failed check (non-blocking)

| Check | Reason |
|-------|--------|
| `flags:unchanged` | Production `settings.py` does not contain literal `UNIFIED_ENGINE_PUBLIC` string (older server copy). Hotfix did **not** change `settings.py`. Repo-local validation passes 31/31. |

---

## Part F — Before / after

Screenshots were not captured in this automated deploy session. Observed behavior changes:

| Before | After |
|--------|-------|
| Card Wrong while showing unrelated 1X2 X | Partial / filter-aware status |
| Single status chips | Expandable per-market breakdown |
| Winrate = all settled cards | **Best Bet Winrate** only |
| Dark results styling | Amber/yellow + white theme |
| No market filter on Results | Dropdown, default **Best Bets Only** |

---

## Known limitations

1. **Production validation 30/31** — `flags:unchanged` sentinel reflects pre-existing prod/repo drift in `settings.py`, not hotfix regression.
2. **Historical 1X2-only rows** (2 fixtures) remain `limited_historical_payload`; no retroactive multi-market data invented.
3. **18 fixtures** still pending (matches not finished).
4. **`/api/history`** requires authentication; public smoke uses `/api/results/evaluated`.
5. **Accuracy Center** research/shadow split unchanged beyond archive stats object.

---

## Rollback plan

1. Restore backup:
   ```bash
   BACKUP=/opt/worldcup-predictor/backups/deploy-hotfix-market-level-20260626-205016
   tar xzf $BACKUP/repo_snapshot_pre.tar.gz -C /opt/worldcup-predictor
   tar xzf $BACKUP/frontend_dist_pre.tar.gz -C /var/www/worldcup/frontend/
   cp $BACKUP/football_intelligence.db /opt/worldcup-predictor/data/  # only if DB rollback needed
   systemctl restart worldcup-api && systemctl reload nginx
   ```
2. Evaluation rows remain forward-compatible; rollback restores prior code + optional DB snapshot.
3. No stored prediction payloads were modified — rollback does not require payload restore.

---

## Production status

| Service | Status |
|---------|--------|
| `worldcup-api` | **active** |
| `nginx` | **active** |
| Frontend dist | Updated 2026-06-26 ~20:50 UTC |
| `market_level_evaluation.py` | Present on server |

### Final status: **DEPLOYED_WITH_LIMITATIONS**

Functional hotfix is **PRODUCTION ACTIVE**. Limitation: post-deploy validation sentinel `flags:unchanged` (30/31) due to unchanged older production `settings.py` — does not affect market evaluation, winrate, or UI behavior.

**Stopped after report.**
