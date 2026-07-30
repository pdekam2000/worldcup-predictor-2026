# PHASE 5 — Live True-Forward Accumulation and Owner Research Preview

**Status: COMPLETE (research-only; no promotion / no routing activation)**

Vienna target date: **2026-07-31** (tomorrow relative to 2026-07-30 CEST).

## 1. Phase 5 status

Phase 5 ran the naturally occurring tomorrow owner-scope slate through the canonical full-day pipeline, captured **5/5** eligible freezes as `cohort_type=true_forward`, wrote Lambda V2 + Exact V2 shadow rows, and published an owner-only read-only Canonical vs Shadow research preview.

Result follow-up (Part F) is **deferred** until FT results exist — matches have not kicked off yet.

## 2. Tomorrow discovered fixture count

**5** supported owner-scope fixtures (Tier B = 5, Tier A = 0).

| fixture_id | Match | League | Kickoff UTC | Kickoff Vienna |
|---:|---|---|---|---|
| 1556397 | Be1 NFA vs Jonava | one_lyga | 2026-07-31T15:30:00Z | 17:30 CEST |
| 1556398 | Hegelmann II vs Minija | one_lyga | 2026-07-31T16:00:00Z | 18:00 CEST |
| 1494723 | Valerenga vs Ham-Kam | eliteserien | 2026-07-31T17:00:00Z | 19:00 CEST |
| 1497644 | Oddevold vs Norrby IF | superettan | 2026-07-31T17:00:00Z | 19:00 CEST |
| 1494717 | Bodo/Glimt vs Lillestrom | eliteserien | 2026-07-31T19:00:00Z | 21:00 CEST |

Discovery exclusions for this slate: **0** (no friendlies / unsupported / post-KO in the entering set).

## 3. Eligible canonical prediction count

**5** complete canonical predictions + **5** new immutable freezes (eval DB 318 → 323).

## 4. Blocked / skipped count with reasons

| Bucket | Count | Notes |
|---|---:|---|
| Discovery exclusions | 0 | — |
| Odds / gate blocked from prediction | 0 | All 5 entered jobs |
| True-forward skipped/blocked/failed | 0 | — |
| True-forward success | 5 | `true_forward_success` |

Transient enrichment warnings during jobs (season field / xG probe / weather) did **not** block canonical freezes or TF shadow.

## 5. True-forward rows created

**5** successful `l2f_forward_shadow_jobs` with `run_id=l2f-forward-v1`, `cohort_type=true_forward`.

## 6. Lambda V2 rows created

**4 Lambda V2 models × 5 fixtures = 20** new Lambda shadow rows for this slate  
(`LAMBDA_V2_FOOTBALL`, `LAMBDA_V2_MARKET_TOTAL`, `LAMBDA_V2_BLENDED`, `LAMBDA_V2_BLENDED_ADAPTIVE`).

## 7. Exact V2 rows created

**4 Exact V2 models × 5 fixtures = 20** new Exact shadow rows for this slate  
(`EXACT_V2_POISSON`, `EXACT_V2_DC`, `EXACT_V2_OVERDISPERSED`, `EXACT_V2_SELECTED`).

## 8. Complete prediction table (eligible fixtures)

Labels: **CANONICAL** = official; **SHADOW_RESEARCH_ONLY** = challenger preview only.

### 1556397 — Be1 NFA vs Jonava (one_lyga)

- Odds H/D/A: **1.75 / 3.70 / 3.85** · books **9** · `ODDS_FRESH` · ts `2026-07-30T20:41:23Z` · age ~8.8m
- CANONICAL WDE: **home_win** · conf **49.9** · no_bet **True**
- CANONICAL λ: 1.796 / 0.817 / **2.613**
- Lambda V2 (adaptive): 2.076 / 0.944 / **3.020**
- Agreement: **RESEARCH_ONLY_NO_BET** (tags include MODELS_CONFLICT, EXACT_V2_HIGH_GOAL_SHIFT)
- TF job: success · freeze `4a5b563e-…`

### 1556398 — Hegelmann II vs Minija (one_lyga)

- Odds H/D/A: **19.0 / 8.0 / 1.08** · books **10** · `ODDS_FRESH` · ts `2026-07-30T20:41:59Z`
- CANONICAL WDE: **away_win** · conf **55.5** · no_bet **True**
- CANONICAL λ: 0.164 / 2.886 / **3.050**
- Lambda V2: 0.164 / 2.885 / **3.049**
- Agreement: **RESEARCH_ONLY_NO_BET** (also MODELS_AGREE on exact Top1)
- TF job: success · freeze `98652514-…`

### 1494723 — Valerenga vs Ham-Kam (eliteserien)

- Odds H/D/A: **1.57 / 4.30 / 5.00** · books **13** · `ODDS_FRESH`
- CANONICAL WDE: **draw** · conf **58.1** · no_bet **True**
- CANONICAL λ: 1.685 / 0.529 / **2.214**
- Lambda V2: 2.608 / 0.819 / **3.427**
- Agreement: **RESEARCH_ONLY_NO_BET**
- TF job: success · freeze `b48419cd-…`

### 1497644 — Oddevold vs Norrby IF (superettan)

- Odds H/D/A: **1.67 / 3.85 / 4.50** · books **13** · `ODDS_FRESH`
- CANONICAL WDE: **home_win** · conf **49.4** · no_bet **True**
- CANONICAL λ: 1.486 / 0.551 / **2.037**
- Lambda V2: 1.965 / 0.729 / **2.695**
- Agreement: **RESEARCH_ONLY_NO_BET**
- TF job: success · freeze `29e02288-…`

### 1494717 — Bodo/Glimt vs Lillestrom (eliteserien)

- Odds H/D/A: **1.24 / 6.45 / 9.50** · books **13** · `ODDS_FRESH`
- CANONICAL WDE: **home_win** · conf **67.8** · no_bet **False**
- CANONICAL λ: 2.373 / 0.310 / **2.682**
- Lambda V2: 2.939 / 0.384 / **3.323**
- Agreement: **EXACT_V2_HIGH_GOAL_SHIFT** (Top1 agrees on 2-0; Exact shifts mass upward)
- TF job: success · freeze `2061f78e-…`

Full structured JSON: `artifacts/phase5_true_forward/research_preview_2026-07-31.json` (production) / local copy `artifacts/phase5_true_forward_research_preview_2026-07-31.json`.

## 9. Canonical vs Exact V2 Top1–Top5 side-by-side

### 1494717 Bodo/Glimt vs Lillestrom

| Rank | Canonical score | Canonical p | Exact V2 score | Exact V2 p |
|---:|---|---:|---|---:|
| 1 | 2-0 | 0.1925 | 2-0 | 0.1557 |
| 2 | 1-0 | 0.1122 | 3-0 | 0.1526 |
| 3 | 3-0 | 0.1523 | 4-0 | 0.1121 |
| 4 | 4-0 | 0.0903 | 5-0 | 0.0659 |
| 5 | 0-0 | 0.0749 | 1-0 | 0.0655 |

Top1 agree **Yes** · Top3 overlap **2** · Top5 overlap **4** · Top1 distance **0** · high-score tail Δ **+0.135**

### 1494723 Valerenga vs Ham-Kam

| Rank | Canonical | p | Exact V2 | p |
|---:|---|---:|---|---:|
| 1 | 1-0 | 0.1438 | 2-0 | 0.1105 |
| 2 | 2-0 | 0.1551 | 3-0 | 0.0960 |
| 3 | 0-0 | 0.1219 | 2-1 | 0.0905 |
| 4 | 1-1 | 0.1101 | 3-1 | 0.0787 |
| 5 | 3-0 | 0.0871 | 1-1 | 0.0784 |

Top1 agree **No** · Top3 **1** · Top5 **3** · dist **1** · tail Δ **+0.259**

### 1497644 Oddevold vs Norrby IF

| Rank | Canonical | p | Exact V2 | p |
|---:|---|---:|---|---:|
| 1 | 1-0 | 0.1563 | 2-0 | 0.1305 |
| 2 | 2-0 | 0.1439 | 1-1 | 0.1094 |
| 3 | 0-0 | 0.1443 | 1-0 | 0.0988 |
| 4 | 1-1 | 0.1207 | 2-1 | 0.0952 |
| 5 | 2-1 | 0.0794 | 3-0 | 0.0855 |

Top1 agree **No** · Top3 **2** · Top5 **4** · dist **1** · tail Δ **+0.134**

### 1556397 Be1 NFA vs Jonava

| Rank | Canonical | p | Exact V2 | p |
|---:|---|---:|---|---:|
| 1 | 1-0 | 0.1010 | 1-1 | 0.1081 |
| 2 | 2-0 | 0.1183 | 2-0 | 0.1052 |
| 3 | 1-1 | 0.1215 | 2-1 | 0.0993 |
| 4 | 2-1 | 0.0966 | 1-0 | 0.0740 |
| 5 | 0-0 | 0.0873 | 3-0 | 0.0728 |

Top1 agree **No** · Top3 **2** · Top5 **4** · dist **1** · tail Δ **+0.090**

### 1556398 Hegelmann II vs Minija

| Rank | Canonical | p | Exact V2 | p |
|---:|---|---:|---|---:|
| 1 | 0-2 | 0.1972 | 0-2 | 0.1973 |
| 2 | 0-3 | 0.1897 | 0-3 | 0.1897 |
| 3 | 0-4 | 0.1369 | 0-4 | 0.1369 |
| 4 | 0-1 | 0.0854 | 0-1 | 0.0854 |
| 5 | 0-5 | 0.0790 | 0-5 | 0.0790 |

Top1 agree **Yes** · Top3 **3** · Top5 **5** · dist **0** · tail Δ **~0**

These comparison metrics **do not** alter canonical routing.

## 10. Model agreement classification (every fixture)

| fixture_id | Primary classification |
|---:|---|
| 1556397 | RESEARCH_ONLY_NO_BET |
| 1556398 | RESEARCH_ONLY_NO_BET |
| 1494723 | RESEARCH_ONLY_NO_BET |
| 1497644 | RESEARCH_ONLY_NO_BET |
| 1494717 | EXACT_V2_HIGH_GOAL_SHIFT |

## 11. Freeze and leakage integrity proof

| Check | Result |
|---|---|
| prediction_timestamp < kickoff | **PASS** (5/5) |
| freeze_timestamp < kickoff | **PASS** (5/5) |
| odds_timestamp < kickoff | **PASS** (5/5; fresh prematch snapshots) |
| immutable freeze identity | **PASS** (5/5) |
| cohort_type=true_forward | **PASS** (5/5) |
| no historical/backfill run_id | **PASS** (`l2f-forward-v1`) |
| no result leakage in shadow payloads | **PASS** |
| prior freezes unchanged | **PASS** — hash of 318 pre-run freezes remains `81ce14eadbf4ed07ceae65860d82eeff8e632e5de3e350f37edcab7380cb9b40` |
| per-fixture freeze hash unchanged after shadow | **PASS** |
| shadow exceptions cannot fail canonical | **PASS** (isolated hook + try/except) |
| disk before/after | **9.8G free** (≥8G gate) |
| large uncompressed DB backup | **not created** |

Part F result evaluation: **not performed** (no FT results yet). Use `scripts/run_l2f_true_forward_followup.py` after matches finish; cohort remains `true_forward`.

## 12. Files modified

- `scripts/run_owner_full_day_predictions.py` — post-freeze true_forward hook + poll harden
- `worldcup_predictor/research/infra_l2f_forward/agreement.py` — agreement classifications
- `worldcup_predictor/research/infra_l2f_forward/research_preview.py` — owner side-by-side builder
- `scripts/report_l2f_research_preview.py` — CLI preview
- `worldcup_predictor/gpt_actions/app.py` — owner-auth `GET …/research/l2f-research-preview`
- `tests/research/infra_l2f_forward/test_phase5_research_preview.py`
- `PHASE5_LIVE_TRUE_FORWARD_REPORT.md` (this file)

## 13. Tests and validation

- `pytest tests/research/infra_l2f_forward` → **30 passed** (local + production)
- Full-day run exit **0** · `OWNER_FULL_DAY_PREDICTION_MODE_READY`
- Preview filter `--vienna-date 2026-07-31` → **count=5**
- Services after restart: `worldcup-api` / `worldcup-gpt-actions` / `nginx` **active**

Owner preview CLI:

```text
python scripts/report_l2f_research_preview.py --vienna-date 2026-07-31
```

Owner-auth GPT route (read-only; docs/OpenAPI intentionally disabled on gpt-actions):

```text
GET /api/gpt-actions/v1/research/l2f-research-preview?vienna_date=2026-07-31
```

## 14. Local / GitHub / Production commit hashes

| Location | SHA |
|---|---|
| Local | `dd23390` |
| GitHub (`release/football-strength-shadow-infra-20260730T151432Z`) | `dd23390` |
| Production `/opt/worldcup-predictor` | `dd23390` |

Tip message: *Document Phase 5 live true-forward accumulation and research preview.*

Code tip for TF hook + preview (before docs commit): `3b1293f`.

## 15. Challenger outputs remain research-only

**Explicit statement:** Lambda V2, Exact V2, and all agreement / Top1–Top5 comparison outputs from Phase 5 are **SHADOW_RESEARCH_ONLY**. They do **not** replace public canonical WDE/ECSE output, are **not** official predictions, were **not** promoted, and do **not** activate routing.
