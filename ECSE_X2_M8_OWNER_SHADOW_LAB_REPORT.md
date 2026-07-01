# PHASE ECSE-X2-M8 — Owner-Only ECSE Shadow Lab Report

**Date:** 2026-06-27  
**Mode:** Owner-only internal lab — no public launch — no prediction engine change  
**Prior phase:** ECSE-X2-M7 `READY_FOR_ADMIN_UI_REVIEW`

---

## Summary

Built an owner-only **ECSE Shadow Lab** at `/owner/ecse-shadow-lab` for personal analysis of baseline vs enhanced exact-score shortlists. Public prediction output, ECSE baseline table, WDE, EGIE, and subscription logic remain unchanged. All data is read from real M6/M7 shadow artifacts.

**Final recommendation:** `OWNER_LAB_READY`

---

## Files changed

| Area | File |
|------|------|
| Backend service | `worldcup_predictor/research/ecse_x2_m8/lab_service.py` |
| Backend module | `worldcup_predictor/research/ecse_x2_m8/__init__.py` |
| Owner API routes | `worldcup_predictor/api/routes/owner_ecse_shadow_lab.py` |
| API wiring | `worldcup_predictor/api/main.py` |
| Owner page | `base44-d/src/pages/owner/OwnerEcseShadowLab.jsx` |
| API client | `base44-d/src/api/saasApi.js` |
| Route registration | `base44-d/src/App.jsx` |
| Owner navigation | `base44-d/src/lib/ownerNavConfig.js` |
| Validation | `scripts/validate_ecse_x2_m8_owner_shadow_lab.py` |
| Report | `ECSE_X2_M8_OWNER_SHADOW_LAB_REPORT.md` |

---

## Owner route

- **Path:** `/owner/ecse-shadow-lab`
- **Guard:** `OwnerRoute` → `isOwnerUser` (role `owner` only)
- **Warning banner:** “Owner research lab only. Not public. Does not change live predictions.”
- **Nav:** Owner Command → ECSE Shadow Lab

---

## API endpoints

### Owner (primary UI)

| Method | Endpoint | Auth |
|--------|----------|------|
| GET | `/api/owner/ecse-shadow-lab/summary` | `require_owner_user` |
| GET | `/api/owner/ecse-shadow-lab/fixtures` | `require_owner_user` |
| GET | `/api/owner/ecse-shadow-lab/fixtures/{fixture_id}` | `require_owner_user` |

Query params on fixtures: `filter`, `league`, `date_from`, `date_to`, `limit`, `offset`.

### Admin (unchanged, still available)

| Method | Endpoint | Auth |
|--------|----------|------|
| GET | `/api/admin/ecse-x2/shadow-live-shortlists` | `require_super_admin_user` |
| GET | `/api/admin/ecse-x2/shadow-live-shortlists-summary` | `require_super_admin_user` |
| GET | `/api/admin/ecse-x2/shadow-live-shortlists/{fixture_id}` | `require_super_admin_user` |

### Owner-friendly computed fields (M8 lab service)

- `enhanced_better`, `enhanced_worse`, `unchanged`
- `baseline_hit_rank`, `enhanced_hit_rank`, `delta_rank`
- `owner_note`, `segment_summary`, `rank_movement_summary`
- `fixture_label` (from fixtures / ECSE snapshots when available)

---

## Access control

| Actor | Owner API | Owner page |
|-------|-----------|------------|
| Logged out | 401 | Redirect to `/owner-login` |
| free_user / pro | 403 (`is_owner` false) | Access denied |
| super_admin (non-owner) | 403 | Access denied |
| owner | 200 | Allowed |
| Admin shadow API (super_admin) | — | 200 (separate admin endpoints) |

---

## Summary card values (live artifacts)

| Card | Value |
|------|-------|
| Total shadow rows | 108 |
| Enhancer applied | 24 |
| Excluded | 84 |
| Missing ft_home odds | 75 |
| Balanced excluded | 3 |
| Strong home (≥60%) | 20 |
| Pending evaluations (row status) | 108 |
| Completed evaluations (eval artifact) | 21 |
| **Public output changed** | **0** |

### Evaluation hit rates (21 completed)

| Metric | Baseline | Enhanced | Δ pp |
|--------|----------|----------|------|
| Top-1 | 9.52% | 14.29% | +4.76 |
| Top-3 | 19.05% | 19.05% | 0.00 |
| Top-5 | 33.33% | 28.57% | −4.76 |
| Top-10 | 57.14% | 57.14% | 0.00 |

---

## Sample fixture comparison

### Evaluated — no rank change (fixture 223087)

- **Baseline Top-1:** 1-1 → **Enhanced Top-1:** 1-1  
- **Actual:** 1-1  
- **Baseline hit rank:** 1 | **Enhanced hit rank:** 1  
- **Owner note:** “No useful rank change”

### Enhanced better (fixture 223142, Torneo Federal A)

- **Home prob:** 63.7% (strong home favorite)  
- **Baseline Top-1:** 1-0 → **Enhanced Top-1:** 1-1  
- Reordering inside Top-10 pool; owner note reflects pending or evaluated rank delta when result available.

### Enhanced worse (fixture 223090, Serie D)

- **Home prob:** 82.0%  
- **Baseline Top-1:** 1-1 → **Enhanced Top-1:** 2-1  
- Useful for owner decision: enhancer moved favorite scoreline when home was very strong.

### Skipped — missing odds

- 75 fixtures excluded with `missing_ft_home`  
- UI label: “Skipped: missing odds”

### Skipped — balanced match

- 3 fixtures excluded with `balanced_match`  
- UI label: “Skipped: balanced match”

---

## Public output unchanged proof

- All 108 shadow rows: `public_output_changed: false`
- M7 before/after public snapshots: 8/8 fixtures unchanged
- `predictions.py` has no M8 or `enhanced_top10` references
- ECSE baseline table row count unchanged (verified in validation)

---

## Validation results

Run: `python scripts/validate_ecse_x2_m8_owner_shadow_lab.py`

| Area | Result |
|------|--------|
| Owner route + page + nav + API helpers | PASS |
| RBAC: free/pro blocked, owner allowed | PASS |
| Owner API auth integration | PASS |
| Real shadow artifact data (no demo rows) | PASS |
| Summary counts match artifacts | PASS |
| Filters + detail Top-10 panels | PASS |
| ECSE baseline / billing / WDE unchanged | PASS |
| Frontend `npm run build` | PASS |
| Report present | PASS |

---

## Production enablement (manual only — not auto-enabled)

Do **not** enable on production unless explicitly approved.

Append to `/opt/worldcup-predictor/.env.production`:

```env
ECSE_X2_M6_SHADOW_LIVE_ENABLED=1
ECSE_LIVE_ENABLED=1
```

Then:

```bash
sudo systemctl restart worldcup-api
```

Owner lab UI is available at `/owner/ecse-shadow-lab` once deployed frontend + backend are live. Shadow collection requires the flags above.

---

## Owner-use notes

- 21 evaluations is enough for initial lab review but sample is small; Top-1 delta (+4.76pp) is promising, Top-5 slightly worse on this slice.
- 75/108 rows skipped for missing `ft_home` odds — personal decisions should weight “applied only” (24 fixtures) more heavily.
- Strong home segment (20 rows) is the primary enhancer target per M5/M6 design.
- Lab is research-only; owner notes include “Use only as research signal, not final betting advice” for pending fixtures.

---

## Final recommendation

**`OWNER_LAB_READY`**

Owner-only ECSE Shadow Lab is implemented with real shadow data, correct access control, summary cards, filters, fixture table, side-by-side Top-10 detail, and owner insight notes. Public predictions and production systems are unchanged. Production shadow flags remain manual opt-in.
