# OWNER-PREDICTIONS-UI-2 — Final Report

Phase: **OWNER-PREDICTIONS-UI-2** | Status: Complete — **UI only, no model promotion**

## Final Recommendation

**OWNER_UI_TOP3_READY**

Validation: **31/31 passed** | Frontend build: **OK** | ECSE re-rank: **NOT promoted**

---

## Summary

End Result presentation updated across Match Center and Match Detail. Public users see **Top 3 score candidates** with honest variance disclaimer. Pro/owner/admin can expand **Top 5** with consistency notes and engine metadata. Owner/admin see optional **shadow re-rank preview** (advisory only) when artifacts exist. **Odds freshness badge** added from read-only DB metadata.

No changes to WDE logic, ECSE production ranking, lambda calibration, or timers.

---

## Files Changed

### Backend (read-only payload extensions)

| File | Change |
|------|--------|
| `worldcup_predictor/research/ecse_match_display.py` | UI-2 payload: `top_3`, `top_5`, disclaimer, odds freshness, consistency notes, engine meta, shadow preview |
| `worldcup_predictor/api/routes/ecse_display.py` | Optional auth; strips top_5/shadow for public |

### Frontend

| File | Change |
|------|--------|
| `base44-d/src/components/match-center/EndResultCandidatesPanel.jsx` | **New** — Top 3/5, freshness badge, shadow preview gating |
| `base44-d/src/components/match-center/EcseExactScorePanel.jsx` | Thin wrapper → `EndResultCandidatesPanel` |
| `base44-d/src/components/match-center/PredictionExpandPanel.jsx` | Main Pick WDE 1X2 + End Result Candidates |
| `base44-d/src/pages/MatchDetailPage.jsx` | Uses `EndResultCandidatesPanel` |
| `base44-d/src/lib/trustCopy.js` | End result title + disclaimer strings |
| `base44-d/src/lib/planGating.js` | `canViewEndResultTop5()` |
| `base44-d/src/lib/predictionDetailProUtils.js` | Markets label → "End Result Candidates (WDE reference)" |

### Docs / validation

| File | Change |
|------|--------|
| `OWNER_PREDICTIONS_UI_2_AUDIT.md` | Part A audit |
| `scripts/validate_owner_predictions_ui_2_end_result_display.py` | Part F validation |
| `artifacts/owner_predictions_ui_2_validation.json` | Validation artifact |

---

## UI Locations Updated

| Surface | Before | After |
|---------|--------|-------|
| Match Center expand | "ECSE Exact Scores" (up to 5) + WDE Correct Score top 3 | **Main Pick WDE 1X2** + **End Result Candidates Top 3** + WDE reference (muted) |
| Match Detail Summary/Markets | "ECSE Exact Scores" up to 5 | **End Result Candidates Top 3** + expandable Top 5 (Pro/owner/admin) |
| Public users | Implied single best exact score | Top 3 candidates + variance disclaimer |
| Owner/admin | No shadow in match UI | Optional **Shadow Re-rank Preview** (advisory label) |

---

## Top 3 / Top 5 Handling

- **Public:** API returns `top_3` only; `top_5` stripped server-side.
- **Pro / owner / admin:** `top_5` + consistency notes (BTTS/O/U alignment, clean-sheet warning).
- **Fallback:** If Top 3 unavailable, single candidate with yellow warning.
- **Production ranking:** Still from `ecse_score_distributions` — no re-rank applied.

---

## Odds Freshness Display

Badge states (from `odds_snapshots` + prediction time):

| Flag | UI |
|------|-----|
| `FRESH_ODDS` | Green — "Fresh odds" |
| `STALE_ODDS` | Yellow — "Stale odds" |
| `ODDS_FRESHNESS_UNKNOWN` | Orange — owner/admin only (hidden from anonymous public) |
| `REQUIRES_FRESH_ODDS` | Yellow — when stale or unknown |

Tooltip: *"Odds age can affect exact-score ranking. Fresh odds are recommended for knockout matches."*

No odds fetched from UI or backend on page load beyond existing DB read.

---

## Shadow Preview Access Rules

| Role | Shadow preview |
|------|----------------|
| Public / guest | **Hidden** (stripped from API + frontend gate) |
| Pro | **Hidden** |
| Owner / admin | Shown only if `artifacts/ecse_rerank_1_shadow_results.jsonl` has fixture row |
| Label | "Shadow advisory only — not production prediction." |

ECSE re-rank logic remains in `worldcup_predictor/research/ecse_rerank/` — **not wired to production display ranking**.

---

## Validation Result

```
OWNER-PREDICTIONS-UI-2 validation: 31/31 passed
Recommendation: OWNER_UI_TOP3_READY
```

Checks include: Top 3 public display, no guaranteed Top 1 label, Top 5 gating, shadow access rules, odds badge, no UI provider calls, DB unchanged, WDE/ECSE/lambda unchanged, timers disabled, frontend build success.

---

## Production Deploy Instructions

1. **Deploy backend** (API payload changes):
   ```bash
   cd /opt/worldcup-predictor
   git pull
   # restart API service (systemd unit — do NOT enable timers)
   sudo systemctl restart worldcup-predictor-api
   ```

2. **Build and deploy frontend**:
   ```bash
   cd base44-d
   npm ci
   npm run build
   # copy dist to nginx/static per existing deploy runbook
   ```

3. **Optional:** Ensure shadow artifacts exist on server for owner preview:
   ```bash
   python scripts/run_ecse_rerank_1_shadow_analysis.py  # read-only, writes artifacts only
   ```

4. **Verify:**
   ```bash
   python scripts/validate_owner_predictions_ui_2_end_result_display.py
   curl -s http://localhost:8000/api/research/ecse/fixtures/<fixture_id> | jq '.top_3,.top_5,.shadow_preview'
   ```

5. **Do NOT:**
   - Enable systemd timers
   - Promote ECSE re-rank to production ranking
   - Recalibrate lambda from knockout sample

---

## Explicit Non-Changes

- WDE 1X2 / BTTS / O/U logic — unchanged
- ECSE score distribution ranking — unchanged
- Lambda / Poisson training — unchanged
- Production DB writes from UI — none
- Public exposure of shadow internals — blocked

---
STOP — UI wording promoted (PROMOTE_UI_TOP3_ONLY). ECSE re-rank remains shadow-only.
