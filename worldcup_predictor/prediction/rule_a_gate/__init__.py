"""Rule A harmonization gate — shadow only (Phase 21A)."""

from worldcup_predictor.prediction.rule_a_gate.shadow_runner import maybe_record_rule_a_shadow
from worldcup_predictor.prediction.rule_a_gate.live_validation_runner import maybe_record_rule_a_live
from worldcup_predictor.prediction.rule_a_gate.shadow_store import RuleAShadowRecord, RuleAShadowStore

__all__ = [
    "RuleAShadowRecord",
    "RuleAShadowStore",
    "maybe_record_rule_a_shadow",
    "maybe_record_rule_a_live",
]
