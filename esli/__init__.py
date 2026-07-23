"""ExactScoreLeagueIntelligence (ESLI) — FORWARD SHADOW candidate-selection layer.

ESLI is NOT a prediction model. It is a read-only league-suitability + candidate
selection/ranking layer that sits *beside* the canonical WDE/ECSE/BTTS/O-U pipeline.

Hard invariants (enforced by validate_esli_forward_shadow_and_top3_combo.py):
  - ESLI never mutates ECSE probabilities/ranks/Top1-Top5/Top10/lambda.
  - ESLI never mutates WDE/BTTS/O-U/no_bet/odds-gates/freezes/evaluations.
  - ESLI is shadow only: public_visible=false, final_decision_authority=false.
  - ESLI may only affect: owner research candidate ranking + exact-score combo eligibility.
"""

MODEL_ID = "ESLI-1"
MODEL_NAME = "Exact Score League Intelligence"
MODEL_VERSION = "1.0.0"
STATUS = "FORWARD_SHADOW"
IS_SHADOW = True
PUBLIC_VISIBLE = False
FINAL_DECISION_AUTHORITY = False
POLICY_VERSION = "esli-policy-v1"
RESEARCH_SOURCE = "artifacts/research (ESLI read-only audit, n=94 forward-evaluated fixtures)"
