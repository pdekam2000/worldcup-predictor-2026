# CHALLENGER PHASE 3B — GBGM FORENSIC REPORT

## Final status: `GBGM_IMPROVED_CHALLENGER_READY`

### Why GBGM-1 underperforms league baseline
1. **Weak feature set**: L5 rolling goals + league means only; no xG/shots/Elo in v1.
2. **Constant `is_home=1.0`**: non-informative feature baked into GBGM-1.
3. **Domain mix**: PL/BL (~3.2 goals/game) mixed with WC/CL (~2.7) without strong league context.
4. **Overconfident booster**: holdout accuracy ≈ baseline but LogLoss worse → calibration/noise.
5. **Independent Poisson**: draw mass systematically thin vs empirical draws.

### Phase 3B actions
- Reproduced Phase 3 holdout exactly (no pre-improvement changes).
- Audited targets/features/missingness/domains.
- Ran experiment matrix A–H + temperature calibration (val-only fit).
- Ablation + error forensics.
- Forward policy: pause weak GBGM-1 accumulation; activate improved shadow candidate.

### Selection: `H` (Team strength + Bivariate Poisson) — beats league=True

| Model | Holdout 1X2 LogLoss | Holdout Brier |
| ----- | ------------------- | ------------- |
| League baseline (A) | 1.068 | 0.647 |
| GBGM-1-NM (Phase 3) | 1.197 | 0.710 |
| GBGM-NM-v2 (D) | 1.011 | 0.603 |
| Team strength (B) | 1.009 | 0.603 |
| **B + Bivariate Poisson (H)** | **1.009** | **0.603** |

Critical finding: improved GBMs do **not** beat simple attack/defence Poisson. Boosting added noise on this feature set. Market E/F matched NM (usable prematch odds effectively absent in research snapshots).

- Manifest NM hash: `a1bc4bcefa326e9625f11aedbe0bdbfa9ffe09a97e85e0bf4681585aea92a7f7`
- Manifest MC hash: `13ecea05276c153576277210be380db26410c45e0afa2a1354c05d39d5a00768`

Canonical WDE/ECSE/BTTS/O-U untouched. Shadow only. Active shadow candidate = team-strength + bivariate Poisson (not GBGM-1 booster). GBGM-1 new forward generation paused; history preserved.

**STATUS: `GBGM_IMPROVED_CHALLENGER_READY`**
