"""Part E — market readiness matrix."""

from __future__ import annotations

from worldcup_predictor.elite_orchestrator.models import MARKET_IDS, MarketReadiness


def build_readiness_matrix() -> list[MarketReadiness]:
    return [
        MarketReadiness(
            market_id="1x2",
            readiness="PARTIAL",
            primary_components=["odds_intelligence", "market_behavior_intelligence"],
            blockers=["EGIE 1X2 accuracy ~40%", "UEFA odds coverage gaps", "No validated non-odds model"],
            shadow_ready=True,
            production_ready=False,
            notes="MBI improves calibration modestly. Shadow odds+MBI blend first.",
        ),
        MarketReadiness(
            market_id="first_goal_team",
            readiness="READY",
            primary_components=["first_goal_team_v2", "egie_historical_baseline", "goalscorer_intelligence"],
            blockers=[],
            shadow_ready=True,
            production_ready=False,
            notes="55C HIGH_VALUE. Best path: FGT V2 + EGIE ensemble. Shadow before WDE.",
        ),
        MarketReadiness(
            market_id="team_to_score_first",
            readiness="READY",
            primary_components=["first_goal_team_v2", "egie_historical_baseline", "odds_intelligence"],
            blockers=["FTS odds sparse UEFA (3 fixtures strict)"],
            shadow_ready=True,
            production_ready=False,
            notes="Alias fusion path to first_goal_team. Same validated stack.",
        ),
        MarketReadiness(
            market_id="anytime_goalscorer",
            readiness="PARTIAL",
            primary_components=["goalscorer_intelligence", "player_form_store", "lineup_intelligence"],
            blockers=["UEFA goalscorer odds 3%", "Elite top-3 < 70%"],
            shadow_ready=True,
            production_ready=False,
            notes="WC shadow-ready (77% top-3 with odds). UEFA needs odds expansion (55B blocked).",
        ),
        MarketReadiness(
            market_id="first_goalscorer",
            readiness="RESEARCH",
            primary_components=["goalscorer_intelligence"],
            blockers=["31% top-3 composite", "Rare event sparsity", "No odds coverage UEFA"],
            shadow_ready=True,
            production_ready=False,
            notes="Include in shadow object but tier-capped at B. Research track only.",
        ),
        MarketReadiness(
            market_id="goal_timing",
            readiness="PARTIAL",
            primary_components=["egie_historical_baseline", "hybrid_confidence_engine"],
            blockers=["Range accuracy 28%", "Minute accuracy 3.4%"],
            shadow_ready=True,
            production_ready=False,
            notes="Production exists but elite layer adds confidence only — no new timing model.",
        ),
    ]


def shadow_production_priority(matrix: list[MarketReadiness]) -> list[dict[str, object]]:
    """Rank markets for shadow production entry."""
    priority_order = {
        "READY": 0,
        "PARTIAL": 1,
        "RESEARCH": 2,
        "BLOCKED": 3,
    }
    ranked = sorted(
        [m for m in matrix if m.shadow_ready],
        key=lambda m: (priority_order.get(m.readiness, 9), m.market_id),
    )
    return [
        {
            "rank": i + 1,
            "market_id": m.market_id,
            "readiness": m.readiness,
            "primary_components": m.primary_components,
            "notes": m.notes,
        }
        for i, m in enumerate(ranked)
    ]


def readiness_summary(matrix: list[MarketReadiness]) -> dict[str, int]:
    return {level: sum(1 for m in matrix if m.readiness == level) for level in ("READY", "PARTIAL", "RESEARCH", "BLOCKED")}
