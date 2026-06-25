# PHASE 43 — PRIORITY MATRIX

**Project:** World Cup Predictor  
**Audit date:** 2026-06-21  
**Companion document:** [PHASE_43_FULL_PROJECT_AUDIT.md](./PHASE_43_FULL_PROJECT_AUDIT.md)

Priority scale: **P0** = do now · **P1** = next sprint · **P2** = backlog · **P3** = optional cleanup

Effort: **S** = hours · **M** = days · **L** = week+

---

## Priority Matrix

| # | Issue | Severity | Impact | Effort | Recommended Priority |
|---|-------|----------|--------|--------|----------------------|
| 1 | Silent `except Exception: pass` on pipeline enrichments (weather, xG, fusion, extended markets) | High | Predictions may ship incomplete; debugging impossible; user trust erosion if markets missing | S | **P0** |
| 2 | Triple prediction storage (JSONL + SQLite + PostgreSQL) without documented sync contract | High | History/accuracy inconsistencies; duplicate or missing rows across views | L | **P0** |
| 3 | Global archive loads all stored predictions then slices in memory | High | `/api/history?scope=global` slows as archive grows; API timeouts under load | S | **P0** |
| 4 | Public contact form (`/contact`) does not send messages — UI-only fake success | High | Legal/trust violation; users believe message was delivered | M | **P1** |
| 5 | Favorites add flow not wired (`addFavorite` unused) | High | Broken core retention feature; users cannot save matches | S | **P1** |
| 6 | Production evaluated sample size = 2 (metrics unreliable) | High | Performance Center/Best Tips weak trust signal until more matches finish | M | **P1** |
| 7 | Unauthenticated `GET /api/predict/{id}` exposes cached predictions | Medium | Free access to paid engine output when cache warm | M | **P1** |
| 8 | Duplicate history API surfaces (`/api/history` vs `/api/user/prediction-history` + `/results`) | Medium | Frontend/backend drift; maintenance cost; confused integrators | S | **P1** |
| 9 | `/api/accuracy/summary` vs `/api/performance/summary` overlap | Medium | Two accuracy stories; unused legacy client export | S | **P1** |
| 10 | Production deploy validation fails on missing frontend source tree | Medium | Deploy scripts exit non-zero despite successful runtime smoke | S | **P1** |
| 11 | Legacy billing checkout routes unauthenticated | Medium | Information disclosure (checkout readiness state) | S | **P2** |
| 12 | `rebuild_accuracy_summary` on cold performance summary request | Medium | Latency spike on first `/api/performance/summary` hit after deploy | S | **P2** |
| 13 | ApiSettings page is stub ("sync coming later") | Medium | Admin confusion; appears broken in production | S | **P2** |
| 14 | `/pricing` route orphaned from navigation | Low | SEO/UX gap; users may not find standalone pricing page | S | **P2** |
| 15 | Deploy pack folders (`_pack_phase*`, `deploy_staging_*`) in repo root | Medium | Stale code mirrors; wrong-file edits; repo bloat | M | **P2** |
| 16 | Desktop GUI subtree (`worldcup_predictor/ui/`) unused by SaaS | Low | ~80 files of dead weight; confuses new contributors | M | **P2** |
| 17 | 7 unused `saasApi.js` exports | Low | Dead code; misleading API surface for frontend devs | S | **P3** |
| 18 | ~30 unused shadcn UI components | Low | Bundle/maintenance noise | M | **P3** |
| 19 | Premium archive placeholders ("coming soon") visible in detail | Low | Sets expectation for unfinished premium tier | M | **P3** |
| 20 | Inconsistent HTTPException detail shapes (string vs dict) | Low | Harder client error handling | M | **P3** |
| 21 | OpenAPI `/docs` may be exposed in production | Medium | Attack surface / schema disclosure if nginx not blocking | S | **P1** |
| 22 | PG `user_prediction_history.result` vs SQLite evaluation status drift | High | Wrong green/red badge for some merged history rows | M | **P0** |
| 23 | Broad `except Exception` in `public_accuracy_summary.py` / admin routes | Medium | Silent accuracy dashboard failures | S | **P2** |
| 24 | Best Tips empty when no upcoming fixtures (current prod state) | Low | Honest empty state — not a bug; improve copy | S | **P3** |
| 25 | Duplicate resend-verification auth routes | Low | Harmless redundancy | S | **P3** |
| 26 | Legacy GUI SQLite auth (`access/repository.py`) parallel to JWT | Low | Confusion only if accidentally wired to API | M | **P3** |
| 27 | Missing email notification digests for results | Medium | Retention/commercial gap | L | **P2** |
| 28 | No integration test for history merge dedupe + global detail | Medium | Regressions in 42D trust feature undetected | M | **P1** |
| 29 | Lambda bridge calibration docstring says "Temporary" | Low | Shadow-only; clarify production non-impact | S | **P3** |
| 30 | Contact admin (in-app) works but public contact does not | High | Inconsistent support channels | M | **P1** |

---

## Severity × Effort Quadrant

```
                    LOW EFFORT (S)          HIGH EFFORT (M/L)
                 ┌─────────────────────┬─────────────────────┐
    HIGH         │ P0: #1 #3 #22       │ P0: #2              │
    SEVERITY     │ P1: #4 #5 #8 #9 #10 │ P1: #6 #28          │
                 │ P1: #21 #30         │                     │
                 ├─────────────────────┼─────────────────────┤
    MEDIUM       │ P2: #11 #12 #13 #23 │ P2: #15 #27         │
                 │                     │ P2: #16             │
                 ├─────────────────────┼─────────────────────┤
    LOW          │ P3: #14 #17 #24 #25 │ P3: #18 #19 #26 #29 │
                 └─────────────────────┴─────────────────────┘
```

---

## Recommended Sprint Order

### Sprint A — Trust & integrity (P0)

1. Log enrichment failures + surface `enrichment_degraded` in prediction metadata (#1)
2. SQL-level pagination for global archive (#3)
3. Audit PG vs SQLite evaluation sync for history badges (#22)
4. Write architecture doc for prediction storage contract (#2 — start)

### Sprint B — User-facing gaps (P1)

5. Wire contact form to email backend (#4, #30)
6. Wire favorites add in Match Center (#5)
7. Add integration tests for 42D history merge (#28)
8. Verify/block OpenAPI in production nginx (#21)
9. Fix deploy validation for prod (smoke-only mode) (#10)

### Sprint C — Cleanup & scale (P2)

10. Deprecate duplicate history/accuracy endpoints (#8, #9)
11. Cache performance summary (#12)
12. Quarantine deploy pack folders (#15)
13. Hide or implement ApiSettings (#13)

---

## Quick Reference: Production Feature Status

| Feature | Production | Risk if unfixed |
|---------|------------|-----------------|
| Login / Register / Password | Active | — |
| Predict pipeline + WDE | Active | #1 enrichment silence |
| Global archive + Performance | Active | #3 scale, #22 sync |
| Best Tips | Active (empty OK) | #6 sample size |
| Stripe billing | Active | — |
| Admin + gates | Active | #21 docs exposure |
| Weather intelligence | Active | #1 if weather fails silently |
| Favorites | Partial | #5 |
| Public contact | Broken | #4 |

---

*Read-only audit — no implementation performed.*
