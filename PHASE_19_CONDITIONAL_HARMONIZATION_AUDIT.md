# Phase 19 — Conditional Harmonization Audit

Generated: 2026-06-19T18:38:10.274856+00:00

## Mode

- **Read-only audit** — no code, weight, or deploy changes
- Same replay dataset as Phase 18 (207 fixtures)

## 1. Dataset

- Fixtures: **207**
- WDE ≠ Scoreline conflicts: **190** (91.8%)
- Production harmful overrides: **63**
- λ spread tertiles: low < **0.000**, high ≥ **0.000** (Bundesliga offline: most fixtures at **0.000** spread — tertile bands degenerate)

> **Note:** Rule A (`no odds -> WDE`, else scoreline) ties DQ/consensus gates at **36.7%**; only **25** fixtures have odds. Rule A is the **simplest** gate.

## 2. Baseline accuracies

| Strategy | Accuracy |
|----------|----------|
| WDE only | **34.8%** |
| Scoreline only | **30.0%** |
| Current production (always harmonize) | **30.0%** |
| Best conditional rule | **36.7%** (Rule A: no odds -> WDE) |

## 3. Cohort: WDE vs Scoreline winner

| Group | n | WDE | Scoreline | Production | Conflicts | WDE wins | Scoreline wins | Winner |
|-------|---|-----|-----------|------------|-----------|----------|----------------|--------|
| Odds present | 25 | 36.0% | 52.0% | 52.0% | 9 | 1 | 5 | **Scoreline** |
| Odds absent | 182 | 34.6% | 26.9% | 26.9% | 181 | 62 | 48 | **WDE** |
| High data quality | 13 | 30.8% | 61.5% | 61.5% | 8 | 1 | 5 | **Scoreline** |
| Medium data quality | 2 | 100.0% | 50.0% | 50.0% | 1 | 1 | 0 | **WDE** |
| Low data quality | 192 | 34.4% | 27.6% | 27.6% | 181 | 61 | 48 | **WDE** |
| High λ spread | 207 | 34.8% | 30.0% | 30.0% | 190 | 63 | 53 | **WDE** |
| World Cup | 27 | 40.7% | 51.9% | 51.9% | 10 | 2 | 5 | **Scoreline** |
| League (Bundesliga) | 180 | 33.9% | 26.7% | 26.7% | 180 | 61 | 48 | **WDE** |

## 4. Candidate gating rules (read-only simulation)

| Rule | Accuracy | Δ vs Prod | Δ vs WDE | Harmful remaining | FP scoreline | FN WDE |
|------|----------|-----------|----------|-------------------|--------------|--------|
| Rule A: no odds -> WDE | 36.7% | +6.8% | +1.9% | 1 | 1 | 48 |
| Rule C: DQ >= 60% -> Scoreline | 36.7% | +6.8% | +1.9% | 1 | 1 | 48 |
| Rule D: odds AND DQ>=60 -> Scoreline | 36.7% | +6.8% | +1.9% | 1 | 1 | 48 |
| Rule D2: odds AND DQ>=55 -> Scoreline | 36.7% | +6.8% | +1.9% | 1 | 1 | 48 |
| Rule C: DQ >= 45% -> Scoreline | 36.2% | +6.3% | +1.4% | 2 | 2 | 48 |
| Rule C: DQ >= 50% -> Scoreline | 36.2% | +6.3% | +1.4% | 2 | 2 | 48 |
| Rule C: DQ >= 55% -> Scoreline | 36.2% | +6.3% | +1.4% | 2 | 2 | 48 |
| Rule E: market consensus -> Scoreline | 36.2% | +6.3% | +1.4% | 2 | 2 | 48 |
| Rule E2: sharp money -> Scoreline | 36.2% | +6.3% | +1.4% | 2 | 2 | 48 |
| Rule F3: WC OR (odds AND spread≥0.25) | 36.2% | +6.3% | +1.4% | 2 | 2 | 48 |
| Rule F6: odds AND (consensus OR sharp) AND spread≥0.15 | 35.7% | +5.8% | +1.0% | 1 | 1 | 50 |
| Rule B: spread >= 0.15 -> Scoreline | 35.3% | +5.3% | +0.5% | 2 | 2 | 50 |
| Rule B: spread >= 0.20 -> Scoreline | 35.3% | +5.3% | +0.5% | 1 | 1 | 51 |
| Rule F1: odds AND DQ≥60 AND spread≥0.25 | 35.3% | +5.3% | +0.5% | 0 | 0 | 52 |
| Rule F2: (odds OR consensus) AND spread≥0.20 | 35.3% | +5.3% | +0.5% | 1 | 1 | 51 |
| Rule F4: consensus AND NOT low spread (<0.20) | 35.3% | +5.3% | +0.5% | 1 | 1 | 51 |
| Rule B: spread >= 0.25 -> Scoreline | 34.8% | +4.8% | +0.0% | 1 | 1 | 52 |
| Rule B: spread >= 0.30 -> Scoreline | 34.8% | +4.8% | +0.0% | 1 | 1 | 52 |
| Baseline: always WDE | 34.8% | +4.8% | +0.0% | 0 | 0 | 53 |
| Rule F5: median spread gate (≥0.00) | 30.0% | +0.0% | -4.8% | 63 | 63 | 0 |
| Baseline: always Scoreline (production) | 30.0% | +0.0% | -4.8% | 63 | 63 | 0 |

## 5. Best gating rule

**Rule A: no odds -> WDE**

- Accuracy: **36.7%**
- Improvement vs production: **+6.8%**
- Improvement vs WDE-only: **+1.9%**
- Harmful overrides remaining: **1** / 63 production harmful (98.4% eliminated)
- False positives (scoreline picked, WDE was right): **1**
- False negatives (WDE picked, scoreline was right): **48**

## 6. Override feature profile (conflict fixtures only)

| Feature | WDE wins (n) | Scoreline wins (n) |
|---------|--------------|-------------------|
| Odds present | 1 | 5 |
| Odds absent | 62 | 48 |
| Consensus present | 2 | 5 |
| Sharp present | 2 | 5 |
| High DQ | 1 | 5 |
| Low DQ | 61 | 48 |
| Low spread | 0 | 0 |
| High spread | 63 | 53 |
| World Cup | 2 | 5 |
| League | 61 | 48 |

## 7. Architecture recommendation

**Conditional harmonization is justified in shadow.** Rule `Rule A: no odds -> WDE` beats both WDE (34.8%) and production (30.0%) at **36.7%** (+6.8% vs production).

Recommended gate (from audit):
- **WDE wins** when: no odds, λ spread < 0.25, or league/offline Bundesliga replay
- **Scoreline wins** when: odds present AND (consensus OR sharp) AND spread ≥ 0.20, OR World Cup with odds

## Success criteria answers

**Q1 — Can conditional harmonization beat both WDE and production?** **YES** — Best rule `Rule A: no odds -> WDE` at **36.7%**.

**Q2 — What is the best gating rule?** **Rule A: no odds -> WDE** (36.7% accuracy).

**Q3 — What percentage of harmful overrides disappear?** **98.4%** (62 of 63 production-harmful cases avoided).

**Q4 — Is implementation justified?** **Yes for shadow A/B** — measurable lift over production with acceptable false-positive rate.

**Stop — audit only. No implementation. No deploy.**
