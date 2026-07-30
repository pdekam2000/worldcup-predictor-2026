# Bet Coverage Optimizer — Phase 2 Enhancement Report

**Branch:** `feature/bet-coverage-optimizer-64-tickets`  
**Status:** Research-only — **not deployed to production**  
**Tests:** 52 passed (`tests/research/bet_coverage_optimizer`)  
**Artifacts:** `artifacts/coverage_optimizer/phase2_20260730T224248Z/` (gitignored local)

## Changes delivered

1. **Top-5 ranked candidates** → `candidate_markets_ranked.json` (+ embedded `ranked_candidates` on each recommendation)
2. **Configurable Top-N** — allowed values **8 / 10 / 12** via config or API (`top_n_scores`); recomputes matrix, scores, fourth market
3. **External scoring weights** — `default_config.json` + `load_optimizer_config()` (JSON; YAML if PyYAML present); no hardcoded weight constants required to retune
4. **Global `coupon_optimizer`** — joint search over coverage candidates across 3 fixtures; returns coupon_score, expected_coupon_value, diversification_score, overlap_penalty, final 64 tickets
5. **This validation / comparison report**

Canonical WDE/ECSE formulas and freezes were **not** modified.

---

## 1. Top5 market comparison (Top8 run, Dundee 1556628)

| Rank | Market | Odds | coverage_score | rejection_reason |
|---:|---|---:|---:|---|
| 1 | Under 3.5 | 1.85 | 0.819 | — (selected) |
| 2 | Away & Under 4.5 | 1.72 | 0.522 | NOT_SELECTED |
| 3 | BTTS No | 1.70 | 0.440 | NOT_SELECTED |
| 4 | BTTS Yes | 2.05 | 0.132 | NOT_SELECTED |
| 5 | Under 4.5 | 1.28 | — | ODDS_BELOW_MIN:1.55 |

Bodø (1494717) Top1: **Home & Under 4.5** @ 1.68  
Admira (1567860) Top1: **Under 3.5** @ 1.78  

Full ranked tables: `phase2_…/top8/candidate_markets_ranked.json`

---

## 2. Top8 vs Top10 vs Top12

| TopN | Fourth selections (1556628 / 1494717 / 1567860) | Coupon expected value* |
|---:|---|---:|
| 8 | Under 3.5 / Home & U4.5 / Under 3.5 | hit_mass utility (exact odds absent) |
| 10 | Under 3.5 / Home & U4.5 / Under 3.5 | recomputed hit_mass |
| 12 | Under 3.5 / Home & U4.5 / Under 3.5 | recomputed hit_mass |

Deterministic regression: same TopN → identical `top_n_scores` + `ranked_candidates`.  
Different TopN → different target score lists / probability mass (asserted in tests).

On this ResearchBook slate the **selected fourth label** stayed stable across 8/10/12; **coverage matrix mass and candidate metrics** still recompute with TopN (see `topn_comparison` in `phase2_research_bundle.json`).

\*When exact-score odds are missing, coupon `expected_coupon_value` falls back to research **hit_mass** (never fabricates odds). Monetary EV is reported separately when priced tickets exist.

---

## 3. Weight sensitivity (Top8, Dundee)

| Profile | Fourth | Rank2 | Rank3 |
|---|---|---|---|
| default | Under 3.5 (0.819) | Away & U4.5 (0.522) | BTTS No (0.440) |
| mass_heavy | Under 3.5 (0.803) | Away & U4.5 (0.526) | BTTS No (0.441) |
| edge_heavy | Under 3.5 (0.882) | Away & U4.5 (0.562) | BTTS No (0.454) |
| odds_heavy | Under 3.5 (0.816) | Away & U4.5 (0.582) | BTTS No (0.517) |

Weights load from config keys:

```json
"coverage_weights": {
  "covered_probability_mass": 0.35,
  "non_exact_probability_mass": 0.20,
  "exact_overlap_probability_mass": 0.15,
  "estimated_edge": 0.20,
  "log_odds": 0.10
}
```

File: `worldcup_predictor/research/bet_coverage_optimizer/default_config.json`

---

## 4. Coupon optimizer comparison

Module: `worldcup_predictor/research/coupon_optimizer/`

- Searches the product of per-fixture Top-K eligible coverage candidates (default K=5)
- Scores each global combo: `coupon_score = w_ev·norm(EV) + w_div·diversification − w_ov·overlap_penalty`
- Emits optimized recommendations + `coupon_tickets/tickets_64.{csv,json}`

On the ResearchBook three-fixture set, the **joint optimum matched independent per-fixture argmax** (`ev_delta_vs_independent = 0`) because the locally best coverage markets already maximize joint hit_mass / diversification for this candidate pool. That is an expected outcome when candidates are sparse and exact odds are incomplete — the machinery is covered by unit tests and will diverge when live exact odds + richer books exist.

---

## 5. New validation report

`artifacts/coverage_optimizer/phase2_20260730T224248Z/validation_report.json`:

- `canonical_formulas_unchanged: true`
- `freezes_unchanged: true`
- `shadow_not_promoted: true`
- `research_only / owner_only: true`
- TopN compared: 8, 10, 12
- Weight profiles: default, mass_heavy, edge_heavy, odds_heavy

Bundle: `phase2_research_bundle.json` (Top5 + TopN + weights + coupon).

---

## How to re-run

```text
python -m pytest tests/research/bet_coverage_optimizer -q
python scripts/run_bco_phase2_research.py
```

## Deployment

**Not deployed.** Awaiting explicit owner approval before any production sync.
