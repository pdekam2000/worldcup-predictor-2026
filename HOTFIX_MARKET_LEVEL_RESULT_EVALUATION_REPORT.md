# HOTFIX — Market-Level Result Evaluation Report

**Generated:** 2026-06-26  
**Mode:** Diagnose → Fix → Validate → Report  
**Deploy status:** **NOT deployed** — awaiting owner approval

**Constraints honored:** No model, prediction logic, public flag, or backtest rewrite changes.

---

## Executive summary

Finished matches in Result/Archive were misleading because **display** read `detailed_markets.match_winner` (showing **Predicted: X** for draws) while **evaluation** scored only top-level `payload.prediction` and then **collapsed row status** to secondary markets when 1X2 was void — producing **Wrong** badges unrelated to the displayed pick.

This hotfix unifies evaluation sources, evaluates every stored market separately, fixes aggregate card status (**Partial** when mixed), adds market filters + expandable breakdown in UI, and restricts **public winrate** to **best bets only**.

---

## Part A — Root cause

| Layer | Problem |
|-------|---------|
| **Display** | `_main_prediction()` uses `prediction` OR `detailed_markets.match_winner.selection` → draw shows as **X** |
| **Evaluation** | `pick_evaluator` used `payload.prediction` only for 1X2; OU/BTTS from `probabilities` not `detailed_markets` |
| **Row status** | `compute_row_status_from_evaluation()` preferred 1X2, then fell through to **all secondary wrong** → whole card **Wrong** |
| **Winrate** | `compute_history_stats()` counted card-level correct/wrong across all rows, not best-bet picks only |
| **UI** | Results cards always showed 1X2 pick even when user filtered another market; breakdown was status chips only |

**Note:** `X` in 1X2 display means **draw predicted**, not “unknown”.

**Old payloads:** Many rows only have 1X2 — we do **not** fabricate missing markets.

---

## Part B — Market-level evaluation (backend)

### New module

`worldcup_predictor/api/market_level_evaluation.py`

Per-market row fields:

- `market_key`, `market_label`, `predicted_pick`, `display_pick`
- `actual_result`, `is_correct`, `status` (correct/wrong/pending/unavailable)
- `confidence`, `probability`, `tier`
- `was_best_bet`, `was_user_visible`, `evaluation_reason`

### Evaluator changes

`pick_evaluator.py`:

- 1X2 via `canonical_1x2_selection()` (aligned with display)
- OU/BTTS via `detailed_markets` with `probabilities` fallback
- `attach_market_evaluations_to_result()` adds `market_evaluations`, `card_status`, `limited_historical_payload` to `detail_json`

### Archive join

`archive_evaluation_join.py`:

- `unavailable` no longer normalized to `pending`
- Row status uses **card aggregate** from `detail_json.card_status` or mixed-market logic (no `main_1x2_evaluation` collapse)

### API

`evaluated_results.py` + `routes/results.py`:

- `market` query param on `/api/results/evaluated`
- Response includes `market_breakdown`, `winrate.best_bet_winrate`, `limited_historical_payload`
- Market filter sets `filtered_market_view` per row

`global_prediction_archive.py`:

- Archive rows include `market_breakdown`, `has_best_bet`
- `compute_history_stats()` → `compute_archive_winrate_stats()` (best bet winrate primary)

---

## Part C–E — UI changes

### Market filter dropdown (Results + Archive)

`MARKET_FILTERS` expanded in `archiveFilters.js`:

- Best Bets Only (default), All Markets, 1X2, BTTS, Over/Under 2.5, Double Chance, Correct Score, First Goal Team, Goal Time Range, Goalscorer

Filtered view shows **that market’s pick and status**, not unrelated 1X2.

### Market breakdown per match

`MarketBreakdownPanel.jsx` — expandable rows with green/red/amber/gray per market, **Best bet** badge.

Used in:

- `PredictionResultsPage.jsx`
- `ArchiveCard.jsx`

### Card aggregate status

- **Correct** / **Wrong** / **Partial** / **Pending** / **Unavailable**
- Footer counts: `N correct · M wrong · K unavailable`
- Default list view: **Best Bets Only**

### Yellow / white theme

Results and Archive pages use **amber/yellow + white** surfaces per product direction (`amber-50`, `amber-400`, white cards).

---

## Part F — Winrate rule

**Public winrate = Best Bet Winrate only**

Included when:

- `was_best_bet = true`
- `was_user_visible = true`
- `no_bet = false`
- fixture finished, status correct/wrong
- not quarantined / not shadow / not research-only

Excluded: internal probabilities, hidden markets, unavailable, no_bet, shadow, admin experimental.

Archive header label: **Best Bet Winrate**  
API also exposes `market_research_accuracy` for internal separation (Accuracy Center can use later).

---

## Part G — Backward compatibility

- Old rows: `market_rows_from_evaluation()` rebuilds from DB columns + payload (no payload overwrite)
- `limited_historical_payload: true` when only 1X2 present → UI shows *"Limited historical payload"*
- Missing markets → `status: unavailable`, `evaluation_reason: not_predicted`
- Re-running evaluation job will refresh `detail_json.market_evaluations` without changing stored predictions

---

## Part H — Validation

```bash
python scripts/validate_hotfix_market_level_result_evaluation.py
```

**Result: 31/31 PASS**

Artifact: `data/validation/hotfix_market_level_result_evaluation.json`

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/api/market_level_evaluation.py` | **NEW** — core market eval + winrate |
| `worldcup_predictor/automation/worldcup_background/pick_evaluator.py` | Unified picks + market rows |
| `worldcup_predictor/api/archive_evaluation_join.py` | Aggregate status, unavailable |
| `worldcup_predictor/api/evaluated_results.py` | Breakdown, filters, winrate |
| `worldcup_predictor/api/global_prediction_archive.py` | Breakdown on rows, best-bet stats |
| `worldcup_predictor/api/routes/results.py` | `market` query param |
| `base44-d/src/lib/archiveFilters.js` | Filters + `marketViewForItem` |
| `base44-d/src/lib/archiveStatus.js` | Yellow/white status colors |
| `base44-d/src/components/archive/MarketBreakdownPanel.jsx` | **NEW** |
| `base44-d/src/components/archive/ArchiveCard.jsx` | Filter-aware + breakdown |
| `base44-d/src/pages/PredictionResultsPage.jsx` | Market filter, theme, breakdown |
| `base44-d/src/pages/ArchivePage.jsx` | Default best bets, winrate label, theme |
| `base44-d/src/api/saasApi.js` | `market` param |
| `scripts/validate_hotfix_market_level_result_evaluation.py` | **NEW** |

**Not changed:** WDE, EGIE, Stripe/auth, prediction engine, public unified flags, backtest rewrite.

---

## Before / after UI behavior

| Before | After |
|--------|-------|
| Card **Wrong** while showing unrelated 1X2 **X** | Card **Partial** when markets split; filter shows relevant pick |
| Single market status chips | Full per-market breakdown with pick → result |
| Winrate = all settled cards | **Best Bet Winrate** only |
| Dark terminal styling on results | Yellow/white public styling |
| No market filter on Results | Market dropdown with Best Bets default |

---

## Known limitations

1. **Existing evaluations** in DB may lack `market_evaluations` in `detail_json` until the next evaluation job run — API rebuilds breakdown on read from columns + payload.
2. **OU lines** 0.5/1.5/3.5 evaluated only when present in payload (most stored preds have 2.5).
3. **Accuracy Center** still has separate research/shadow views — not fully split in this hotfix UI beyond archive stats object.
4. **Historical 1X2-only** rows remain limited; no retroactive multi-market data.

---

## Rollback plan

1. Revert the files listed above to prior commit.
2. Redeploy backend + frontend bundle.
3. Evaluation rows in SQLite are forward-compatible — old `detail_json` still readable; no migration required.
4. No stored prediction payloads were modified.

---

## Next steps (after owner approval)

1. Deploy backend to production.
2. Run `run_evaluate_worldcup_results(skip_unchanged=False)` once to refresh `detail_json.market_evaluations` on finished fixtures.
3. Deploy frontend (`base44-d` build).
4. Spot-check `/results` and `/archive` with **Best Bets Only** and **Over 2.5** filters.

**Stopped after report. Not deployed.**
