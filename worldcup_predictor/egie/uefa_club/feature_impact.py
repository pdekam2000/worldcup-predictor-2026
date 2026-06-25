"""Phase API-J — rank paid-feature tier impact from UEFA A–F backtest."""

from __future__ import annotations

from typing import Any


def rank_feature_impact(backtest: dict[str, Any]) -> dict[str, Any]:
    strategies = backtest.get("strategies") or {}
    base = strategies.get("A") or {}
    base_fg = float(base.get("first_goal_team_hit_rate") or 0)
    base_gr = float(base.get("goal_range_hit_rate") or 0)
    base_sm = float(base.get("goal_minute_soft_hit_rate") or 0)
    base_cov = (base.get("coverage") or {}).get("with_paid_data") or 0

    feature_map = {
        "xg": ("B", "baseline_plus_xg"),
        "pressure": ("C", "baseline_plus_pressure"),
        "odds": ("D", "baseline_plus_odds"),
        "xg_pressure_odds": ("E", "baseline_plus_xg_pressure_odds"),
        "full_provider": ("F", "full_provider"),
    }

    rows: list[dict[str, Any]] = []
    for feature, (key, label) in feature_map.items():
        s = strategies.get(key) or {}
        cov = (s.get("coverage") or {}).get("with_paid_data") or 0
        fg = s.get("first_goal_team_hit_rate")
        gr = s.get("goal_range_hit_rate")
        sm = s.get("goal_minute_soft_hit_rate")
        fg_m = base.get("metrics") or {}
        s_m = s.get("metrics") or {}
        pending_a = ((fg_m.get("by_market") or {}).get("first_goal_team") or {}).get("pending") or 0
        pending_s = ((s_m.get("by_market") or {}).get("first_goal_team") or {}).get("pending") or 0
        rows.append(
            {
                "feature": feature,
                "strategy": key,
                "label": label,
                "coverage_with_paid_data": cov,
                "coverage_delta_vs_a": cov - base_cov,
                "fg_team_hit_rate": fg,
                "fg_team_delta_vs_a": (float(fg) - base_fg) if fg is not None else None,
                "goal_range_hit_rate": gr,
                "goal_range_delta_vs_a": (float(gr) - base_gr) if gr is not None else None,
                "soft_minute_hit_rate": sm,
                "soft_minute_delta_vs_a": (float(sm) - base_sm) if sm is not None else None,
                "fg_pending": pending_s,
                "fg_pending_delta_vs_a": pending_s - pending_a,
            }
        )

    # Lineups/events/predictions from coverage audit on strategy F
    f_cov = ((strategies.get("F") or {}).get("coverage") or {})
    component_notes = {
        "lineups": "Coverage via strategy F; FG impact only when enrichment shifts picks",
        "events": "Required for FG evaluation; not a paid enrichment tier",
        "predictions": "0% historical coverage — no measurable backtest lift",
    }

    def _tier(delta: float | None, coverage: int) -> str:
        if coverage == 0:
            return "B"
        if delta is None:
            return "B"
        if delta >= 0.15:
            return "S"
        if delta >= 0.03:
            return "A"
        return "B"

    ranked = []
    for r in rows:
        fg_d = r.get("fg_team_delta_vs_a")
        tier = _tier(float(fg_d) if fg_d is not None else None, int(r.get("coverage_with_paid_data") or 0))
        ranked.append({**r, "tier": tier})

    ranked.sort(key=lambda x: float(x.get("fg_team_delta_vs_a") or 0), reverse=True)

    return {
        "baseline_a": {
            "fg_team_hit_rate": base_fg,
            "goal_range_hit_rate": base_gr,
            "soft_minute_hit_rate": base_sm,
            "with_paid_data": base_cov,
        },
        "ranked_features": ranked,
        "component_notes": component_notes,
        "tier_legend": {
            "S": "Material FG lift (>=15pp) with coverage",
            "A": "Moderate lift (>=3pp) with coverage",
            "B": "No coverage or no measurable lift",
        },
        "xg_historical_note": (
            "Strategy B tier depends on xG availability; if xG coverage=0%, B cannot diverge from A on xG signal."
        ),
    }
