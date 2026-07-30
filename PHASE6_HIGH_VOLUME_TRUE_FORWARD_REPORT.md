# PHASE 6 — High-Volume True-Forward Collection

**Status: COMPLETE (infrastructure + staged production validation; research-only)**

Tip SHA: **`a13f4ba`** — Local = GitHub = Production  
Vienna target day validated: **2026-07-31**

**No promotion and no routing activation occurred.**  
Lambda V2 / Exact V2 / detectors remain `SHADOW_RESEARCH_ONLY`.

---

## 1. Final Phase 6 status

| Area | Status |
|---|---|
| Daily universe discovery + eligibility | Done |
| Deterministic diversity sampling | Done (`l2f-hv-tf-sampling-v1`) |
| Bounded HV batch (disk/idempotency/resume) | Done |
| Canonical → freeze → shadow isolation | Validated |
| Stage 1 dry-run | Pass |
| Stage 2 cap 20 | Pass (11/12 canonical; 1 odds-gate block) |
| Stage 3 cap 50 | Pass (idempotent reuse on same day slate) |
| Stage 4 cap 100 | Pass (eligible &lt; 100 → all eligible) |
| Stage 5 result follow-up | Dry-run only — all 11 pending_not_started (pre-KO) |
| Systemd timers | Documented, **not enabled** (`docs/PHASE6_HV_TF_TIMERS.md`) |

---

## 2. Full discovered fixture universe (2026-07-31)

**Discovered: 12 · Eligible: 12 · Excluded: 0**

| Fixture ID | Match | League |
|---:|---|---|
| 1556397 | Be1 NFA vs Jonava | one_lyga |
| 1556398 | Hegelmann II vs Minija | one_lyga |
| 1567860 | Admira Wacker vs Rapid Wien II | austria_2_liga |
| 1567861 | Voitsberg vs SKU Amstetten | austria_2_liga |
| 1567862 | Austria Vienna (Am) vs FC BW Linz | austria_2_liga |
| 1567866 | SV Kapfenberg vs FC Liefering | austria_2_liga |
| 1567867 | Wacker Innsbruck vs Schwarz-Weiß Bregenz | austria_2_liga |
| 1494723 | Valerenga vs Ham-Kam | eliteserien |
| 1497644 | Oddevold vs Norrby IF | superettan |
| 1567864 | Floridsdorfer AC vs SKN ST. Polten | austria_2_liga |
| 1494717 | Bodo/Glimt vs Lillestrom | eliteserien |
| 1556628 | Dundee Utd vs Rangers | scottish_premiership |

Eligible by league: austria_2_liga 6 · one_lyga 2 · eliteserien 2 · superettan 1 · scottish_premiership 1.

Artifact: `artifacts/phase6_hv_tf/2026-07-31/.../universe.json` (prod).

---

## 3. Eligibility and exclusion counts

| Bucket | Count |
|---|---:|
| Discovered | 12 |
| Eligible | 12 |
| Excluded | 0 |
| Exclusion reasons | _(none)_ |

Policy enforced: never exclude for challenger disagreement, expected performance, `no_bet`, or betting attractiveness. Odds quality is enforced at **execution** (fixture 1567862 blocked with `NO_LEGITIMATE_1X2_ODDS_AFTER_REFRESH`).

---

## 4. Sampling policy and reproducibility proof

- **Policy version:** `l2f-hv-tf-sampling-v1`
- **Seed:** `phase6-true-forward-2026`
- **Rule:** if eligible ≤ cap → select all; else hash-rank + league soft-share ≤ 20% when alternatives exist
- **Prematch-only features:** league, odds-strength / market-balance / expected-total **proxy** buckets from 1X2 snapshots
- **Proof digest (cap≥12, all selected):** `96ded79261b2d701dcc4e3721b32387e4cc90f967597d04889bbc5f96cbfd067`
- **Outcome knowledge:** not used (unit-tested)

---

## 5. Results of cap 20 / 50 / 100 stages

| Stage | Cap | Selected | Canonical OK | Shadow OK | Freeze mutations | Gate next |
|---|---:|---:|---:|---:|---:|---|
| 1 dry-run | 100 | 12 | n/a (no writes) | n/a | 0 | OK |
| 2 live | 20 | 12 | **11** (+1 odds_blocked) | **11** | **0** | may_increase_cap=true |
| 3 live | 50 | 12 | 11 | 11 | 0 | true |
| 4 live | 100 | 12 | 11 | 11 | 0 | true |

Canonical success rate stage 2: **91.7%**. Shadow success among attempted shadows: **100%**.  
Blocked: `1567862` — `NO_LEGITIMATE_1X2_ODDS_AFTER_REFRESH` (quality gate preserved).

Modes stage 2: REUSE_IMMUTABLE_FREEZE 7 · NEW_PREDICTION 4 · odds_blocked 1.

---

## 6. Daily true-forward count

For Vienna **2026-07-31**: **11** successful `true_forward` jobs (`run_id=l2f-forward-v1`).  
Eligible day slate size today is **12** (&lt;&lt; 100); HV pipeline will scale when discovery yields more owner-scope fixtures.

---

## 7. Canonical / shadow success and failure counts

| Metric | Count |
|---|---:|
| Canonical success (new + reused freeze) | 11 |
| Canonical blocked (odds gate) | 1 |
| Canonical failed | 0 |
| Shadow success (incl. idempotent) | 11 |
| Shadow failed | 0 |
| Shadow not_run (canonical blocked) | 1 |

---

## 8. Latency and provider usage

From cumulative observability on true-forward jobs:

- Median shadow latency ≈ **25 ms** (idempotent/reuse path dominates)
- p95 ≈ **19.1 s** (new shadow pipeline path)
- Enrichment warnings observed (season field / xG probe / weather) — **non-blocking**
- Provider odds gate blocked 1 fixture legitimately
- Disk remained **9.8G** free; services `worldcup-gpt-actions` + `worldcup-mcp` **active**

---

## 9. Freeze and leakage integrity proof

- All processed freezes: `prediction` / `odds` / `freeze` timestamps before kickoff (executor gates)
- `freeze_mutated_after_shadow = 0` for all 11
- `resolve_cohort_type(backfill=True)` cannot label `true_forward` (tested)
- No result data used in prematch path; follow-up classified all 11 as `pending_not_started`
- No backfill / replay flag on HV day path (`backfill=False`)

---

## 10. Storage-growth estimate and retention policy

Assumptions: ~45 KB DB + ~25 KB artifact / fixture; ~2 MB logs/day before rotation.

| Horizon @ 100 fixtures/day | Approx growth |
|---|---|
| 30 days | ~0.2 GB (+ logs) |
| 90 days | ~0.6 GB (+ logs) |
| 180 days | ~1.2 GB (+ logs) |

Retention (`storage_policy.py`):

- **Keep:** canonical predictions, immutable freezes, shadow outputs, evaluations, preregistration
- **Rotate/compress:** verbose logs (gzip 7d / drop 45d), old markdown reports, transient job JSON
- **Runtime:** stop batch if free &lt; **8G**; alert &lt; **10G**; no duplicate full-payload dumps; no large uncompressed DB backups

Current free ≈ **9.8G** → alert band; stop gate not tripped.

---

## 11. Result-follow-up status

Follow-up dry-run: **11 processed**, all `pending_not_started` (matches not kicked off yet).  
Live FT recovery + evaluation deferred until grace after kickoff (Stage 5 after FT).

---

## 12. Cumulative evaluation metrics

| Cohort | Evaluated TF | Notes |
|---|---:|---|
| `true_forward` | **0** | Waiting on FT |
| `historical_replay` | 94 model-rows | Separate; not relabeled |
| `historical_replay_result_recovered` | present | Separate |

Readiness: Exact V2 / Lambda V2 / detector = **`NOT_READY_INSUFFICIENT_TRUE_FORWARD`** (need ≥100 evaluated TF).  
`promotion_occurred=false`, `routing_activation_occurred=false`.

---

## 13. Readiness status

**NOT_READY_INSUFFICIENT_TRUE_FORWARD** for challenger promotion review.  
Operational HV collection **ready** for continued daily accumulation at cap 20→50 with disk watch; cap 100 OK when eligible universe grows, subject to 8G stop gate.

---

## 14. Local / GitHub / Production commit parity

| Mirror | SHA |
|---|---|
| Local | `a13f4bafccd78948e4f5d3c8326ff068a1c186fd` |
| GitHub | `a13f4ba` (branch `release/football-strength-shadow-infra-20260730T151432Z`) |
| Production `/opt/worldcup-predictor` | `a13f4ba` |

---

## 15. Tests and validation

`tests/research/infra_l2f_forward/test_phase6_hv_tf.py` — **10 passed** (local + production):

- deterministic sampling / no outcome-based selection
- league diversity soft-cap
- prematch classification / exclusions
- dry-run checkpoint + resume
- disk stop gate
- canonical isolation / no promotion flags
- cohort separation (no historical→true_forward relabel)

---

## 16. Explicit statement

**No promotion and no routing activation occurred.**

---

## 17. Recommendation for Phase 7 (do not start)

Phase 7 should focus on **multi-day accumulation ops + post-FT evaluation dashboards**, not model promotion:

1. Enable timers only after another ≥2 Vienna days at cap 20 with disk ≥10G headroom.
2. Wire automated Stage 5 follow-up after FT; keep cohorts separated.
3. Expand owner discovery coverage if daily eligible stays ≪100 (today 12).
4. Revisit readiness only after **≥100 evaluated true_forward** with CIs — still manual owner approval, never auto-promote.

**Do not start Phase 7 in this change set.**

---

### Key modules

- `worldcup_predictor/research/infra_l2f_forward/daily_universe.py`
- `diversity_sampling.py` · `hv_batch.py` · `hv_fixture_executor.py`
- `phase6_reports.py` · `storage_policy.py`
- `scripts/run_phase6_true_forward_day.py` · `scripts/report_phase6_true_forward.py`
- `docs/PHASE6_HV_TF_TIMERS.md`
