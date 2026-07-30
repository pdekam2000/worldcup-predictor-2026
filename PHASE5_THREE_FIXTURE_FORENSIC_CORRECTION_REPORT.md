# PHASE 5 THREE-FIXTURE FORENSIC AUDIT & REPORT CORRECTION

**Status: COMPLETE (reporting-layer defect only; stored outputs unchanged)**

Date: 2026-07-30  
Fixtures: 1556628, 1494717, 1567860  
Tip after reporting fix: see final parity section.

**No prediction, freeze, shadow, promotion, or routing was changed.**

---

## 1. Root cause — rank/probability mismatch

**Defect class:** report/extraction cross-join (not stored canonical inconsistency).

Canonical ECSE ranks by **`independent_poisson_probability`** (`generate_score_distribution(..., use_dixon_coles=False)`), sorted descending. Snapshots store correct Top10 with matching Poisson probabilities.

The Phase 5 / research preview path (`research_preview._canonical_ecse_tops`) often saw `top_5_scores` as **score strings only**, then attached probabilities from **`dist_dc` (Dixon–Coles ON)**.  

That joins a **different distribution** onto the **Poisson rank order**, so displayed probabilities are not descending and do not match the ranking field.

| Model | Documented ranking field | Display probability must come from |
|---|---|---|
| Canonical ECSE | `independent_poisson_probability` | Independent Poisson (same as rank) |
| Exact V2 SELECTED | `dixon_coles_probability` | Dixon–Coles (already consistent) |

**Not:** stale ranks, intentional non-prob ranking, or corrupted freezes.

**Fix applied (read-only extraction only):** prefer `top_10_scorelines` (rank+prob); if probs missing, join **Poisson** map only — never DC onto canonical ranks.

---

## 2. Root cause — Dundee WDE decision vs argmax

| Field | Value |
|---|---|
| WDE probabilities H/D/A | 25.8 / 25.6 / 48.6 |
| Raw argmax | **away_win** |
| Stored / displayed decision | **draw** (`prediction`, `detailed_markets.match_winner.selection`) |
| no_bet | **True** |
| Override | Yes |

Canonical WDE does **not** set 1X2 selection by probability argmax. Final selection comes from `WeightedDecisionEngine._resolve_1x2` (home-edge bands + optional draw preference / calibration). Abstention gate sets `no_bet=true`.

This is **genuine stored canonical semantics**, not a report join bug. Prior reports under-specified by showing only `decision` without `raw_argmax` / `decision_policy`.

Reporting now exposes:

- `raw_argmax` / `probability_argmax`
- `canonical_decision`
- `decision_policy`
- `decision_override_reason` (when decision ≠ argmax)

Canonical decision logic was **not** changed.

---

## 3. Corrected Top1–Top5 (all three fixtures)

### 1556628 Dundee United vs Rangers

**Canonical** ranking_field=`independent_poisson_probability`

| Rank | Score | Displayed p (= ranking score) |
|---:|---|---:|
| 1 | 0-1 | 0.190123 |
| 2 | 0-2 | 0.162838 |
| 3 | 0-0 | 0.110991 |
| 4 | 0-3 | 0.092979 |
| 5 | 1-1 | 0.092275 |

**Exact V2** ranking_field=`dixon_coles_probability`

| Rank | Score | Displayed p |
|---:|---|---:|
| 1 | 0-2 | 0.129232 |
| 2 | 0-3 | 0.105632 |
| 3 | 1-2 | 0.089788 |
| 4 | 1-1 | 0.082751 |
| 5 | 1-3 | 0.073391 |

Phase 5 bug display had Canonical Top1 p=0.148 / Top2 p=0.163 (DC probs on Poisson order).

### 1494717 Bodø/Glimt vs Lillestrøm

**Canonical**

| Rank | Score | p |
|---:|---|---:|
| 1 | 2-0 | 0.192537 |
| 2 | 1-0 | 0.162299 |
| 3 | 3-0 | 0.152272 |
| 4 | 4-0 | 0.090321 |
| 5 | 0-0 | 0.068405 |

**Exact V2**

| Rank | Score | p |
|---:|---|---:|
| 1 | 2-0 | 0.155697 |
| 2 | 3-0 | 0.152556 |
| 3 | 4-0 | 0.112109 |
| 4 | 5-0 | 0.065908 |
| 5 | 1-0 | 0.065454 |

(Phase 5 wrongly showed Canonical Top2 p=0.112 from DC while rank stayed 1-0.)

### 1567860 Admira Wacker vs Rapid Wien II

**Canonical**

| Rank | Score | p |
|---:|---|---:|
| 1 | 1-0 | 0.153346 |
| 2 | 0-0 | 0.146730 |
| 3 | 1-1 | 0.134035 |
| 4 | 0-1 | 0.128253 |
| 5 | 2-0 | 0.080130 |

**Exact V2**

| Rank | Score | p |
|---:|---|---:|
| 1 | 1-1 | 0.138611 |
| 2 | 2-1 | 0.088933 |
| 3 | 0-0 | 0.085702 |
| 4 | 1-0 | 0.082080 |
| 5 | 1-2 | 0.074380 |

(Phase 5 bug: Canonical Top1 p=0.133 / Top2 p=0.164 — DC on Poisson order.)

---

## 4. Correct raw WDE argmax and canonical decision

| Fixture | WDE H/D/A | Raw argmax | Stored decision | Override | Policy |
|---|---|---|---|---|---|
| 1556628 Dundee–Rangers | 25.8 / 25.6 / 48.6 | **away_win** | **draw** | Yes | `wde_edge_resolve_1x2_not_probability_argmax` (+ no_bet) |
| 1494717 Bodø–Lillestrøm | 85.1 / 10.7 / 4.2 | **home_win** | **home_win** | No | probability_argmax aligned |
| 1567860 Admira–Rapid II | 13.2 / 21.4 / 65.5 | **away_win** | **away_win** | No | probability_argmax aligned (no_bet still true) |

---

## 5. Full-distribution 1X2 mass (not Top5-only)

| Fixture | Canonical H/D/A mass | Can dir | Exact V2 H/D/A mass | Exact dir | WDE argmax | WDE decision |
|---|---|---|---|---|---|---|
| 1556628 | 0.100 / 0.224 / 0.676 | away_win | 0.083 / 0.173 / 0.723 | away_win | away_win | draw |
| 1494717 | 0.834 / 0.129 / 0.035 | home_win | 0.832 / 0.100 / 0.027 | home_win | home_win | home_win |
| 1567860 | 0.388 / 0.315 / 0.297 | home_win | 0.407 / 0.290 / 0.303 | home_win* | away_win | away_win |

\*Exact V2 full-mass is home-leaning; Exact Top1 is 1-1 (draw) — Top1 ≠ full-mass argmax (truncation artifact). WDE away vs score-mass home = genuine disagreement.

**Conflict classification:**

- **Dundee:** WDE decision vs argmax = **genuine WDE policy** (edge resolve + no_bet). ECSE/Exact full-mass both **away_win** — agreement on direction; report previously looked more confused due to Top5 DC join.
- **Bodø:** Models agree home; no display bug material to conclusions.
- **Admira:** WDE away vs ECSE Top1 home / Exact Top1 draw = **genuine model disagreement** (plus truncated-Top5 ≠ full mass). Not only a display bug.

---

## 6. Do prior Phase 5 conclusions change?

| Conclusion | Change? |
|---|---|
| Dundee NO_BET / WATCHLIST | **No** (no_bet still true) |
| Best-supported Dundee 1X2 lean **away** | **Strengthened** (full-mass + argmax away; decision=draw is policy/abstention, not market favourite) |
| Bodø RESEARCH_CANDIDATE home / Top1 2-0 agree | **No material change** |
| Admira NO_BET / conflict | **No** — still conflict; corrected probs make ECSE Top1 1-0 clearer vs WDE away |
| Exact V2 Top lists | **Unchanged** (already DC-consistent) |
| Canonical Top1 scorelines | **Unchanged** (ranks were already correct; only displayed p fixed) |

Original Phase 5 artifact was **not overwritten**. Correction lives in this report + `artifacts/phase5_three_fixture_forensic_*`.

---

## 7–8. Freeze / shadow hashes before and after

Read-only extract confirmed freeze + Exact V2 hashes; correction recompute does not write prediction/freeze/shadow tables.

| Fixture | Freeze ID | Freeze hash (prefix) | Exact V2 hash (prefix) |
|---|---|---|---|
| 1556628 | `04a82bb7-…` | `874cc97aee33d3c9…` | `282ebd2a9b9e51ec…` |
| 1494717 | `2061f78e-…` | `d86184bfbf4098fa…` | `d8a83cea35ea2619…` |
| 1567860 | `5dc8e770-…` | `5d27a1e4bfa54f39…` | `4479ca6fc6b39994…` |

**hashes_unchanged = True** after forensic recompute (no DB mutation).

---

## 9. Tests

`tests/research/infra_l2f_forward/test_phase5_rank_probability_forensic.py` (+ existing preview tests):

- Canonical ranking field ≠ DC for Dundee-like lambdas
- Canonical Top5 descending on Poisson probs; row-aligned
- Documented DC-on-Poisson cross-join is non-descending
- Exact V2 tops descending on DC
- WDE raw argmax vs decision_pick
- Side-by-side comparison preserves score/prob pairing

**9 passed** locally with preview suite.

---

## 10. Commit parity

Reporting fix commit will be recorded after push/deploy. Production deploy is **reporting-only** (`research_preview.py` + tests + this report).

---

## 11. Explicit confirmation

**No prediction, freeze, shadow row, promotion, or routing activation was changed.**  
Defect confined to owner research preview / report extraction. Canonical ranking semantics unchanged.
