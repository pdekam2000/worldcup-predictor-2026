"""Safety envelope for lambda bridge — fail-closed friendly."""

from __future__ import annotations

from worldcup_predictor.prediction.lambda_bridge.config import (
    AGENT_GROUPS,
    DQ_DISABLE_BELOW,
    DQ_FULL_AT,
    DQ_SCALE_MIN,
    GLOBAL_LAMBDA_CAP,
    GROUP_CAPS,
    LAMBDA_MAX,
    LAMBDA_MIN,
)
from worldcup_predictor.prediction.lambda_bridge.models import (
    LambdaBridgeMode,
    LambdaBridgeResult,
    SpecialistLambdaContribution,
)


def data_quality_scale(data_quality_pct: float) -> float:
    if data_quality_pct < DQ_DISABLE_BELOW:
        return 0.0
    if data_quality_pct >= DQ_FULL_AT:
        return 1.0
    return max(DQ_SCALE_MIN, min(1.0, data_quality_pct / DQ_FULL_AT))


def confidence_scale_from_contributions(contributions: list[SpecialistLambdaContribution]) -> float:
    included = [c for c in contributions if c.included]
    if not included:
        return 0.5
    return min(1.0, 0.5 + 0.1 * len(included))


def apply_group_caps(
    contributions: list[SpecialistLambdaContribution],
) -> tuple[float, float]:
    group_home: dict[str, float] = {}
    group_away: dict[str, float] = {}
    for c in contributions:
        if not c.included:
            continue
        group = AGENT_GROUPS.get(c.agent_name, "other")
        group_home[group] = group_home.get(group, 0.0) + c.delta_home
        group_away[group] = group_away.get(group, 0.0) + c.delta_away

    total_h = 0.0
    total_a = 0.0
    for group, cap in GROUP_CAPS.items():
        gh = group_home.get(group, 0.0)
        ga = group_away.get(group, 0.0)
        if abs(gh) > cap:
            gh = cap if gh > 0 else -cap
        if abs(ga) > cap:
            ga = cap if ga > 0 else -cap
        total_h += gh
        total_a += ga
    return total_h, total_a


def apply_global_cap(delta_home: float, delta_away: float) -> tuple[float, float, bool]:
    cap = GLOBAL_LAMBDA_CAP
    applied = abs(delta_home) > cap or abs(delta_away) > cap
    dh = max(-cap, min(cap, delta_home))
    da = max(-cap, min(cap, delta_away))
    return dh, da, applied


def finalize_lambda(
    lambda_base_home: float,
    lambda_base_away: float,
    delta_home: float,
    delta_away: float,
) -> tuple[float, float]:
    return (
        max(LAMBDA_MIN, min(LAMBDA_MAX, lambda_base_home + delta_home)),
        max(LAMBDA_MIN, min(LAMBDA_MAX, lambda_base_away + delta_away)),
    )


def build_result(
    *,
    lambda_base_home: float,
    lambda_base_away: float,
    contributions: list[SpecialistLambdaContribution],
    data_quality_pct: float,
    mode: LambdaBridgeMode,
    config_version: str,
) -> LambdaBridgeResult:
    dq_scale = data_quality_scale(data_quality_pct)
    conf_scale = confidence_scale_from_contributions(contributions)
    if dq_scale <= 0:
        return LambdaBridgeResult(
            lambda_base_home=lambda_base_home,
            lambda_base_away=lambda_base_away,
            lambda_adjusted_home=lambda_base_home,
            lambda_adjusted_away=lambda_base_away,
            delta_home_total=0.0,
            delta_away_total=0.0,
            contributions=contributions,
            data_quality_pct=data_quality_pct,
            data_quality_scale=dq_scale,
            confidence_scale=conf_scale,
            config_version=config_version,
            mode=mode,
        )

    pre_h, pre_a = apply_group_caps(contributions)
    pre_h *= dq_scale * conf_scale
    pre_a *= dq_scale * conf_scale
    dh, da, capped = apply_global_cap(pre_h, pre_a)
    adj_h, adj_a = finalize_lambda(lambda_base_home, lambda_base_away, dh, da)
    return LambdaBridgeResult(
        lambda_base_home=lambda_base_home,
        lambda_base_away=lambda_base_away,
        lambda_adjusted_home=adj_h,
        lambda_adjusted_away=adj_a,
        delta_home_total=round(adj_h - lambda_base_home, 4),
        delta_away_total=round(adj_a - lambda_base_away, 4),
        contributions=contributions,
        data_quality_pct=data_quality_pct,
        data_quality_scale=dq_scale,
        confidence_scale=conf_scale,
        global_cap_applied=capped,
        global_cap_pre_home=pre_h,
        global_cap_pre_away=pre_a,
        config_version=config_version,
        mode=mode,
    )
