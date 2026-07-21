"""Centralized no_bet reason evaluator — Phase 2.

Computes active reasons from the *final* prediction state after adaptive enrichment.
Does not OR inherited sticky booleans. A reason clears only when its condition is false.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from worldcup_predictor.decision.no_bet_reasons import (
    CONFIDENCE_NO_BET_THRESHOLD,
    SCORING_DATA_QUALITY_THRESHOLD,
    VISIBILITY_DATA_QUALITY_THRESHOLD,
    WDE_DATA_QUALITY_NO_BET_THRESHOLD,
    NoBetReason,
    NoBetSourceStage,
    normalize_reason_code,
    ordered_reason_codes,
)

DECISION_STAGE_FINAL: str = "FINAL_POST_ENRICHMENT"

# Conflict codes that remain blocking when explicitly present in model_conflicts.
_BLOCKING_CONFLICT_CODES: frozenset[str] = frozenset(
    {
        NoBetReason.MODEL_CONFLICT.value,
        NoBetReason.WDE_ECSE_CONFLICT.value,
        NoBetReason.HIGH_CONFLICT.value,
        "model_conflict",
        "wde_ecse_conflict",
        "high_conflict",
    }
)


@dataclass(frozen=True, slots=True)
class NoBetReasonDetail:
    code: str
    source_stage: str
    observed_value: float | str | bool | None = None
    threshold: float | str | None = None
    clearable: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NoBetDecision:
    no_bet: bool
    active_reasons: list[str] = field(default_factory=list)
    cleared_reasons: list[str] = field(default_factory=list)
    retained_reasons: list[str] = field(default_factory=list)
    recomputed: bool = True
    decision_stage: str = DECISION_STAGE_FINAL
    reason_details: list[NoBetReasonDetail] = field(default_factory=list)
    baseline_no_bet: bool | None = None
    final_no_bet: bool | None = None

    def to_diagnostics(self) -> dict[str, Any]:
        """Owner / research diagnostics payload (additive, no secrets)."""
        return {
            "no_bet": self.no_bet,
            "no_bet_recomputed": self.recomputed,
            "no_bet_decision_stage": self.decision_stage,
            "no_bet_reasons": list(self.active_reasons),
            "no_bet_reason_details": [d.to_dict() for d in self.reason_details],
            "no_bet_cleared_reasons": list(self.cleared_reasons),
            "no_bet_retained_reasons": list(self.retained_reasons),
            "baseline_no_bet": self.baseline_no_bet,
            "final_no_bet": self.final_no_bet if self.final_no_bet is not None else self.no_bet,
        }


def _norm_inherited(inherited_reasons: Iterable[str] | None) -> list[NoBetReason]:
    out: list[NoBetReason] = []
    seen: set[NoBetReason] = set()
    for raw in inherited_reasons or []:
        code = normalize_reason_code(raw)
        if code is None or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _detail(
    reason: NoBetReason,
    *,
    observed_value: float | str | bool | None = None,
    threshold: float | str | None = None,
    source_stage: str | None = None,
) -> NoBetReasonDetail:
    meta = reason.meta
    return NoBetReasonDetail(
        code=reason.value,
        source_stage=source_stage or meta.source_stage.value,
        observed_value=observed_value,
        threshold=threshold,
        clearable=meta.clearable,
        description=meta.user_facing_description,
    )


def evaluate_no_bet_reasons(
    *,
    confidence: float | None,
    confidence_level: str | None = None,
    wde_data_quality: float | None = None,
    visibility_data_quality: float | None = None,
    scoring_data_quality: float | None = None,
    odds_status: str | None = None,
    placeholder: bool = False,
    fixture_started: bool = False,
    unsupported_fixture: bool = False,
    unsupported_market: bool = False,
    model_conflicts: list[str] | None = None,
    manual_block: bool = False,
    inherited_reasons: list[str] | None = None,
    provider_data_invalid: bool = False,
    insufficient_prematch_data: bool = False,
    invalid_prediction_state: bool = False,
    baseline_no_bet: bool | None = None,
    decision_stage: str = DECISION_STAGE_FINAL,
) -> NoBetDecision:
    """Evaluate active no_bet reasons from final prediction state.

    Rules:
    - Final confidence is evaluated after enrichment (caller responsibility).
    - Inherited sticky boolean alone is NOT a reason and does not force no_bet.
    - A clearable reason clears only when its condition is demonstrably false.
    - MANUAL_BLOCK and LEGACY_UNKNOWN_REASON never auto-clear.
    """
    _ = confidence_level  # reserved for future level-specific gates; numeric 60 covers LOW

    inherited = _norm_inherited(inherited_reasons)
    active: list[NoBetReason] = []
    details: list[NoBetReasonDetail] = []

    conf = float(confidence) if confidence is not None else None
    wde_dq = float(wde_data_quality) if wde_data_quality is not None else None
    vis_dq = float(visibility_data_quality) if visibility_data_quality is not None else None
    scoring_dq = float(scoring_data_quality) if scoring_data_quality is not None else None

    def _add(reason: NoBetReason, **kwargs: Any) -> None:
        if reason not in active:
            active.append(reason)
            details.append(_detail(reason, **kwargs))

    # --- Current-state gates (always evaluated) ---
    if conf is not None and conf < CONFIDENCE_NO_BET_THRESHOLD:
        _add(
            NoBetReason.CONFIDENCE_BELOW_60,
            observed_value=round(conf, 2),
            threshold=CONFIDENCE_NO_BET_THRESHOLD,
            source_stage=NoBetSourceStage.FINAL_POST_ENRICHMENT.value,
        )

    if wde_dq is not None and wde_dq < WDE_DATA_QUALITY_NO_BET_THRESHOLD:
        _add(
            NoBetReason.WDE_DATA_QUALITY_BELOW_50,
            observed_value=round(wde_dq, 2),
            threshold=WDE_DATA_QUALITY_NO_BET_THRESHOLD,
        )

    if vis_dq is not None and vis_dq < VISIBILITY_DATA_QUALITY_THRESHOLD:
        _add(
            NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45,
            observed_value=round(vis_dq, 2),
            threshold=VISIBILITY_DATA_QUALITY_THRESHOLD,
            source_stage=NoBetSourceStage.PICK_VISIBILITY.value,
        )

    if scoring_dq is not None and scoring_dq < SCORING_DATA_QUALITY_THRESHOLD:
        _add(
            NoBetReason.SCORING_DATA_QUALITY_BELOW_45,
            observed_value=round(scoring_dq, 2),
            threshold=SCORING_DATA_QUALITY_THRESHOLD,
        )

    if placeholder:
        _add(NoBetReason.PLACEHOLDER_DATA, observed_value=True)

    odds = (odds_status or "").strip().lower()
    if odds in {"stale", "stale_odds"}:
        _add(NoBetReason.STALE_ODDS, observed_value=odds_status)
    elif odds in {"incomplete", "incomplete_odds"}:
        _add(NoBetReason.INCOMPLETE_ODDS, observed_value=odds_status)
    elif odds in {"missing", "missing_odds", "unavailable"}:
        _add(NoBetReason.MISSING_ODDS, observed_value=odds_status)

    if fixture_started:
        _add(NoBetReason.FIXTURE_ALREADY_STARTED, observed_value=True)

    if unsupported_fixture:
        _add(NoBetReason.UNSUPPORTED_FIXTURE, observed_value=True)

    if unsupported_market:
        _add(NoBetReason.UNSUPPORTED_MARKET, observed_value=True)

    if provider_data_invalid:
        _add(NoBetReason.PROVIDER_DATA_INVALID, observed_value=True)

    if insufficient_prematch_data:
        _add(NoBetReason.INSUFFICIENT_PREMATCH_DATA, observed_value=True)

    if invalid_prediction_state:
        _add(NoBetReason.INVALID_PREDICTION_STATE, observed_value=True)

    if manual_block:
        _add(
            NoBetReason.MANUAL_BLOCK,
            observed_value=True,
            source_stage=NoBetSourceStage.MANUAL.value,
        )

    for raw in model_conflicts or []:
        code = normalize_reason_code(raw)
        token = str(raw).strip().lower()
        if code in (
            NoBetReason.MODEL_CONFLICT,
            NoBetReason.WDE_ECSE_CONFLICT,
            NoBetReason.HIGH_CONFLICT,
        ):
            _add(code, observed_value=raw)
        elif token in _BLOCKING_CONFLICT_CODES or "conflict" in token:
            # Only treat as HIGH_CONFLICT when explicitly flagged high / governed.
            if "wde" in token and "ecse" in token:
                _add(NoBetReason.WDE_ECSE_CONFLICT, observed_value=raw)
            elif "high" in token:
                _add(NoBetReason.HIGH_CONFLICT, observed_value=raw)
            else:
                _add(NoBetReason.MODEL_CONFLICT, observed_value=raw)

    # --- Inherited reason retention / clearance ---
    cleared: list[NoBetReason] = []
    retained: list[NoBetReason] = []

    def _condition_still_true(reason: NoBetReason) -> bool | None:
        """Return True if still active, False if demonstrably cleared, None if unknown."""
        if reason == NoBetReason.CONFIDENCE_BELOW_60:
            if conf is None:
                return None
            return conf < CONFIDENCE_NO_BET_THRESHOLD
        if reason == NoBetReason.WDE_DATA_QUALITY_BELOW_50:
            if wde_dq is None:
                return None
            return wde_dq < WDE_DATA_QUALITY_NO_BET_THRESHOLD
        if reason == NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45:
            if vis_dq is None:
                return None
            return vis_dq < VISIBILITY_DATA_QUALITY_THRESHOLD
        if reason == NoBetReason.SCORING_DATA_QUALITY_BELOW_45:
            if scoring_dq is None:
                return None
            return scoring_dq < SCORING_DATA_QUALITY_THRESHOLD
        if reason == NoBetReason.PLACEHOLDER_DATA:
            return bool(placeholder)
        if reason == NoBetReason.STALE_ODDS:
            return odds in {"stale", "stale_odds"}
        if reason == NoBetReason.INCOMPLETE_ODDS:
            return odds in {"incomplete", "incomplete_odds"}
        if reason == NoBetReason.MISSING_ODDS:
            return odds in {"missing", "missing_odds", "unavailable"}
        if reason == NoBetReason.FIXTURE_ALREADY_STARTED:
            return bool(fixture_started)
        if reason == NoBetReason.UNSUPPORTED_FIXTURE:
            return bool(unsupported_fixture)
        if reason == NoBetReason.UNSUPPORTED_MARKET:
            return bool(unsupported_market)
        if reason == NoBetReason.PROVIDER_DATA_INVALID:
            return bool(provider_data_invalid)
        if reason == NoBetReason.INSUFFICIENT_PREMATCH_DATA:
            return bool(insufficient_prematch_data)
        if reason == NoBetReason.INVALID_PREDICTION_STATE:
            return bool(invalid_prediction_state)
        if reason == NoBetReason.MANUAL_BLOCK:
            return True  # never auto-clear
        if reason == NoBetReason.LEGACY_UNKNOWN_REASON:
            return True  # never auto-clear
        if reason in (
            NoBetReason.MODEL_CONFLICT,
            NoBetReason.WDE_ECSE_CONFLICT,
            NoBetReason.HIGH_CONFLICT,
        ):
            # Cleared only when no longer listed in model_conflicts.
            if not model_conflicts:
                return False
            return True
        return None

    for reason in inherited:
        still = _condition_still_true(reason)
        if still is False and reason.meta.clearable:
            cleared.append(reason)
            continue
        if still is True or still is None:
            # Unknown → retain as LEGACY if non-clearable path; else keep / promote.
            if still is None and reason.meta.clearable:
                # Evidence missing to prove clearance → treat as legacy unknown block.
                retained.append(NoBetReason.LEGACY_UNKNOWN_REASON)
                _add(
                    NoBetReason.LEGACY_UNKNOWN_REASON,
                    observed_value=reason.value,
                    source_stage=NoBetSourceStage.LEGACY.value,
                )
            else:
                retained.append(reason)
                if reason not in active:
                    _add(reason, observed_value="retained_from_inherited")

    # Deterministic ordering
    active_ordered = [NoBetReason(c) for c in ordered_reason_codes(active)]
    details_by_code = {d.code: d for d in details}
    details_ordered = [details_by_code[r.value] for r in active_ordered if r.value in details_by_code]

    no_bet = len(active_ordered) > 0
    return NoBetDecision(
        no_bet=no_bet,
        active_reasons=[r.value for r in active_ordered],
        cleared_reasons=ordered_reason_codes(cleared),
        retained_reasons=ordered_reason_codes(retained),
        recomputed=True,
        decision_stage=decision_stage,
        reason_details=details_ordered,
        baseline_no_bet=baseline_no_bet,
        final_no_bet=no_bet,
    )


def apply_no_bet_decision_to_prediction(
    prediction: Any,
    decision: NoBetDecision,
    *,
    mode: str,
) -> Any:
    """Attach diagnostics and optionally update no_bet_flag.

    mode:
      off    — no-op (return prediction unchanged)
      shadow — store diagnostics only; do not change no_bet_flag
      active — set no_bet_flag from decision.no_bet
    """
    from dataclasses import replace

    mode_norm = (mode or "off").strip().lower()
    if mode_norm not in ("shadow", "active"):
        # off and unknown modes: fail-safe — no public mutation, no diagnostics write
        return prediction

    md = dict(getattr(prediction, "metadata", None) or {})
    diag = decision.to_diagnostics()
    # metadata is dict[str,str] — store compact JSON-safe strings
    import json

    md["no_bet_recomputed"] = "true" if decision.recomputed else "false"
    md["no_bet_decision_stage"] = decision.decision_stage
    md["no_bet_reasons"] = ",".join(decision.active_reasons)
    md["no_bet_cleared_reasons"] = ",".join(decision.cleared_reasons)
    md["no_bet_retained_reasons"] = ",".join(decision.retained_reasons)
    md["no_bet_recompute_mode"] = mode_norm
    md["final_no_bet"] = "true" if decision.no_bet else "false"
    if decision.baseline_no_bet is not None:
        md["baseline_no_bet"] = "true" if decision.baseline_no_bet else "false"
    md["no_bet_reason_details_json"] = json.dumps(
        [d.to_dict() for d in decision.reason_details],
        separators=(",", ":"),
        sort_keys=True,
    )
    if mode_norm == "shadow":
        md["shadow_final_no_bet"] = "true" if decision.no_bet else "false"
        md["shadow_no_bet_differs"] = (
            "true"
            if bool(getattr(prediction, "no_bet_flag", None)) != decision.no_bet
            else "false"
        )

    # Prefer mutating audit trace reasons when present (additive).
    audit = getattr(prediction, "audit_report", None)
    if audit is not None and getattr(audit, "trace", None) is not None:
        try:
            audit.trace.no_bet_reasons = list(decision.active_reasons)
        except Exception:
            pass

    new_flag = bool(getattr(prediction, "no_bet_flag", True))
    if mode_norm == "active":
        new_flag = decision.no_bet

    return replace(prediction, no_bet_flag=new_flag, metadata=md)


def extract_inherited_reasons_from_prediction(prediction: Any) -> list[str]:
    """Pull prior-stage reason strings from audit / metadata (never invent)."""
    reasons: list[str] = []
    audit = getattr(prediction, "audit_report", None)
    if audit is not None and getattr(audit, "trace", None) is not None:
        for r in list(getattr(audit.trace, "no_bet_reasons", None) or []):
            if r and str(r) not in reasons:
                reasons.append(str(r))
    md = getattr(prediction, "metadata", None) or {}
    raw = md.get("no_bet_reasons")
    if raw:
        for part in str(raw).split(","):
            part = part.strip()
            if part and part not in reasons:
                reasons.append(part)
    return reasons


def recompute_no_bet_after_enrichment(
    prediction: Any,
    *,
    mode: str,
    wde_data_quality: float | None = None,
    visibility_data_quality: float | None = None,
    scoring_data_quality: float | None = None,
    odds_status: str | None = None,
    fixture_started: bool = False,
    unsupported_fixture: bool = False,
    unsupported_market: bool = False,
    model_conflicts: list[str] | None = None,
    manual_block: bool = False,
) -> tuple[Any, NoBetDecision | None]:
    """Post-enrichment recompute entrypoint used by ScoringEngine._finalize_prediction."""
    mode_norm = (mode or "off").strip().lower()
    if mode_norm not in ("shadow", "active"):
        return prediction, None

    inherited = extract_inherited_reasons_from_prediction(prediction)
    # Sticky boolean alone is not inherited as a reason.
    # If baseline was no_bet but no reasons exist, do NOT invent LEGACY unless
    # caller explicitly passed opaque inherited codes.

    conf = float(getattr(prediction, "confidence_score", None) or 0.0)
    level = getattr(prediction, "confidence_level", None)
    level_s = getattr(level, "value", None) or (str(level) if level is not None else None)

    wde_dq = wde_data_quality
    if wde_dq is None:
        try:
            wde_dq = float(prediction.confidence_breakdown.data_quality_score)
        except Exception:
            wde_dq = None

    scoring_dq = scoring_data_quality
    if scoring_dq is None:
        scoring_dq = wde_dq

    vis_dq = visibility_data_quality
    if vis_dq is None:
        vis_dq = wde_dq

    decision = evaluate_no_bet_reasons(
        confidence=conf,
        confidence_level=level_s,
        wde_data_quality=wde_dq,
        visibility_data_quality=vis_dq,
        scoring_data_quality=scoring_dq,
        odds_status=odds_status,
        placeholder=bool(getattr(prediction, "is_placeholder", False)),
        fixture_started=fixture_started,
        unsupported_fixture=unsupported_fixture,
        unsupported_market=unsupported_market,
        model_conflicts=model_conflicts,
        manual_block=manual_block,
        inherited_reasons=inherited,
        baseline_no_bet=bool(getattr(prediction, "no_bet_flag", False)),
    )
    updated = apply_no_bet_decision_to_prediction(prediction, decision, mode=mode_norm)
    return updated, decision
