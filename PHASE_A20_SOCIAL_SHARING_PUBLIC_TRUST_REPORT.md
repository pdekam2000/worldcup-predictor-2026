# PHASE A20 — Social Sharing, Public Trust & Viral Growth

**Date:** 2026-06-25  
**Environment:** Production `https://footballpredictor.it.com`

---

## Final Status

**`SOCIAL_TRUST_DEPLOYED_OK`**

---

## Summary

Phase A20 adds shareable public pages for AI picks, combos, and opt-in paper betting reports, plus a public accuracy trust page. All shared content is sanitized (no user IDs, emails, or owner/debug fields). Trust metrics come from real archive evaluations only — no fabricated stats.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend                                                    │
│  ShareButton → POST /api/share/* (auth)                     │
│  /share/pick/:id  /share/combo/:id  /share/paper-report/:id │
│  /public/accuracy                                           │
│  PageMeta (OG tags) · TrustWidgets                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  worldcup_predictor/social_trust/                           │
│  sanitize.py   strip private/owner fields                     │
│  store.py      social_share_links (SQLite)                    │
│  trust_stats.py  30-day accuracy from evaluations             │
│  service.py    create/get shares + OG metadata                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Read-only: worldcup_prediction_evaluations, Bet Quality      │
└─────────────────────────────────────────────────────────────┘
```

---

## Files Changed / Added

### Backend

| Path | Role |
|------|------|
| `worldcup_predictor/social_trust/` | Module (constants, sanitize, store, trust_stats, service) |
| `worldcup_predictor/api/routes/social_trust.py` | REST APIs + OG HTML endpoint |
| `worldcup_predictor/database/migrations.py` | `PHASE_A20_DDL` — `social_share_links` |
| `worldcup_predictor/api/main.py` | Router registration |

### Frontend

| Path | Role |
|------|------|
| `base44-d/src/api/socialTrustApi.js` | API client |
| `base44-d/src/components/social/ShareButton.jsx` | Share / copy link |
| `base44-d/src/components/social/PageMeta.jsx` | OpenGraph meta tags |
| `base44-d/src/components/social/TrustWidgets.jsx` | 30d accuracy, evaluated count, best market |
| `base44-d/src/pages/share/*` | Public share + accuracy pages |
| `ComboTipsPage`, `BettingPlanPage`, `PaperBettingPage`, `MatchDetailPage`, `AccuracyCenter` | Share buttons |

### Scripts

| Path | Role |
|------|------|
| `scripts/validate_phase_a20_social_trust.py` | 29-check validation |
| `scripts/deploy_phase_a20_quick.sh` | Deploy |
| `scripts/deploy_phase_a20_smoke.sh` | HTTP smoke |

---

## APIs

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/share/pick` | User |
| POST | `/api/share/combo` | User |
| POST | `/api/share/betting-plan` | User |
| POST | `/api/share/paper-report` | User (opt-in required) |
| GET | `/api/share/pick/{id}` | Public |
| GET | `/api/share/combo/{id}` | Public |
| GET | `/api/share/plan/{id}` | Public |
| GET | `/api/share/paper-report/{id}` | Public |
| GET | `/api/public/accuracy` | Public |
| GET | `/api/share/og/{id}` | Public (crawler OG HTML) |

---

## Privacy

- `sanitize.py` blocks `user_id`, `email`, `snapshot_id`, owner/debug fields
- Public `get_share()` never returns `user_id`
- Paper report share requires `opt_in: true` + confirm dialog
- Paper payloads are anonymized portfolio stats only
- Trust stats require ≥5 settled 1X2 picks in 30 days before showing accuracy %

---

## OpenGraph

Each share includes `og:title`, `og:description`, `og:image` via:
- API response `og` object
- `PageMeta` component on share pages
- `/api/share/og/{id}` HTML for crawlers

---

## Share Buttons

| Location | Share type |
|----------|------------|
| Match detail | Pick |
| Combo Tips | Combo |
| AI Betting Plan | Plan |
| Paper Betting monthly report | Paper report (opt-in) |
| Accuracy Center | Link to `/public/accuracy` + trust widgets |

---

## Validation Result

| Environment | Result |
|-------------|--------|
| Local | **29/29 PASS** |
| Production | **29/29 PASS** |

---

## Deploy Result

```
share_pick=200
share_combo=200
public_accuracy=200
api_accuracy=200
betting_plan=200
combo=200
SMOKE_OK
DEPLOY_OK
```

---

## Rollback Plan

1. Revert frontend dist from backup
2. Revert `worldcup_predictor/social_trust/` and API route
3. `social_share_links` table is additive — no drop required
4. Restart `worldcup-api`

---

## Safety

- No WDE / EGIE / model / calibration / billing changes
- No fake accuracy numbers
- Educational disclaimer on all public share pages
