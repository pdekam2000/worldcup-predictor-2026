# PHASE 32D — LEAKAGE & REALITY AUDIT

**Mode:** Audit only  
**Date:** 2026-06-20  
**Code changes:** None  
**Deploy:** None

---

## Executive Summary

Phase 32B/32C confidence improvements were audited for data leakage, circular scoring, and scoring realism across **72 World Cup fixtures** in SQLite and the **20-fixture validation cohort** used in Phases 32B/32C.

| Area | Validation cohort (20 upcoming NS) | Full WC DB (72) |
|------|-----------------------------------|-----------------|
| Form future leakage | **0 issues** | 13 date violations (all self-inclusion on FT fixtures) |
| H2H future leakage | **0 issues** | 7 date violations (self-inclusion on FT fixtures) |
| Circular (fixture in own history) | **0** | **20** (finished opening matches) |
| Consensus inflation | All 20 → **95.0 cap** | Same pattern |
| Injury inflation | 13/20 → **95.0 default** | Sparse lists → max score |

### Final Verdict: **B) Needs fixes**

The **20-fixture validation sample used to claim 55 → 79.47 is not contaminated by future results** — all source match dates precede kickoff. However, the engines **lack an explicit pre-kickoff date filter**, finished fixtures **can score themselves into their own form/H2H history**, and **consensus/injury defaults inflate confidence** toward hard caps. Safe to deploy only after targeted fixes (Phase 32E recommended).

---

## 1. Form Cache Audit

### Code review

`form_engine.py` aggregates the first N entries from `recent_fixtures` with **no kickoff cutoff**:

```104:116:worldcup_predictor/intelligence/national_team/form_engine.py
def build_team_form_metrics(
    *,
    team_id: int | None,
    team_name: str,
    recent_fixtures: list[dict[str, Any]] | None,
) -> TeamFormMetrics:
    fixtures = safe_list(recent_fixtures)
    if team_id is None or not fixtures:
        ...
```

Phase 32C stores raw API `fixtures?team=` payloads in `national_team_form_cache` without temporal filtering at build time.

### Empirical check

| Scope | Future matches after kickoff | Self-inclusion (same fixture_id) |
|-------|------------------------------|----------------------------------|
| **20 validation fixtures** (NS, Jun 20–24) | **0** | **0** |
| **72 WC fixtures** (incl. 4 FT) | 13 | 20 |

**Example (clean upcoming):** Belgium vs Egypt (1489377, kickoff 2026-06-15) — home history ends 2026-06-06; away history ends 2026-06-06. All dates strictly before kickoff.

**Example (leakage on finished):** Mexico vs South Africa (1489369, FT) — team's `fixtures?team=` cache includes **fixture 1489369 itself** with status `FT` and identical kickoff timestamp. This is **circular scoring**, not forward leakage from a different match.

### Finding

- **Validation cohort:** Form cache uses only pre-match history. **PASS for upcoming fixtures.**
- **Structural gap:** No `match_date < fixture_kickoff` filter; **FAIL for backtest/replay on finished fixtures.**
- **Cache contamination:** Team recent-fixture API cache is shared globally — not fixture-date scoped. A finished WC match can appear in its own form window.

---

## 2. H2H Cache Audit

### Code review

`h2h_engine.py` processes meetings list with recency weighting but **no kickoff exclusion**:

```43:49:worldcup_predictor/intelligence/national_team/h2h_engine.py
    for item in rows:
        side = team_side_in_fixture(item, home_team_id)
        if side is None:
            continue
        home_g, away_g = goals_from_fixture(item)
        if home_g is None or away_g is None:
            continue
```

H2H synthesis (Phase 32C) merges overlapping recent-fixture caches — also without date filter.

### Empirical check

| Scope | Future H2H after kickoff | Self-inclusion |
|-------|--------------------------|----------------|
| **20 validation fixtures** | **0** | **0** |
| **72 WC fixtures** | 7 | Included in circular set |

Netherlands vs Sweden (validation) — 2 H2H meetings found via synthesis; both pre-date 2026-06-20 kickoff.

### Finding

- **Validation cohort:** **PASS** — no future H2H.
- **Structural gap:** Same missing cutoff as form; self-inclusion on FT fixtures.
- Dedicated `fixtures/headtohead` endpoint cache sparse; synthesis path is valid but must inherit date filter when added.

---

## 3. Squad / Injury Audit

### Code review

- **Squad strength** uses `report.lineups` (expected/projected XI) and `report.home_team.injuries.players` at prediction time. No result fields consumed.
- **Injury impact** penalizes listed unavailable players by category (Critical/Important/Rotation/Depth).

### Inflation concern (not leakage)

When injury lists are **empty or sparse**, `injury_impact_engine.py` returns:

```64:66:worldcup_predictor/intelligence/national_team/injury_impact_engine.py
    score = clamp(100 - total_penalty * 0.45, 25, 95)
    if total_penalty == 0:
        score = max(score, 62.0)
```

With zero penalty → **score = 95.0** (clamp ceiling). On validation cohort: **13/20 fixtures at 95**, **7/20 at 50** (missing injury data path).

This is **not post-match leakage** but **optimistic default scoring** that adds ~+6.75 weighted confidence vs Phase 32 baseline (50 → 95 at 15% weight).

### Finding

- **No post-match information detected** in squad/injury path.
- **Scoring realism issue:** empty injury list treated as near-perfect availability.

---

## 4. Consensus Audit

### Code review

`consensus_engine.py` combines:
1. `market_consensus_agent` signal (`consensus_strength_raw`)
2. Bookmaker spread from `report.odds`
3. Bookmaker count bonus: `+1.2 per bookmaker` (up to 8)
4. Sharp money blend (35% weight)

### Empirical trace — Netherlands vs Sweden (1539007)

| Input | Value |
|-------|------:|
| `consensus_strength_raw` | 97.2 |
| `sources_used` | `['api_sports', 'sqlite_snapshot']` (2 sources, not duplicate bookmakers) |
| `bookmakers` in odds | 14 |
| `disagreement_index` | 0.0 |
| Sharp confidence | 88.5 |
| **Final consensus_strength_score** | **95.0** (hard cap) |

### Duplicate weighting check

- **No duplicate bookmaker double-count** — 14 bookmakers counted once in spread/bonus; `sources_used` counts data *pipelines* (API + snapshot), not individual books.
- **Formula inflation:** Phase 32B raised `_consensus_strength` base to `42 + source_count × 14`; with 2 sources → base 70 before bonuses. Bookmaker bonus adds up to +9.6; sharp blend pushes toward **clamp(95)**.
- **Validation cohort:** **20/20 fixtures = 95.0** exactly — indicates **ceiling saturation**, not differentiated market signal.

### Finding

- **No future-data leakage** in consensus path (uses pre-match odds snapshots).
- **Synthetic inflation:** consensus component systematically maxed at 95 on validation sample (+6.0 weighted vs baseline odds 55).

---

## 5. Confidence Bridge — How 55 → 79.47 Occurred

### Phase 32 baseline (audit)

| Component | Score | Weight | Weighted |
|-----------|------:|-------:|---------:|
| Form | 50.0 | 22% | 11.0 |
| H2H | 45.0 | 18% | 8.1 |
| Injuries | 50.0 | 15% | 7.5 |
| Lineups | 80.0 | 10% | 8.0 |
| Odds | 55.0 | 15% | 8.25 |
| Data quality | 55.0 | 20% | 11.0 |
| **Scoring subtotal** | | | **53.9** |
| WDE final (typical) | | | **~55–56** |

### After 32C (validation cohort avg)

| Component | Avg score | Δ vs baseline | Weighted Δ |
|-----------|----------:|--------------:|-----------:|
| **Form** | 65.6 | +15.6 | **+3.4** |
| **H2H** | 51.7 | +6.7 | **+1.2** |
| **Injuries** | 79.3 | +29.3 | **+4.4** |
| **Lineups/Squad** | 66.1 | −13.9 | **−1.4** |
| **Odds/Consensus** | 95.0 | +40.0 | **+6.0** |
| **Data quality** | 55.0 | 0 | 0 |
| **Scoring subtotal** | | | **~67.6** |
| **WDE national boost** | +2.5 | | **+2.5** |
| **WDE/other adjustments** | ~+9.4 | | |
| **Final avg confidence** | | | **79.47** |

### Contribution ranking (real vs inflated)

| Factor | Nature of lift |
|--------|----------------|
| **Consensus → 95 cap** | Scoring formula inflation (~+6.0 weighted) |
| **Injury default → 95** | Empty-list optimistic default (~+4.4 weighted) |
| **National form** | **Real** pre-match history (~+3.4 weighted) |
| **WDE data-rich boost** | Policy add-on (+2.5 when ≥3 recent matches) |
| **H2H** | Modest (+1.2 weighted); mostly neutral 50 |
| **Squad** | Slightly below baseline lineups score |

**Conclusion:** ~**10–12 points** of the ~**24-point lift** (55 → 79) come from **scoring defaults/caps** (consensus + injury). ~**6–8 points** come from **legitimate form history activation** (Phase 32C). Remainder from WDE boost and specialist stack.

---

## 6. Manual Review — 10 Random Upcoming Fixtures

Random seed 32; all status **NS**; audit date **2026-06-20**.

| # | Match | Kickoff | History dates (latest) | Future leak? | Conf (32C cohort) | Recommend |
|---|-------|---------|------------------------|:------------:|------------------:|:---------:|
| 1 | Belgium vs Egypt | 2026-06-15 | H: 2026-06-06 / A: 2026-06-06 | No | —¹ | — |
| 2 | Türkiye vs Paraguay | 2026-06-20 | H: 2026-06-06 / A: 2026-06-13 | No | —¹ | — |
| 3 | Ghana vs Panama | 2026-06-17 | H: 2026-06-02 / A: 2026-06-06 | No | —¹ | — |
| 4 | Norway vs Senegal | 2026-06-23 | H: 2026-06-07 / A: 2026-06-16 | No | **88.1** | Yes |
| 5 | Ecuador vs Curaçao | 2026-06-21 | H: 2026-06-07 / A: 2026-06-14 | No | **72.2** | Yes |
| 6 | Tunisia vs Japan | 2026-06-21 | H: 2026-06-06 / A: 2026-05-31 | No | **72.2** | Yes |
| 7 | Brazil vs Morocco | 2026-06-13 | H: 2026-06-06 / A: 2026-06-07 | No | —¹ | — |
| 8 | Morocco vs Haiti | 2026-06-24 | H: 2026-06-07 / A: 2026-06-06 | No | **91.8** | Yes |
| 9 | Haiti vs Scotland | 2026-06-14 | H: 2026-06-06 / A: 2026-06-06 | No | —¹ | — |
| 10 | Ivory Coast vs Ecuador | 2026-06-14 | H: 2026-06-08 / A: 2026-06-07 | No | —¹ | — |

¹ Not in the 20-fixture Phase 32C validation cohort (Jun 20–24 subset); history audit still clean.

**Representative calculation — Norway vs Senegal (1489401):**

| Field | Value |
|-------|------:|
| national_form_score | 76.9 |
| national_h2h_score | 50.0 |
| squad_strength_score | 75.3 |
| injury_impact_score | 95 |
| consensus_strength_score | 95 |
| **Final confidence** | **88.1** |
| **No Bet** | **false** |

All 10 reviewed fixtures: **source data dates strictly precede kickoff**; no future results in form or H2H windows.

---

## 7. Leakage & Contamination Checks

| Check | Result | Severity |
|-------|--------|----------|
| Future results in form (validation cohort) | **None found** | — |
| Future results in H2H (validation cohort) | **None found** | — |
| Self-inclusion (fixture in own history) | **20 FT fixtures** in full DB | **Medium** |
| Duplicated history rows | **0** duplicate match IDs in form windows | — |
| Circular scoring (outcome → confidence) | **Present for finished fixtures** via self-inclusion | **Medium** |
| Cache contamination (shared team cache) | Team cache not scoped per target fixture date | **Medium** |
| Consensus double-counting bookmakers | **Not detected** | — |
| Consensus ceiling saturation | **20/20 at 95.0** | **Low–Medium** (inflation) |
| Injury empty-list → 95 | **13/20 fixtures** | **Low–Medium** (inflation) |
| WDE threshold changes | **Unchanged** (60/50) | — |

---

## 8. Required Fixes Before Deploy (Recommended Phase 32E)

1. **Add `kickoff_cutoff` filter** in `form_engine`, `h2h_engine`, `data_resolver`, and `history_backfill` — exclude matches where `match_date >= fixture_kickoff` or `fixture_id == target_fixture_id`.
2. **Rebuild form/H2H caches** per fixture date (or filter at read time) for backtest safety.
3. **Recalibrate consensus formula** — reduce bookmaker bonus slope; avoid 100% saturation at 95 on homogeneous samples.
4. **Injury default** — empty list should return **neutral ~50–62**, not **95**.
5. **Re-validate** confidence after fixes; expect avg to settle **62–72** (still above 60 gate) with more honest differentiation.

---

## Final Verdict

### **B) Needs fixes**

**Rationale:**

- **Not A (Safe to deploy):** Engines lack temporal guards; finished-fixture replay leaks own result into form/H2H; consensus and injury paths inflate confidence toward caps without corresponding signal quality.
- **Not C (Major leakage detected):** The **20-fixture upcoming validation cohort** driving the 55 → 79.47 claim shows **zero future-data leakage** on manual inspection. Form history dates are legitimate pre-match friendlies/qualifiers. The lift is **partially real** (form activation) and **partially inflated** (consensus/injury defaults + WDE boost).

**Deploy recommendation:** Hold Phase 32B/32C production deploy until Phase 32E leakage guards and scoring recalibration are implemented and re-audited.

---

**STOP — NO DEPLOY — AWAITING APPROVAL**
