# PHASE 32 — WORLD CUP PREDICTION QUALITY UPGRADE AUDIT

**Mode:** Audit only  
**Date:** 2026-06-20  
**Reference:** Production commit `267812e`; Phases 30F, 31D, 31E replay findings

**No code changes. No deploy.**

---

## Executive Summary

| Question | Answer |
|----------|--------|
| Why are most WC fixtures 50–55 confidence? | **Scoring inputs cluster at neutral defaults** (form 50, H2H 45, injuries 50, odds 55) while only lineups (80) and DQ (55) lift the weighted total to **~54**. |
| Why No Bet despite “decent” confidence? | **WDE hard floor at 60** — sample avg **55.0**, max **56.4**; all fixtures **3–4 points below** recommendation gate. |
| What actually moves confidence today? | **Lineups (weight 10%)**, **data quality (20%)**, **odds (15%)** in `ScoringEngine`; specialist aggregate adds **≤±4 pts** via `(agg−50)×0.08`. Most agents affect **1X2 edge / O-U**, not confidence. |
| Sportmonks gap | **~15–20% utilized**; xG/predictions mostly **shadow/gated**; `MAX_SPORTMONKS_CONFIDENCE_BOOST = 0` (reduce-only). |
| Fastest path 52→60+ without lowering thresholds? | **(1) Real pre-tournament form + H2H for WC teams**, **(2) stronger odds/consensus signal**, **(3) activate bounded xG/lineup promotion on high-DQ fixtures** — combined **+5 to +10** pts realistic. |

**Verdict:** The system is **mathematically capped** ~3–5 points below the 60 recommendation gate on upcoming WC fixtures. Thresholds are working as designed; **missing discriminative inputs** (form, H2H, injury depth, market conviction) — not broken ranking — limit coverage.

---

## Task 1 — Confidence Breakdown Audit (20 Upcoming WC Fixtures)

**Sample:** First 20 upcoming `world_cup_2026` fixtures (status NS/TIMED), measured via production pipeline stack (hybrid replay with cached odds + full specialist orchestrator, 2026-06-20).

| Metric | Value |
|--------|------:|
| Fixtures measured | 19 / 20 (1 tactics agent error on missing formation) |
| Avg confidence | **55.0** |
| Max confidence | **56.4** |
| Avg data quality | **55.0** |
| No Bet @ WDE 60 | **100%** |
| Ranked picks @ 60 | **0%** |

### Per-fixture pattern (representative — nearly identical across sample)

| Component | Score | Weight | Weighted contribution |
|-----------|------:|-------:|----------------------:|
| **Form** | 50.0 | 22% | 11.0 |
| **H2H** | 45.0 | 18% | 8.1 |
| **Injuries** | 50.0 | 15% | 7.5 |
| **Lineups** | 80.0 | 10% | 8.0 |
| **Odds** | 55.0 | 15% | 8.25 |
| **Data quality** | 55.0 | 20% | 11.0 |
| **Scoring subtotal** | — | — | **53.9** |
| Specialist aggregate (~50.5) | +0.04 | `(agg−50)×0.08` | ~0.04 |
| WDE adjustments (promotions/penalties) | +2.0 typical | — | → **~56 final** |

**Example fixtures:**

| Match | Conf | DQ | No Bet | Top blocker |
|-------|-----:|---:|:------:|-------------|
| Brazil vs Morocco | 56.4 | 55 | Yes | `confidence_below_60` |
| Germany vs Curaçao | 56.4 | 55 | Yes | `confidence_below_60` |
| Spain vs Cape Verde | 47.5 | 55 | Yes | WDE penalties (conflicts/disagreement) |
| England vs Croatia | 56.4 | 55 | Yes | `confidence_below_60` |

### Agent-level confidence contribution (actual code paths)

| Agent / source | Moves `confidence_score` directly? | Typical WC impact | Notes |
|----------------|-----------------------------------|-------------------|-------|
| **ScoringEngine form** | Yes (weight 22%) | **Neutral** (50) | No WC club/national form in API path pre-kickoff |
| **ScoringEngine H2H** | Yes (18%) | **−2.7 pts** (45 vs 50 neutral) | Missing H2H → default 45 |
| **ScoringEngine injuries** | Yes (15%) | Neutral (50) | Sparse injury lists |
| **ScoringEngine lineups** | Yes (10%) | **+3.0 pts** (80 vs 50) | Expected/projected lineups strong |
| **ScoringEngine odds** | Yes (15%) | **+0.75 pts** (55 vs 50) | Odds present but weak differentiation |
| **ScoringEngine DQ** | Yes (20%) | **+1.0 pt** (55 vs 50) | Post–Phase 30E improvement |
| **Specialist aggregate** | Yes (`×0.08`) | **~0** (agg ≈ 50.5) | Master agent neutral on WC friendlies |
| **Team Form Agent** | WDE factor only | Edge, not conf | Drives 1X2 lean |
| **Lineup / Expected Lineup** | WDE `lineup_strength` + promotion | **+0–2 conf** (promotion cap) | Promotion often inactive pre-official XI |
| **Odds / Market Consensus** | WDE `odds_market_signal` | **−5 conf** if disagreement | Penalty binds on some fixtures |
| **Injury agents** | WDE factor | Edge + absence penalty | Rarely >50 absence on WC sample |
| **Sportmonks xG / prediction** | Promotion adapters | **0 boost** (reduce-only cap) | Shadow/gated |
| **Weather / Referee / Motivation** | WDE context factor | O-U / edge | **No direct confidence lift** |
| **Tournament context** | Motivation promotion | **+0–1.5 conf** | Placeholder tables limit lift |

**Finding:** On WC upcoming fixtures, **only the six ScoringEngine components materially set confidence**. Specialist agents mostly **cancel out** (aggregate ≈ 50) unless they trigger **WDE penalties** (→ 47.5 confidence on conflict fixtures).

---

## Task 2 — Confidence Bottleneck Ranking

| Rank | Bottleneck | Quantified impact | Evidence |
|------|------------|-------------------|----------|
| **1** | **WDE `no_bet_confidence_minimum = 60`** | **100% No Bet** when conf 50–59 | 19/19 sample fixtures blocked; avg **4.0 pts** below gate |
| **2** | **Neutral form + H2H defaults** | **~−5.7 pts** vs achievable | Form 50 + H2H 45 fixed across sample; improving both to 65 → **+~6.1 weighted pts** |
| **3** | **Weak odds differentiation** | **~+2.3 pts** headroom | Odds stuck at 55; strong consensus (75+) → **+3.0 weighted pts** |
| **4** | **Specialist aggregate near 50** | **~±0–1 pt** | `(50.5−50)×0.08 ≈ 0.04`; agents add complexity without confidence lift |
| **5** | **WDE penalties (odds disagreement, conflicts)** | **−5 to −9 pts** on subset | 3/19 fixtures dropped to **47.5** |
| **6** | **DQ band 50–55 scoring cap** | Caps at **55** when DQ < 50 | Sample DQ=55 (OK); production WC sometimes DQ=40–45 → extra cap |
| **7** | **Promotion adapters inactive/gated** | **0–6 pts uncaptured** | Lineup/context/xG/SM promotions capped at **+6 cumulative** but rarely fire pre-kickoff |
| **8** | **Market Ranking `_MIN_CONFIDENCE = 55`** | Secondary | Redundant while WDE=60 binds first |

---

## Task 3 — Sportmonks Utilization Matrix

| Capability | Available (Sportmonks) | Used in WC prediction | Prediction impact today | Priority |
|------------|------------------------|----------------------|-------------------------|----------|
| **Fixture shell / participants** | Yes | Partial (date lookup) | Identity only | Low |
| **Lineups** | Yes | Gap-fill when API-Football missing | **High** for lineups score | Medium |
| **Sidelined / injuries** | Yes | Gap-fill | Medium (injury factor) | Medium |
| **In-match statistics** | Yes | Partial (`statistics`) | xG blend in goals | Medium |
| **xG (`xGFixture`)** | Yes | **Not in live predict path** | **High potential** via tactics promotion | **High** |
| **Prediction model** | Yes | Agent only; **boost capped at 0** | Audit/disagreement only | **High** (if reweighted) |
| **Odds** | Yes | **No** | **High** (15% weight) | **High** |
| **Team form (SM)** | Yes | **No** | **High** (22% weight) | **High** |
| **Standings / live table** | Yes | Local/API-Football only | Motivation/context | Medium |
| **H2H** | Yes | **No** (API-Football only) | **High** (18% weight) | **High** |
| **Referee statistics** | Yes | Name only | Low–medium O-U | Low |
| **Pressure index** | Yes | **No** | Medium motivation | Medium |
| **Trends** | Yes | **No** | Medium market signal | Medium |
| **Events** | Yes | CLI path only | Low | Low |

**Utilization estimate:** **~15–20%** (unchanged from Phase 22 audit).

---

## Task 4 — Specialist Agent Impact Ranking

### High impact (moves outputs materially)

| Agent | Confidence | Prediction (1X2/O-U) | Recommendations |
|-------|:----------:|:--------------------:|:---------------:|
| **Odds Market Agent** | Indirect (+odds score) | **High** implied probs | Enables market ranking inputs |
| **Market Consensus Agent** | **−5 if disagreement** | Medium | Rank score modifier |
| **Lineup Intelligence Agent** | **+3 via lineups score** | **High** strength edge | Official XI unlocks picks |
| **Team Form Agent** | Neutral today (50) | **High** when data exists | Would lift conf if fed |
| **Tactics / xG agents** | Via promotion (gated) | **High** O-U | Goals estimate |
| **Master Analysis Agent** | Aggregates (~50) | Conflict detection | Triggers penalties |

### Medium impact

| Agent | Notes |
|-------|-------|
| Injury Suspension (+ Intelligence) | WDE injury factor; −8 conf if injuries missing in scoring |
| Expected Lineup Agent | Promotion shadow; +0–2 conf when gated |
| Tournament Context / Intelligence | Motivation promotion +0–1.5 conf |
| Sportmonks Prediction Agent | **Reduce-only** confidence adapter |
| XG Intelligence Agent | Shadow promotion to tactics |
| Odds Control / Movement / Sharp Money | Market quality; disagreement paths |

### Low impact (complexity > value on WC pre-kickoff)

| Agent | Notes |
|-------|-------|
| Weather Agent | O-U adjustment only; rare WC impact |
| Referee Agent | Static ~58 impact score; minimal edge |
| Elo Team Strength | Blends into form; low data on WC friendlies |
| Player Quality | First-goal candidates; not confidence |
| Motivation Psychology | Heuristic defaults without confirmed tables |

**Agents to simplify or defer pre-kickoff:** Elo, Player Quality, Sharp Money (when no line movement), duplicate injury agents (merge signals).

---

## Task 5 — Recommendation Coverage Audit

### Source A — Stored prediction history (Phase 30F, n=105)

| Metric | Value |
|--------|------:|
| No Bet | **61.9%** |
| Recommended | **38.1%** |
| Avg confidence | Mixed (59% below 60) |
| Safe / Value / Aggressive | Not fully tracked in JSONL |

**Primary No Bet cause:** `confidence_below_60` (**95.4%** of No Bet rows).

### Source B — Production WC upcoming live API (Phase 30F, n=40)

| Metric | Value |
|--------|------:|
| No Bet | **100%** |
| Ranked picks | **0%** |
| Confidence range | ~16–55 (most 48–55) |
| DQ range | 40–55 |

### Source C — Phase 32 sample (19 WC fixtures, 2026-06-20)

| Metric | Value |
|--------|------:|
| No Bet @ 60 | **100%** |
| Safe Pick | **0%** |
| Value Pick | **0%** |
| Aggressive Pick | **0%** |
| Avg confidence | **55.0** |

### Why recommendations fail

1. **Final confidence 55 ± 1 < WDE 60** (binding).
2. **Phase 30C gate (55/45) never reached** — WDE blocks first.
3. **Market ranking** requires conf ≥ 55 AND DQ ≥ 45 — satisfied on sample, but **WDE No Bet suppresses pick emission**.
4. **Flat scoring** → no fixture reaches 60 organically.
5. **Penalties** on ~16% of fixtures push confidence to **47.5**.

---

## Task 6 — Confidence Improvement Opportunities (thresholds unchanged)

Estimates for **average WC upcoming fixture** currently at **~55**:

| Improvement | Est. confidence gain | Feasibility |
|-------------|---------------------:|-------------|
| **WC team form feed** (last 5 NT matches via API-Football or SM) | **+3 to +5** | High — form 50→65 |
| **H2H enrichment** for WC pairs | **+2 to +3** | Medium — H2H 45→60 |
| **Stronger odds + consensus integration** | **+2 to +3** | High — odds 55→70, reduce disagreement penalty |
| **Sportmonks xG → tactics promotion (active)** | **+1 to +3** | Medium — gated promotion exists |
| **Official lineup confirmation boost** | **+1 to +2** | Medium — lineups already 80; promotion cap +2 |
| **Injury depth (SM sidelined + API)** | **+1 to +2** | Medium |
| **Team ID completeness** (Phase 31E done) | **+0 to +1** | Done — enables H2H/injury cache hits |
| **Pressure / trends / referee SM** | **+0 to +1** | Low–medium |
| **Increase specialist conf multiplier** (0.08→0.12) | **+1 to +2** | Code change — out of scope for audit |
| **Sportmonks prediction as boost** (currently 0 cap) | **+0 to +3** | Policy change — currently reduce-only |

**Combined realistic stack (form + H2H + odds): +5 to +10** → avg **60–65** without threshold changes.

---

## Task 7 — Priority Roadmap (Top 10)

| # | Improvement | Impact | Effort | Risk | Tier |
|---|-------------|--------|--------|------|------|
| 1 | **National-team form pipeline** (last N NT fixtures) | **High (+3–5 conf)** | Medium | Low | **Quick win** |
| 2 | **H2H cache for WC opponents** (team IDs now backfilled) | **High (+2–3)** | Medium | Low | **Quick win** |
| 3 | **Odds quality scoring** — reward tight consensus, fix disagreement false positives | **High (+2–3)** | Medium | Medium | **Quick win** |
| 4 | **Enable xG promotion on WC** when SM xG confidence ≥ 50 | **Medium (+1–3)** | Low | Low | Quick win |
| 5 | **Pre-kickoff lineup certainty ladder** (expected → confirmed) | **Medium (+1–2)** | Medium | Low | Medium |
| 6 | **Sportmonks team form + standings** into form agent | **High (+3–5)** | High | Medium | Medium |
| 7 | **Injury enrichment** (SM sidelined + API injuries league-aware) | **Medium (+1–2)** | Medium | Low | Medium |
| 8 | **Reduce specialist conflict penalties** when signals are weak | **Medium (+1–2 on subset)** | Low | Medium | Medium |
| 9 | **Sportmonks odds feed** (alternative book consensus) | **High (+2–4)** | High | Medium | Major |
| 10 | **Calibrated replay gate** — validate 60 floor vs 55 for WC-only SKU | **Coverage +15–20pp** | High | **High** | Major (policy) |

### Quick wins (1–2 sprints)

- Form pipeline for NT matches  
- H2H backfill for WC fixture pairs  
- Odds/consensus scoring refinement  
- Activate xG promotion on high-DQ WC fixtures  

### Medium effort

- SM form/standings integration  
- Lineup confirmation promotion  
- Injury depth merge  

### Major projects

- Full Sportmonks odds + prediction uplift (requires adapter policy change)  
- Historical odds rebuild for calibration (Phase 31E follow-on)  
- WC-specific confidence calibration study (threshold review — **out of scope unless approved**)

---

## Final Answer

**What is the fastest path to move average World Cup confidence from ~52 to 60+ without lowering thresholds?**

**Stack three input upgrades that target the flat scoring components:**

1. **Feed real national-team form** into `ScoringEngine` (replace neutral 50) — **+3–5 pts**.  
2. **Populate H2H** for WC pairs using backfilled team IDs — **+2–3 pts**.  
3. **Strengthen odds/consensus signal** and reduce false disagreement penalties — **+2–3 pts**.

That yields **+7–11 confidence points** on fixtures currently clustering at **53.9 → 56**, pushing the average into **60–62** and unlocking WDE + Market Ranking recommendations **without touching the 60 threshold**.

Secondary accelerators: **activate existing xG/lineup promotion adapters** (+1–3 pts) and **Sportmonks form/standings** (+2–4 pts longer term).

**Do not prioritize:** adding more specialist agents, lowering gates, or Sportmonks prediction as reduce-only — these do not address the **+4 point gap** economically.

---

**STOP — Audit complete. No code changes. No deploy.**

*Supporting measurement: `artifacts/phase32_audit_data.json` (19 WC fixtures, 2026-06-20).*
