# OWNER-PREDICTIONS-UI-2 — UI Audit (Part A)

Phase: **OWNER-PREDICTIONS-UI-2** | Mode: Audit | Date: 2026-07-04

## Surfaces Audited

| Surface | Path | Prior behavior |
|---------|------|----------------|
| Match Center expand drawer | `base44-d/src/components/match-center/PredictionExpandPanel.jsx` | WDE Correct Score top 3 + separate "ECSE Exact Scores" (up to 5) |
| Match Center card (collapsed) | `base44-d/src/components/match-center/EliteMatchCard.jsx` | WDE 1X2 best pick only |
| Match detail (Summary/Markets) | `base44-d/src/pages/MatchDetailPage.jsx` | `EcseExactScorePanel` — labeled "ECSE Exact Scores" |
| Legacy prediction detail | `base44-d/src/pages/PredictionDetail.jsx` | WDE correct_scores list |
| Markets tab (Pro detail) | `predictionDetailProUtils.js` → `PredictionMarketsPro.jsx` | "Correct Score" group, slice(0,5) |
| Owner shadow labs | `OwnerEcseOddalertsShadow.jsx`, `OwnerEcseShadowLab.jsx` | Top 1/3/5/10 (owner-only, unchanged) |
| Admin owner predictions API | `GET /api/admin/owner-predictions` | Top1 + optional top_3 in JSON — **no UI page** |
| Archive/history detail | `prediction_archive_detail.py` | Top1 correct score only |

## Findings

### Top1-only vs Top3/Top5

- **Cards (collapsed):** WDE 1X2 only — unchanged (by design).
- **ECSE panel:** Previously showed up to 5 lines titled "ECSE Exact Scores" — implied single best score.
- **WDE payload:** `correct_scores` capped at 3 in API; partially shown as duplicate block.
- **DB:** `ecse_prediction_snapshots` has top_1/3/5/10; public display read from `ecse_score_distributions` (Top 5 max, ranking unchanged).

### Odds freshness metadata

- **Before:** Not exposed in UI API.
- **Logic existed:** `worldcup_predictor/research/ecse_rerank/features.py` (`odds_freshness_meta`) — shadow only.
- **ECSE-RERANK-1 audit:** 18/18 snapshots STALE_ODDS.

### Engine / cache visibility

- **Owner cards:** `OwnerInsightOverlay` shows cache/engine on match rows.
- **Admin API:** `cache_source`, `prediction_engine_version` in `/api/admin/owner-predictions`.
- **Public ECSE API:** No engine metadata before UI-2.

### Role / plan gating

- **Owner:** `OwnerRoute`, `require_owner_user` — shadow labs, owner_meta.
- **Admin:** `AdminRoute`, `require_admin_user` — admin APIs.
- **Pro:** `planGating.js` — EGIE/archive; **no end-result depth gating before UI-2**.
- **ECSE public route:** Unauthenticated allowed; optional Bearer for extended fields (UI-2).

## Gaps Addressed in UI-2

1. Unified **End Result Candidates** component (Top 3 public framing).
2. Expandable **Top 5** for Pro/owner/admin.
3. **Odds freshness badge** from read-only DB metadata.
4. **Shadow preview** owner/admin only, advisory labeled.
5. **No production ECSE re-rank** in display path.

## Files Targeted for Implementation

- `base44-d/src/components/match-center/EndResultCandidatesPanel.jsx` (new)
- `worldcup_predictor/research/ecse_match_display.py` (extended read-only payload)
- `worldcup_predictor/api/routes/ecse_display.py` (optional auth + field stripping)
- `base44-d/src/lib/trustCopy.js`, `planGating.js`
- Match Center + detail integration files
