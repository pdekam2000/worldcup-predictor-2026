# Phase 17 — Prediction Attribution Audit

Generated: 2026-06-19T17:54:49.618636+00:00

## Mode

- **Read-only audit** — no code, weight, or model changes
- **No deploy**

## 1. Dataset

- Fixtures analyzed: **207**
- Sources: {'historical_csv': 12, 'db_bundesliga': 180, 'live_wc': 15}
- Final (harmonized) accuracy: **30.0%**
- WDE-only accuracy: **34.8%**
- Scoreline-implied accuracy: **30.0%**
- Harmonization override rate (WDE ≠ final): **91.8%**

> **Architecture note:** Production final 1X2 is always scoreline-implied after harmonization. WDE influences pre-harmonization lean; scoreline λ drives the published pick.

## 2. Accuracy source ranking

| Layer | Accuracy | Role |
|-------|----------|------|
| Harmonized final | 30.0% | Published prediction |
| Scoreline engine | 30.0% | Primary driver of final 1X2 |
| WDE | 34.8% | Overridden when scoreline disagrees |

## 3. Signal leaderboard (aligned with actual on correct predictions)

Correct predictions: **62** (30.0%)

1. **Team Form** — 53 fixtures (85.5% of correct)
2. **Tournament Intelligence** — 53 fixtures (85.5% of correct)
3. **Motivation Psychology** — 53 fixtures (85.5% of correct)
4. **Player Quality** — 53 fixtures (85.5% of correct)
5. **xG** — 52 fixtures (83.9% of correct)
6. **Market Consensus** — 9 fixtures (14.5% of correct)
7. **Odds Market** — 8 fixtures (12.9% of correct)
8. **Sharp Money** — 6 fixtures (9.7% of correct)
9. **Lineups** — 1 fixtures (1.6% of correct)
10. **Weather** — 1 fixtures (1.6% of correct)

## 4. Signal failure leaderboard (pushed toward wrong final pick)

1. **Team Form** — 136 fixtures (93.8% of wrong)
2. **Tournament Intelligence** — 136 fixtures (93.8% of wrong)
3. **Motivation Psychology** — 136 fixtures (93.8% of wrong)
4. **Player Quality** — 136 fixtures (93.8% of wrong)
5. **xG** — 134 fixtures (92.4% of wrong)
6. **Odds Market** — 9 fixtures (6.2% of wrong)
7. **Market Consensus** — 9 fixtures (6.2% of wrong)
8. **Sharp Money** — 5 fixtures (3.4% of wrong)
9. **Lineups** — 4 fixtures (2.8% of wrong)
10. **Weather** — 1 fixtures (0.7% of wrong)

## 5. Correlation table (signal vs actual outcome)

| Signal | Available % | Accuracy when signal has lean | Correlation |
|--------|-------------|-------------------------------|-------------|
| Odds Market | 12.1% | 36.0% | +0.060 |
| Market Consensus | 13.0% | 40.7% | +0.108 |
| Odds Movement | 13.0% | 0.0% | -0.300 |
| Sharp Money | 13.0% | 44.4% | +0.145 |
| Team Form | 100.0% | 29.0% | -0.010 |
| Injuries | 1.4% | 0.0% | -0.300 |
| Lineups | 7.2% | 13.3% | -0.166 |
| xG | 100.0% | 28.5% | -0.014 |
| Tournament Intelligence | 100.0% | 29.0% | -0.010 |
| Motivation Psychology | 100.0% | 29.0% | -0.010 |
| Player Quality | 100.0% | 29.0% | -0.010 |
| ELO | 0.0% | 0.0% | +0.000 |
| Weather | 7.2% | 50.0% | +0.200 |
| Referee | 5.8% | 0.0% | +0.000 |
| Sportmonks Enrichment | 6.3% | 0.0% | +0.000 |

## 6. Winning combinations (top pairs on correct predictions)

- **Motivation Psychology + Player Quality**: 53
- **Motivation Psychology + Team Form**: 53
- **Motivation Psychology + Tournament Intelligence**: 53
- **Player Quality + Team Form**: 53
- **Player Quality + Tournament Intelligence**: 53
- **Team Form + Tournament Intelligence**: 53
- **Motivation Psychology + xG**: 48
- **Player Quality + xG**: 48
- **Team Form + xG**: 48
- **Tournament Intelligence + xG**: 48
- **Market Consensus + Odds Market**: 8
- **Motivation Psychology + Sharp Money**: 5

## 7. Ablation estimates (read-only simulation)

| Removed signal | WDE acc | WDE Δ | Scoreline acc | Scoreline Δ | Final acc | Final Δ |
|----------------|---------|-------|---------------|-------------|-----------|---------|
| xG | 35.3% | -0.5% | 29.0% | +1.0% | 29.0% | +1.0% |
| Odds | 34.3% | +0.5% | 29.5% | +0.5% | 29.5% | +0.5% |
| Injuries | 34.8% | +0.0% | 29.5% | +0.5% | 29.5% | +0.5% |
| Market Consensus | 34.3% | +0.5% | 29.5% | +0.5% | 29.5% | +0.5% |
| Team Form | 34.8% | +0.0% | 30.0% | +0.0% | 30.0% | +0.0% |
| Tournament | 35.3% | -0.5% | 30.0% | +0.0% | 30.0% | +0.0% |

## 8. Architecture recommendation

- **Primary accuracy driver:** Scoreline λ → harmonized final 1X2. WDE is overridden in **91.8%** of fixtures.
- **WDE vs final:** WDE accuracy (**34.8%**) exceeds harmonized final (**30.0%**) — harmonization to scoreline **reduces** accuracy on this sample.
- **Best correlating signals (when lean available):** Sharp Money (+0.145), Market Consensus (+0.108), Odds Market (+0.060).
- **Always-on signals (form, xG, tournament, motivation, player quality):** ~29% hit rate ≈ baseline — they align often on wins only because they always emit a lean, not because they add lift.
- **Sparse / noise signals:** Odds Movement (0% when lean), Injuries, Lineups, Referee, Sportmonks — low availability or no lift.
- **Largest scoreline sensitivity:** Removing **xG** changes scoreline accuracy by **+1.0%** (slight improvement when stripped on Bundesliga offline replay).
- **Highest ROI:** (1) Fix harmonization override — WDE is better than final; (2) Invest in odds/consensus/sharp paths where data exists; (3) Recalibrate always-on λ inputs rather than adding agents.

## Success criteria answers

**Q1 — What contributes most to current accuracy?** The **scoreline Poisson λ path** (odds + form + injuries + xG blend) — it *is* the published prediction after harmonization. Among specialist signals with measurable lift, **Sharp Money** and **Market Consensus** show the highest correlation with actual outcomes (+0.145, +0.108), but only on ~13% of fixtures.

**Q2 — What contributes least?** **Odds Movement**, **Injuries**, **Lineups**, **Referee**, **Sportmonks Enrichment**, **ELO** — sparse availability and zero/negative correlation. Always-on agents (form, tournament, motivation, player quality) match baseline accuracy (~29%) and do not discriminate.

**Q3 — Which signal should receive more investment?** **Market Consensus + Sharp Money + Odds Market** coverage (extend from ~12% to majority of fixtures). Secondary: **scoreline λ calibration** for Bundesliga-scale replays.

**Q4 — Which signal is mostly noise?** **Always-on form/tournament/motivation/player-quality leans** on offline Bundesliga builds — they appear in 85%+ of “correct” calls only because they are always present. **Odds Movement** shows 0% accuracy when a lean exists.

**Q5 — Highest ROI improvement opportunity?** **Stop harmonization from overriding WDE when WDE is stronger** (34.8% vs 30.0% on this sample). Then improve **odds/consensus data coverage** and **λ blend** rather than new specialist agents.

**Stop — audit only. No implementation. No deploy.**
