# Phase 23B — Trace Promotion Design

**Mode:** Design only — no code, no WDE weight changes, no deploy, no calibration  
**Project:** WorldCup Predictor 2026  
**Date:** 2026-06-17  
**Inputs:** Phase 23 Master Decision Audit; Phase 22C–22F implementations  
**Constraint:** All promotions must preserve the **nine-factor weight table** until a separate calibration approval. Promotion = **how signals enter existing factors and threshold layers**, not new weight allocation.

---

## Executive Summary

| Agent | Verdict | Recommended path |
|-------|---------|------------------|
| `expected_lineup_agent` | **Partial promotion → full** | **Option B** — enhance `lineup_strength` + confidence gates |
| `tournament_context_agent` | **Partial promotion** | **Option B** — enhance `motivation_psychology`; minor `tactics_matchup` O/U nudge |
| `xg_intelligence_agent` | **Partial promotion (gated)** | **Option B** — enhance `tactics_matchup` when `plan_support=full` |
| `sportmonks_prediction_agent` | **Partial promotion (never direct winner)** | **Option C + threshold** — Fusion/confidence/audit only; **no 1X2 selection override** |

**Core pattern:** *Promotion Adapter Layer* sits between specialist signals and WDE `_build_factors()` — computes **bounded deltas** to factor **scores/edges** and **confidence caps**, never new factor names or weight sums.

---

## 1. Promotion Architecture

### 1.1 Design principles

1. **Weight preservation** — The 15/15/12/12/12/10/10/8/6 table stays fixed through Phase 24A–24C.
2. **Gate before apply** — Every promotion requires `data_quality`, agent `status`, and domain-specific gates (e.g. `plan_support`, `confirmed_available`).
3. **Bounded influence** — Per-agent cap on factor score shift (±8 pts) and edge shift (±0.04) unless calibration approves higher.
4. **Shadow-first** — Each promotion ships in `shadow` mode (compute + log delta, no apply) before `gated` mode.
5. **Dedup authority** — When trace agent disagrees with WDE-connected agent (lineup_v2, motivation, xg_chance, market_consensus), **down-weight or defer**, never double-count.
6. **Audit trail** — Every applied delta recorded in `audit.trace.promotion_deltas[]` (design spec; not implemented in 23B).

### 1.2 Promotion modes (future feature flag)

| Mode | Behavior |
|------|----------|
| `off` | Current production (trace only) |
| `shadow` | Compute promotion deltas; append to shadow JSONL; prediction unchanged |
| `gated` | Apply deltas only when gates pass |
| `full` | Post-calibration; requires Phase 25 approval |

### 1.3 Per-agent verdict

#### `expected_lineup_agent` (22F)

| Question | Answer |
|----------|--------|
| Promote? | **Yes — partial first, full after 24C validation** |
| Keep trace? | **Yes** — JSONL accuracy history, overlap metrics always trace |
| Partial vs full | **Partial in 24A** (lineup factor + confidence only); **full in 24C** (+ injury cross-factor) |

**Rationale:** Highest late-stage marginal value; overlaps `lineup_intelligence_agent` — must merge, not duplicate.

---

#### `tournament_context_agent` (22E)

| Question | Answer |
|----------|--------|
| Promote? | **Yes — partial only** |
| Keep trace? | **Yes** — motivation comparison, disagreement benchmarks |
| Partial vs full | **Partial permanently likely** — `tournament_intelligence_agent` already in WDE; 22E adds scenario precision |

**Rationale:** Rich qualification math but high correlation with motivation + tournament_intelligence. Full replacement risky.

---

#### `xg_intelligence_agent` (22D)

| Question | Answer |
|----------|--------|
| Promote? | **Yes — gated partial** |
| Keep trace? | **Yes** — plan probe, disagreement vs xg_chance_quality |
| Partial vs full | **Partial until SM xG pre-match coverage ≥70% on WC sample** |

**Rationale:** Sportmonks xG often empty pre-match; promotion without gate would inject noise into `tactics_matchup`.

---

#### `sportmonks_prediction_agent` (22C)

| Question | Answer |
|----------|--------|
| Promote? | **Yes — partial (confidence/audit/disagreement only)** |
| Keep trace? | **Yes** — raw SM probs, recommendation enum |
| Partial vs full | **Never full direct winner promotion** (see §6) |

**Rationale:** External model must remain benchmark; direct 1X2 override breaks internal authority chain.

---

## 2. Integration Options (A / B / C)

### 2.1 `expected_lineup_agent`

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A** New factor `expected_lineup` | Add 10th WDE factor | Clean separation | **Violates weight constraint**; requires recalibration |
| **B** Enhance `lineup_strength` (+ `injuries_suspensions` secondary) | Blend expected + confirmed into same 12% slot | No weight change; kickoff-aware | Must dedupe vs lineup_v2 |
| **C** Fusion-only | Confidence adjust ±10 cap | Safest rollout | Misses 1X2 edge when official XI missing |

**Recommendation: Option B** (primary) + **Option C** (confidence companion in 24A).

---

### 2.2 `tournament_context_agent`

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A** New factor `tournament_context` | Dedicated 8–10% | Captures scenario math | Overlaps motivation; weight change |
| **B** Enhance `motivation_psychology` (+ minor tactics O/U) | must_win, draw_acceptability → edge | Fits existing 8% slot | Complex merge with tournament_intelligence |
| **C** Fusion-only | Context as confidence modifier | Low risk | Weak on matchday 3 1X2 flips |

**Recommendation: Option B** with **dedup rules** vs `motivation_psychology_agent` + `tournament_intelligence_agent`.

---

### 2.3 `xg_intelligence_agent`

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A** New factor `sportmonks_xg` | Separate xG authority | Clear audit | Weight change; triple xG stack |
| **B** Enhance `tactics_matchup` | SM xG nudges `tactics_score` and O/U lean | Uses existing 12% | Only when plan_support=full |
| **C** Fusion-only | xG confidence band | Safe | Minimal O/U impact |

**Recommendation: Option B (gated)** + keep trace for partial/none plan states.

---

### 2.4 `sportmonks_prediction_agent`

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A** New factor `sportmonks_consensus` | SM as 10% odds parallel | Simple mental model | Conflicts with odds 10%; weight change |
| **B** Enhance `odds_market_signal` | Blend SM implied into odds_score/edge | Single odds voice | Risk of double-count with market_consensus |
| **C** Fusion + confidence + audit thresholds | Disagreement penalties, no selection | **Preserves internal winner** | No direct edge when SM alone is right |

**Recommendation: Option C** primary; **Option B** only as *validation blend* (max 15% of odds_score) in 24C after shadow proves uplift.

---

## 3. ExpectedLineup Promotion Design

**Goal:** Influence predictions **without changing the 12% lineup weight** or adding factors.

### 3.1 Lineup factor enhancement (`lineup_strength` — 12%)

Introduce **composite lineup score** inside existing WDE path:

```
composite_lineup_score = w_off * lineup_v2_strength
                       + w_exp * expected_xi_quality
                       + w_conf * lineup_confidence_factor

Default weights (score blend, NOT WDE weights):
  w_off = 0.55  if official_lineup else 0.15
  w_exp = 0.35  if not official_lineup else 0.10
  w_conf = 0.10 always

composite capped to [25, 95]
```

**Edge enhancement:**

| Signal | Edge delta (home-relative) | Gate |
|--------|---------------------------|------|
| `goalkeeper_change_flag` | ±0.02 toward underdog side volatility | official or high-confidence expected |
| `rotation_risk = High` | −0.02 to favored side edge | group stage only |
| `player_overlap_pct ≥ 85` (confirmed) | +0.015 edge stability bonus | post-kickoff calibration trace |
| `lineup_supports_internal = false` | freeze edge delta (use v2 only) | disagreement ≥ threshold |

**Authority rule:** `lineup_intelligence_agent` remains primary when `official_lineup=true`. `expected_lineup_agent` **leads** when official=false and `hours_to_kickoff ≤ 4`.

### 3.2 Injury factor cross-influence (`injuries_suspensions` — 12%)

Do **not** duplicate injury counts. Use expected lineup **role gaps** as modifier:

| Signal | Effect on `inj_score` | Max shift |
|--------|----------------------|-----------|
| `missing_attackers ≥ 2` (one side) | −4 pts that side's implied strength via edge | −4 |
| `star_player_absence_score ≥ 40` | −3 pts composite inj_score | −3 |
| `missing_key_players` overlap with injury_v2 list | **no extra penalty** (dedup) | 0 |

Injury **edge** only adjusts when expected lineup reveals absences **not** in injury API (late news):

```
late_news_edge_penalty = min(0.03, 0.005 * late_unlisted_absences)
```

Gate: `late_news_risk ∈ {medium, high}`.

### 3.3 Confidence layer (no WDE weight change)

Apply to **existing threshold machinery** only:

| Condition | Confidence effect | Cap type |
|-----------|-------------------|----------|
| Official lineups both sides | +3 confidence (already partially via lineup edge) | boost |
| Expected only, `lineup_confidence ≥ 60` | no cap change | neutral |
| Expected only, `lineup_confidence < 45` | maintain first-goal cap 30; −2 confidence | reduction |
| `late_news_risk = high` | −4 confidence | reduction |
| `comparison_available` + overlap < 60% | record only in shadow; **no auto penalty until 24C** | trace |

**Explicit non-goals for 24A:** No auto no-bet from expected lineup alone.

---

## 4. TournamentContext Promotion Design

**Goal:** Enhance **motivation (8%)** and **tactics O/U (12%)** without new weights or replacing `tournament_intelligence_agent`.

### 4.1 Motivation enhancement (`motivation_psychology` — 8%)

**Merge function** (when `group_context_strength ≥ 36` and agent status ≠ unavailable):

```
mot_score_blended = 0.50 * mot_psych_score
                  + 0.30 * tour_intel_pressure
                  + 0.20 * context_motivation_avg

mot_edge_blended  = mot_edge_base
                  + context_edge_nudge
```

**Context edge nudges** (bounded ±0.025 total):

| Signal | Edge nudge |
|--------|------------|
| `must_win_flag` + home must-win | +0.015 home |
| `draw_acceptability` | −0.01 absolute edge (toward draw) |
| `elimination_risk_home - elimination_risk_away ≥ 20` | ±0.01 toward lower-risk side |
| `context_supports_internal = false` | halve all context nudges |

**Dedup:** If `tournament_intelligence_agent.risk_flags` contains `must_win_match`, apply **only 50%** of context must-win nudge.

### 4.2 Tactics enhancement (`tactics_matchup` — 12%)

Context affects **O/U lean only**, not 1X2 edge:

| Signal | `tactics_over` delta |
|--------|---------------------|
| `expected_aggression = high` | +0.04 |
| `expected_conservatism = high` | −0.04 |
| `rotation_risk = High` | +0.03 (volatile squads) |
| `tournament_importance = critical` | +0.02 |
| Knockout match (`match_context` ∉ group) | cap total context O/U delta at ±0.05 |

### 4.3 Odds interpretation (without changing odds 10% weight)

Context modulates **disagreement penalty sensitivity**, not odds_score:

| Condition | Effect |
|-----------|--------|
| `must_win_flag` + market favors draw implied > 28% | flag `audit.market_disagreement_warnings` context-scenario note |
| `draw_acceptability` + model lean ≠ draw | reduce odds disagreement confidence penalty from −5 to −3 |
| Final group matchday 3 | increase conflict penalty weight by +1 (not +weight factor) |

**No direct change** to `odds_edge` from context in 24B — avoids triple motivation/odds coupling.

---

## 5. xG Intelligence Promotion Design

**Goal:** Enhance **tactics (12%)** and O/U/BTTS calibration paths without new weights.

### 5.1 Gating (mandatory)

Promotion adapter **inactive** unless:

```
plan_support == "full"
AND xg_confidence >= 50
AND comparison_available == true
AND disagreement_score <= 0.35
```

If `plan_support == "partial"` → trace only. If `plan_support == "none"` → trace only.

### 5.2 Tactics enhancement (`tactics_matchup` — 12%)

When gated active:

```
sm_xg_total = home_xg + away_xg  (Sportmonks)
internal_pressure = goals_pressure_score from xg_chance_quality

tactics_score_adjust = clamp(
    0.6 * (sm_xg_total - 2.5) * 10 + 0.4 * (internal_pressure - 50) * 0.1,
    -6, +6
)
tactics_score_final = avg(existing_tactics_score, tactics_score + adjust)
```

**Edge:** `xg_difference` (home − away) → home edge nudge `±0.015` max when `|xg_difference| ≥ 0.5`.

**Dedup:** If `xg_supports_internal = false`, **do not apply** SM xG adjust (trace disagreement only).

### 5.3 O/U calibration (within existing `_resolve_over_under`)

Design hook — **bounded blend** of total-goals hint:

```
total_goals_hint += clamp((sm_xg_total - baseline_total) * 0.25, -0.15, +0.15)
```

Only when gated; feeds ScoringEngine/WDE O/U path already using tactics_over accumulation.

### 5.4 BTTS calibration (extended markets path)

BTTS is **not** a WDE factor today. Design for `attach_extended_markets_to_prediction`:

| SM xG home & away both ≥ 1.0 | BTTS probability +5% relative (cap +8%) |
| SM xG total ≤ 1.8 | BTTS probability −5% relative |
| Gate failed | no change |

**Phase 24C** implements BTTS hook; **24B** trace-only BTTS delta in shadow.

---

## 6. Sportmonks Prediction Promotion Design

### 6.1 Should it ever influence winner prediction directly?

**Answer: No — not in Phase 24A–24C or until explicit governance approval.**

Sportmonks prediction must **not**:

- Override `_resolve_1x2()` selection
- Replace `baseline.one_x_two.selection`
- Become primary `odds_edge` source (>50% of odds factor)

Sportmonks prediction **may**:

- Reduce/increase **confidence** when `disagreement_vs_internal` is high
- Add **audit limitations** and structured disagreement records
- Influence **Fusion** confidence band (Option C)
- Trigger **human-review flags** (`no_bet_review` → audit only, not auto no-bet)

### 6.2 Confidence layer

| `conflict_level` | `recommendation` | Confidence delta |
|----------------|------------------|------------------|
| low | support_internal | 0 |
| medium | caution | −3 |
| high | caution / no_bet_review | −6 |
| high + agreement with market_consensus low | | additional −2 |

Gate: SM data available + `sportmonks_confidence ≥ 55`.

### 6.3 Disagreement detection

Extend existing `_market_disagreement()` logic:

```
if disagreement_vs_internal >= 0.25:
    append audit warning (structured)
if disagreement_vs_internal >= 0.40 AND conflict_level == high:
    apply confidence −6 (not selection flip)
if sm_winner != internal_winner AND sm_prob_max >= 0.55:
    append conflict "external_model_divergence" — NO selection change
```

### 6.4 Audit enrichment

Always populate (even in shadow mode):

- `sportmonks_benchmark_trace` (existing)
- **New design fields:** `sm_winner_lean`, `internal_winner_lean`, `disagreement_vs_internal`, `consensus_with_internal`, `promotion_action: none|confidence_only`

### 6.5 Optional 24C odds factor blend (still not winner-direct)

Max **15% influence** on `odds_score` computation:

```
odds_score = 0.85 * consensus_score + 0.15 * sm_implied_strength
```

Only when SM odds available AND conflict_level ≠ high. Never touches 1X2 resolver directly — only shifts odds factor score that feeds edge indirectly.

---

## 7. Impact Simulation

Estimated **analytical uplift** if promotion applied in `gated` mode after shadow validation. Not betting ROI.

| Promotion target | Phase | Impact | Confidence | Primary beneficiary markets |
|------------------|-------|--------|------------|----------------------------|
| ExpectedLineup → lineup + confidence | 24A | **High** | Medium–High | 1X2 late; first goal; O/U when rotation |
| ExpectedLineup → injury cross | 24C | **Medium** | Medium | 1X2 when late news |
| TournamentContext → motivation | 24B | **Medium** | Medium | 1X2 draw/must-win; group MD3 |
| TournamentContext → tactics O/U | 24B | **Low–Medium** | Medium | O/U 2.5 |
| xG Intelligence → tactics (gated) | 24C | **Medium** | Low–Medium | O/U; BTTS |
| Sportmonks pred → confidence/audit | 24C | **Low** | High | Confidence calibration; watch-only |
| Sportmonks pred → odds blend 15% | 24C optional | **Low–Medium** | Low | 1X2 edge indirect |
| All combined (post-calibration) | 25 | **High** | Low–Medium | Full stack |

**Aggregate gated rollout (24A+24B+24C shadow-proven):** **+5% to +12%** relative hit-rate improvement vs current trace-only baseline (Phase 23 estimate narrowed with adapter caps).

---

## 8. Safe Rollout Plan

### 8.1 Recommended phase order

```
24A  Expected Lineup Promotion (highest ROI, clearest gates)
  └─ shadow → gated lineup factor + confidence

24B  Tournament Context Promotion (group-stage value)
  └─ shadow → gated motivation + tactics O/U nudges

24C  xG + Sportmonks Benchmark Promotion (lowest pre-match coverage)
  └─ shadow → gated xG tactics; SM confidence/audit only
  └─ optional SM odds blend after replay uplift proof

25   Calibration & weight review (OUT OF SCOPE for 23B/24)
```

**Alternative considered:** SM before xG — rejected because SM direct-winner risk is higher and audit-only value is sufficient until lineup/context promotions prove adapter pattern.

### 8.2 Per-phase deliverables (design spec)

| Phase | Implementation scope | Weight table | Mode progression |
|-------|---------------------|--------------|------------------|
| **24A** | Promotion Adapter v1; ExpectedLineup hooks; shadow JSONL | Unchanged | off → shadow → gated |
| **24B** | TournamentContext hooks; dedup with tour_intel + motivation | Unchanged | shadow → gated |
| **24C** | xG gated tactics; SM confidence; BTTS shadow; replay report | Unchanged | shadow → gated |
| **25** | Calibrated weights optional; may add 10th factor only if backtest proves | May change | calibration approval |

### 8.3 Rollback strategy

- Feature flag per agent: `promotion_expected_lineup`, `promotion_tournament_context`, `promotion_xg`, `promotion_sportmonks`
- Instant rollback = set flag `off` → identical to Phase 22 trace behavior
- Shadow logs retained for post-mortem

---

## 9. Promotion Map

```
┌─────────────────────────────┬──────────────────┬─────────────────────────────┐
│ Trace agent                 │ Target WDE factor│ Promotion type              │
├─────────────────────────────┼──────────────────┼─────────────────────────────┤
│ expected_lineup_agent       │ lineup_strength  │ Score/edge blend (24A)      │
│ expected_lineup_agent       │ injuries (cross) │ Late-news modifier (24C)  │
│ expected_lineup_agent       │ confidence caps  │ Threshold layer (24A)     │
│ tournament_context_agent    │ motivation       │ Score/edge blend (24B)      │
│ tournament_context_agent    │ tactics_matchup  │ O/U lean only (24B)         │
│ tournament_context_agent    │ odds interpret.  │ Penalty sensitivity (24B)   │
│ xg_intelligence_agent       │ tactics_matchup  │ Gated score/edge (24C)      │
│ xg_intelligence_agent       │ O/U / BTTS       │ Extended markets (24C)      │
│ sportmonks_prediction_agent │ confidence       │ Conflict penalties (24C)    │
│ sportmonks_prediction_agent │ odds_market      │ Optional 15% blend (24C)    │
│ sportmonks_prediction_agent │ 1X2 selection    │ ❌ BLOCKED                  │
└─────────────────────────────┴──────────────────┴─────────────────────────────┘

Fusion V2 companions (Option C supplements):
  expected_lineup → confidence band when late_news_risk high
  sportmonks_prediction → consensus_strength dampening when conflict high
```

---

## 10. Factor Map (Post-Promotion — Weights Unchanged)

| Factor | Weight | Current sources | + Promotion add (24A–24C) |
|--------|--------|-----------------|---------------------------|
| data_quality | 15% | Report | unchanged |
| team_form | 15% | form, ELO | unchanged |
| injuries_suspensions | 12% | injury_v2 | + expected late-news (24C) |
| lineup_strength | 12% | lineup_v2 | + expected composite (24A) |
| tactics_matchup | 12% | tactics, xg_chance, impacts | + context O/U (24B); + SM xG gated (24C) |
| player_quality | 10% | player_quality | unchanged |
| odds_market_signal | 10% | consensus, sharp | + optional SM 15% blend (24C) |
| motivation_psychology | 8% | motivation, tour_intel | + context blend (24B) |
| weather_referee | 6% | weather, referee | unchanged |

**Sum remains 100%.** Promotions redistribute *signal within* factors, not weight mass.

---

## 11. Risk Analysis

| Risk | Severity | Mitigation |
|------|----------|------------|
| Double-counting lineup (v2 + expected) | **High** | Authority switch by official flag; overlap dedup |
| Motivation triple stack (psych + tour_intel + context) | **High** | 50% dampening when flags overlap; `context_supports_internal` gate |
| xG quadruple stack (tactics + xg_chance + SM xG) | **Medium** | `plan_support=full` + `xg_supports_internal` gates |
| SM prediction overrides internal model | **Critical** | **Hard block** on 1X2 resolver; confidence-only path |
| Confidence over-penalization → excessive no-bet | **Medium** | Caps on cumulative promotion confidence deltas (−10 max) |
| Placeholder WC standings → bad context promotion | **Medium** | `group_context_strength < 36` → trace only |
| Promotion without calibration → false precision | **Medium** | Shadow mode mandatory minimum 50 fixtures replay |
| Weight table drift pressure | **Low** | Explicit governance; Phase 25 only |

---

## 12. Expected Gain Estimate (By Rollout)

| Milestone | Cumulative est. uplift | Risk-adjusted |
|-----------|------------------------|---------------|
| Current (trace only) | 0% (baseline) | — |
| 24A gated | +3% to +6% | +2% to +4% |
| 24A + 24B gated | +5% to +9% | +3% to +6% |
| 24A + 24B + 24C gated | +7% to +12% | +4% to +8% |
| Phase 25 calibration | +10% to +18% | +6% to +12% (requires deduped promotions) |

**Largest single tranche:** 24A ExpectedLineup (late-stage WC matches).

---

## 13. Shadow Validation Requirements (Pre-Gated)

Before any `gated` mode activation, replay must report:

1. **Lineup overlap correlation** — expected vs confirmed overlap vs 1X2 hit-rate delta  
2. **Context disagreement rate** — when `context_supports_internal=false`, outcome variance  
3. **xG gate pass rate** — % fixtures with `plan_support=full` pre-kickoff  
4. **SM divergence rate** — high conflict frequency and false-positive confidence penalty cost  
5. **Net confidence delta distribution** — ensure no >20% fixtures pushed into unintended no-bet  

Minimum sample: **50 WC-relevant fixtures** (or full group-stage round replay).

---

## 14. Governance Checklist (Approval Gates)

| Gate | Approver action |
|------|-----------------|
| 23B design approved | Proceed to 24A implementation |
| 24A shadow report acceptable | Enable 24A gated |
| 24B shadow report acceptable | Enable 24B gated |
| 24C shadow report acceptable | Enable 24C gated (SM still no winner-direct) |
| Phase 25 calibration | Separate approval; may adjust weights |

---

## 15. Stop Boundary

Phase 23B **Trace Promotion Design complete**.  
**No code, WDE weights, deployment, or calibration executed.**  
Await approval before Phase **24A** implementation.

---

## Appendix A — Promotion Adapter Interface (Design Sketch)

```python
# NOT IMPLEMENTED — specification only

@dataclass
class PromotionDelta:
    factor_name: str          # existing WDE factor key
    score_delta: float        # bounded ±8
    edge_delta: float         # bounded ±0.04
    confidence_delta: float   # bounded ±6
    source_agent: str
    gate_passed: bool
    mode: Literal["shadow", "gated", "applied"]

class TracePromotionAdapter:
    def compute(
        self,
        specialist_report: MatchSpecialistReport,
        *,
        mode: PromotionMode,
        hours_to_kickoff: float | None,
    ) -> list[PromotionDelta]: ...
```

This adapter is the **single insertion point** for all Phase 24 work — prevents scattered WDE edits.
