# TOP10-TO-TOP3-SELECTOR-1 — Final Report

Phase: **TOP10-TO-TOP3-SELECTOR-1** | Mode: Read-only shadow selector | Status: **Complete — DO NOT PROMOTE**

## Final Recommendation

**TOP10_SELECTOR_NO_VALUE**

Validation: **24/24 passed** | Sample: **13 finished WC knockout matches** | 89% target: **NOT achieved (theoretical only)**

No shadow selector strategy improves aggregate Top3 hit rate vs raw ECSE Top3 on the current sample. Rank-6–10 rescue mechanics work on individual fixtures (Germany, England) but trade off hits elsewhere (+4 gained / −4 lost on E/F). Tail injection adds Belgium **3-2** to the shadow pool but no strategy selects it into Top3.

---

## Executive Summary

Built a shadow-only package that selects **exactly 3** End Result candidates from ECSE Top10 using six selector strategies (A–F) plus a tail-injection variant. Evaluation uses **90-minute score**; AET/PEN flagged separately. No production WDE, ECSE ranking, lambda, DB, or provider changes.

| Metric | Value |
|--------|-------|
| Raw ECSE Top3 | **53.8%** (7/13) |
| ECSE Top5 coverage | 76.9% (10/13) |
| ECSE Top10 coverage | **92.3%** (12/13) |
| Top10 oracle ceiling (perfect Top3 from Top10) | **92.3%** (12/13) |
| Best selector Top3 | **53.8%** (7/13) — tied with raw |
| Achieved % of Top10 ceiling | **58.3%** (7/12 in-pool hits) |
| 89% observed? | **No** (would require 12/13) |
| 89% theoretical? | **Only if oracle picks correct Top10 line every time** |

**Best strategy on aggregate:** **A_raw_top3** (tied at 53.8%; zero churn vs alternatives that swap hits without net gain).

**Comparison:** TOP3-ENDRESULT-OPTIMIZER-1 **S5 Conservative** still outperforms this phase at **61.5% (8/13)** on the same sample — selecting from Top10 alone does not beat the earlier Top5-focused optimizer.

---

## PART A — Top10 Feature Table

**Artifact:** `artifacts/top10_to_top3_selector_1_feature_table.csv`

For each finished fixture with ECSE Top10, one row per candidate rank 1–10 (plus shadow-injected tail rows stored in JSON payload for F strategy only).

| Feature | Description |
|---------|-------------|
| `original_ecse_rank` | ECSE rank 1–10 (101+ for injected tail) |
| `scoreline` | Candidate score |
| `total_goals`, `goal_difference` | Derived from scoreline |
| `winner_direction` | home / draw / away |
| `btts`, `over_25`, `clean_sheet` | yes/no |
| `favorite_direction_match` | vs WDE 1X2 pick |
| `wde_1x2_alignment`, `wde_btts_alignment`, `wde_ou25_alignment` | yes/no/null |
| `draw_risk_alignment` | yes when draw risk ≥ 0.35 and line is draw |
| `knockout` | boolean |
| `odds_freshness_status` | STALE_ODDS on all 13 matches |
| `candidate_probability`, `candidate_rank_probability_decay` | From snapshot when available |
| `injected_tail_candidate` | false for ECSE rows; true for shadow tail only |

**Rows:** 180 (13 fixtures × 10 ECSE candidates; tail injection not written to CSV — shadow pool only in JSON/runtime for F strategy).

---

## PART B — Selector Strategies

**Package:** `worldcup_predictor/research/top10_to_top3_selector/`

| ID | Strategy | Top3 Hit | Δ vs Raw | Gained | Lost | Rank 6–10 Rescues |
|----|----------|----------|----------|--------|------|-------------------|
| **A** | Raw Top3 (ranks 1–3) | **53.8%** | 0.0 pp | 0 | 0 | 0 |
| **B** | Market-aligned Top3 | 53.8% | 0.0 pp | 3 | 3 | 1 |
| **C** | Portfolio coverage | 38.5% | −15.4 pp | 2 | 4 | 0 |
| **D** | Anti clean-sheet bias | 53.8% | 0.0 pp | 1 | 1 | 1 |
| **E** | Rank 6–10 rescue | 53.8% | 0.0 pp | 4 | 4 | 2 |
| **F** | Hybrid best | 53.8% | 0.0 pp | 4 | 4 | 2 |
| **F_tail** | Hybrid + tail injection pool | 53.8% | 0.0 pp | 4 | 4 | 2 |

### Strategy notes

- **B (Market-aligned):** Re-scores Top10 by ECSE rank decay + WDE 1X2/BTTS/O-U alignment; stale-odds penalty; duplicate clean-sheet penalty. Net zero churn (+3/−3).
- **C (Portfolio):** Archetype diversity underperforms badly (−15.4 pp) — winner/BTTS/hedge slots disrupt strong raw Top3 hits.
- **D (Anti clean-sheet):** Rescues **Germany 1-1** (+1) but loses **Netherlands 1-1** (−1) when swapping clean-sheet slots.
- **E/F (Rank rescue / Hybrid):** Rescues **Germany** and **England** but loses **France 3-0**, **USA 2-0**, **Spain 3-0**, **Switzerland 2-0** — classic small-sample swap pattern without net improvement.

---

## PART C — Tail Candidate Injection (Shadow)

**Rules applied:** When WDE `pick_btts=yes` and `pick_ou25=over_2_5`, inject missing tail lines: 3-2, 2-3, 4-1, 1-4, 4-2, 2-4 (filtered by WDE 1X2 direction). All injected rows carry `injected_tail_candidate=true`.

### Belgium vs Senegal — Actual **3-2** (AET, 90' score)

| Field | Value |
|-------|-------|
| ECSE Top10 | No 3-2 present |
| WDE | home_win · BTTS Yes · Over 2.5 |
| Shadow injection | **3-2 injected** (rank 100, `injected_tail_candidate=true`) |
| Also injected | 4-1, 4-2 (2-3 skipped — away win filter) |
| F_hybrid_tail_injection Top3 | 1-0 · 1-1 · 2-1 |
| **Result** | **Injection covers pool gap; selector does not pick 3-2** |

**Conclusion:** Tail injection solves **candidate absence** in the shadow pool but requires a dedicated high-goal tail slot in selection logic — current hybrid prioritizes ECSE-ranked and rescue heuristics over low-decay injected tails.

---

## PART D — Backtest Results

**Artifacts:**
- `artifacts/top10_to_top3_selector_1_results.json`
- `artifacts/top10_to_top3_selector_1_match_level.csv`

### Segments (strategy A baseline; all strategies share same n per segment)

| Segment | n | Raw Top3 | Top10 Coverage |
|---------|---|----------|----------------|
| All finished knockout | 13 | 53.8% | 92.3% |
| Knockout only | 13 | 53.8% | 92.3% |
| Group stage | 0 | — | — |
| Stale odds | 13 | 53.8% | 92.3% |
| Fresh odds | 0 | — | — |
| AET/PEN flagged (90' still used) | 4 | 50.0% | 75.0% |
| AET/PEN excluded | 9 | 55.6% | 100.0% |

### Key case studies

#### Germany vs Paraguay — Actual **1-1** (rank 7, AET/PEN)

| Strategy | Selected Top3 | Hit |
|----------|---------------|-----|
| A_raw_top3 | 2-0 · 3-0 · 1-0 | No |
| D_anti_clean_sheet | 2-0 · 3-0 · **1-1** | **Yes** (+1) |
| E_rank7_rescue | **1-1** · 2-1 · 1-0 | **Yes** (+1) |
| F_hybrid_best | **1-1** · 2-1 · 1-0 | **Yes** (+1) |

Draw rescue from rank 7 works when Top3 is clean-sheet heavy and no draw present. WDE payload was sparse; ECSE pool heuristics drove rescue.

#### England vs Congo DR — Actual **2-1** (rank 7)

| Strategy | Selected Top3 | Hit |
|----------|---------------|-----|
| A_raw_top3 | 2-0 · 3-0 · 1-0 | No |
| B_market_aligned | 2-0 · **2-1** · 3-1 | **Yes** (+1) |
| E_rank7_rescue | 0-0 · **2-1** · 1-0 | **Yes** (+1) |
| F_hybrid_best | 0-0 · **2-1** · 1-0 | **Yes** (+1) |

BTTS home-win rescue from rank 7 works; B achieves this with lower churn than E/F.

#### Belgium vs Senegal — Actual **3-2** (outside Top10)

| Strategy | Selected Top3 | Hit | Tail injected |
|----------|---------------|-----|---------------|
| All A–F | No 3-2 in selection | No | F_tail adds 3-2 to pool only |

### Overfitting check

| Pattern | Assessment |
|---------|------------|
| E/F +4/−4 on n=13 | High churn; net zero — **not promotable** |
| D +1/−1 | Single-match rescue without aggregate gain |
| B +3/−3 | Swaps within Top5/Top10; net zero |
| Claim 89%? | **No** — best remains 7/13 (53.8%) |
| Claim 92.3% ceiling reachable? | **Theoretical only** — requires oracle selection |

---

## PART E — Promotion Gate Simulation

**Gate status:** **INSUFFICIENT_DATA** (4/7 checks passed)

| Check | Status |
|-------|--------|
| ≥ 40 finished matches | **Fail** (13/40) |
| Top3 hit rate ≥ 58% | **Fail** (best 53.8%) |
| Improve raw Top3 by ≥ +5 pp | **Fail** (0.0 pp) |
| No major segment regression | Pass |
| Best or tied best | Pass (A tied) |
| Odds freshness documented | Pass (all STALE_ODDS) |
| AET/PEN stable when excluded | Pass |

**Why insufficient:** Only **13** finished knockout matches with ECSE Top10 snapshots. Need **27 more** (→ 40 total) before the proposed gate can open. All odds are stale — fresh-odds segment untestable.

**Important:** Even TOP3-OPTIMIZER-1 S5 at 61.5% would fail the ≥58% + ≥+5 pp gate on promotion criteria if applied naively to n=13; this selector does worse than S5.

---

## PART F — UI & Next Phase

### UI recommendation (no promotion)

| Audience | Display |
|----------|---------|
| **Public** | Raw ECSE **Top3** only |
| **Owner / Pro** | Raw ECSE **Top5** |
| **Owner shadow preview** | Selected Top3 from best future selector (currently **not better than raw** — preview disabled or labeled experimental) |

Do **not** surface shadow selector output as production win rate. Do **not** claim 89%.

### Next phase recommendation

1. **EVAL-COVERAGE-1** — Expand finished-match evaluation beyond 13 knockouts; link `ecse_score_distributions` when registry resolves.
2. **ODDS-FRESHNESS-1** — All 13 matches STALE_ODDS; selector WDE alignment untested on fresh odds.
3. **KEEP_COLLECTING_DATA** — Need 40+ finished matches before any Top3 selector promotion gate.
4. **Candidate generation** — Belgium 3-2 gap is a **generation/tail** problem, not solvable by Top10 re-ranking alone; consider upstream ECSE tail expansion separately from selector logic.

---

## PART G — Validation

**Script:** `scripts/validate_top10_to_top3_selector_1.py`  
**Artifact:** `artifacts/top10_to_top3_selector_1_validation.json`

| Check | Result |
|-------|--------|
| Imports / package load | Pass |
| No DB writes | Pass |
| No provider calls | Pass |
| WDE / ECSE production unchanged | Pass |
| Exactly 3 candidates per strategy | Pass |
| Injected candidates shadow-labeled | Pass |
| 90-minute score / AET/PEN handling | Pass |
| Raw Top3 reproduces 53.8% | Pass |
| Top10 coverage reproduces 92.3% | Pass |
| Artifacts created | Pass |
| Timers not enabled | Pass |

**Final recommendation:** `TOP10_SELECTOR_NO_VALUE`

---

## Deliverables Checklist

| Item | Path | Status |
|------|------|--------|
| Feature table | `artifacts/top10_to_top3_selector_1_feature_table.csv` | Done |
| Results JSON | `artifacts/top10_to_top3_selector_1_results.json` | Done |
| Match-level CSV | `artifacts/top10_to_top3_selector_1_match_level.csv` | Done |
| Validation JSON | `artifacts/top10_to_top3_selector_1_validation.json` | Done |
| Package | `worldcup_predictor/research/top10_to_top3_selector/` | Done |
| Run script | `scripts/run_top10_to_top3_selector_1.py` | Done |
| Validate script | `scripts/validate_top10_to_top3_selector_1.py` | Done |
| Report | `TOP10_TO_TOP3_SELECTOR_1_REPORT.md` | Done |

**STOP — No promotion. No timers. Shadow research complete.**
