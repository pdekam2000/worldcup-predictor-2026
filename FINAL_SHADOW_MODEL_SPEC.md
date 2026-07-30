# Final shadow model spec

## Models
- L: Dixon–Coles dynamic grid (`hst-L-dc-dynamic-v1`)
- H: Ensemble NB/hurdle/market/blowout (`hst-H-ensemble-v1`)
- Regime selector: prematch score → LOW/HIGH/UNCLEAR
- WDE shadow: ECSE direction diagnostic

## Persistence
- Table: `high_score_tail_shadow_outputs`
- Never writes to `frozen_predictions`

## Display rule
- Always show canonical ECSE
- Additionally show L, H, selected regime, diagnostics