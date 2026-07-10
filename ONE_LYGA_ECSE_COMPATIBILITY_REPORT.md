# 1 Lyga — ECSE Compatibility Report

**Generated:** 2026-07-10 20:35 CEST  
**Mode:** Controlled compatibility validation — no formula changes

---

## Controlled fixture

| Field | Value |
|-------|-------|
| fixture_id | 1556381 |
| Match | Minija vs Jonava |
| competition_key | `one_lyga` |
| tier | B |

---

## Compatibility checks

| Component | Status | Notes |
|-----------|--------|-------|
| ECSE fixture resolution | ✅ | Same Tier B MCP / `run_daily_ecse` path as Phase 6C |
| lambda/input path | ⏸ | Requires odds + DB fixture row — gated |
| Top10 generation | ⏸ | Deferred until odds-qualified |
| Top1–Top5 extraction | ⏸ | Deferred until odds-qualified |
| rank probability storage | ✅ | `exact_score_rankings` schema ready |
| Top3 / Top5 Mass | ⏸ | Deferred |
| entropy (authentic-only) | ✅ | Policy unchanged — unavailable when not computed |
| snapshot freeze | ✅ | `freeze_tier_b_shadow_prediction` path exists |
| actual score rank eval | ✅ | Ranks 1–5 + OUTSIDE_TOP5 supported |

---

## ECSE execution on control fixture

**Skipped** — `ODDS_MISSING` under existing `classify_candidate` gate.

No ECSE formula invocation without authentic odds (per audit constraints).

---

## Verdict

**ECSE_SUPPORTED** at pipeline/registry layer.  
Execution on control fixture correctly blocked by unchanged odds policy.

When odds-qualified, expect same Top1–Top5 + mass fields as Allsvenskan Tier B shadow jobs (2026-07-12 reference).
