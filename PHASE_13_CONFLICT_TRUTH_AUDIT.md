# Phase 13 — Conflict Truth Audit

Generated: 2026-06-19T16:36:23.832861+00:00

## Mode

Read-only audit. No code, weight, λ, harmonization, or deploy changes.

## 1. Sample size

- **Total finished fixtures analyzed:** 262
- **With known results:** 262
- Sources: DB Bundesliga + European (`n=250`), historical World Cup CSV (`n=12`)

> **Dataset caveat:** Bundesliga rows lack rich pre-match odds/lineup context. WDE collapses to ~99% `home_win` while the scoreline engine produces ~95% draws — inflating conflict rate. A **production World Cup replay subset** (`n=15`, live cache) is included below for operational truth.

### Production World Cup subset (live-cache replay)

| Metric | Value |
|--------|-------|
| Fixtures with results | 15 |
| Conflict rate (WDE ≠ Final) | **60.0%** (9 / 15) |
| WDE accuracy (all) | **46.7%** |
| Final accuracy (all) | **60.0%** |
| WDE accuracy (conflicts only) | **33.3%** |
| Final accuracy (conflicts only) | **55.6%** |
| Conflict matrix | `home_win→draw` ×6, `away_win→draw` ×3 |
| WDE home/away → Final draw | 9 cases; draw correct **5**, WDE side correct **3** |

On production World Cup fixtures, **Final beats WDE** overall and during conflicts — opposite of the bulk offline sample.

## 2. Conflict rate

- **WDE ≠ Final:** 251 / 262 = **95.8%**

## 3–4. Accuracy tables

### A) All fixtures

| Metric | WDE | Scoreline-implied | Final |
|--------|-----|-------------------|-------|
| Accuracy | 38.2% | 27.9% | 27.9% |
| Draw rate | 0.0% | — | 95.4% |
| Home rate | 99.2% | — | 3.4% |
| Away rate | 0.8% | — | 1.1% |

### B) Conflict fixtures only

n = 251

| Metric | WDE | Final |
|--------|-----|-------|
| Accuracy | 37.8% | 27.1% |
| Draw rate | 0.0% | 99.6% |
| Home rate | 100.0% | 0.0% |
| Away rate | 0.0% | 0.4% |

### C) Non-conflict fixtures

n = 11

| Metric | WDE | Final |
|--------|-----|-------|
| Accuracy | 45.5% | 45.5% |
| Draw rate | 0.0% | 0.0% |

## 5. Conflict matrix (WDE → Final)

| Transition | Count | % of conflicts |
|------------|-------|----------------|
| home → draw | 250 | 99.6% |
| home → away | 1 | 0.4% |

## 6. Winner analysis (conflict fixtures only)

| Outcome | Count |
|---------|-------|
| WDE correct, Final wrong | 95 |
| Final correct, WDE wrong | 68 |
| Both correct | 0 |
| Both wrong | 88 |

**WDE accuracy (conflicts):** 37.8%  
**Final accuracy (conflicts):** 27.1%  
**Difference (Final − WDE):** -10.8%

## 7. Draw investigation

Conflicts where WDE picked home/away but Final = draw: **250** (99.6% of conflicts)

- Draw was **correct** in these cases: 68 / 250 (27.2%)
- WDE side was **correct**: 95 / 250 (38.0%)

This pattern (directional WDE → harmonized draw) is the dominant conflict shape.

## 8. Harmonization audit (all fixtures)

| Effect | Count | % of all |
|--------|-------|----------|
| Improved accuracy (WDE wrong → Final right) | 68 | 26.0% |
| Reduced accuracy (WDE right → Final wrong) | 95 | 36.3% |
| Changed selection, same correctness | 88 | 33.6% |
| No selection change | 11 | 4.2% |

Note: When WDE ≠ scoreline-implied, harmonization forces Final to match scoreline 1X2.

## 9. Evidence-based answers

### Q1: Is WDE better than Final during conflicts?

**Depends on dataset.**

| Cohort | WDE (conflicts) | Final (conflicts) | Winner |
|--------|-----------------|-------------------|--------|
| All 262 fixtures | 37.8% | 27.1% | **WDE** (+10.8 pp) |
| Production WC (`n=9` conflicts) | 33.3% | 55.6% | **Final** (+22.2 pp) |

Bulk European sample: WDE is more often right when they disagree.  
Production World Cup: scoreline/harmonization path is more often right.

### Q2: Is Harmonization helping or hurting?

**Net hurting on bulk sample; net helping on production WC.**

| Cohort | Improved | Hurt | Net |
|--------|----------|------|-----|
| All 262 | 68 (26.0%) | 95 (36.3%) | **Hurt** |
| Production WC (15) | ~5 | ~3 | **Help** (est. from replay) |

Harmonization faithfully forces Final = scoreline-implied 1X2. It helps when scoreline is well-calibrated (WC); it hurts when λ collapses to symmetric draws without market context (Bundesliga offline).

### Q3: Is Draw overproduction the real bottleneck?

**Yes** — in both cohorts, conflicts are overwhelmingly **directional WDE → Final draw**:

| Cohort | Share of conflicts |
|--------|-------------------|
| All 262 | 99.6% (250 / 251) |
| Production WC | 100% (9 / 9) |

Draw is correct only **27.2%** (bulk) vs **55.6%** (WC conflicts) — scoreline draw bias is harmful without odds, but can be net-positive with full intelligence.

### Q4: Where should future work target?

**Primary: Scoreline engine (λ → Poisson → draw collapse)** — this is where directional WDE signal is lost.  
**Secondary: Conditional harmonization** — do not force draw when WDE confidence and specialists disagree with symmetric λ.  
**Not first:** WDE weight retuning — WDE is not the primary failure mode on production WC; scoreline symmetry is.

## Architecture recommendation

1. **Fix scoreline λ symmetry** — prevent default 1–1 / draw collapse when home/away λ are near-equal but WDE and market lean directional.
2. **Add draw guard before harmonization** — if WDE ≠ scoreline-implied and specialist/market consensus supports WDE, do not auto-flip to draw.
3. **Keep harmonization** for O/U and internal consistency, but decouple blind 1X2 override when scoreline confidence is low.
4. **Do not prioritize WDE weight changes** — production WC evidence shows Final path wins when intelligence is rich; failures trace to scoreline, not WDE.

**Stop here — audit only. No implementation.**
