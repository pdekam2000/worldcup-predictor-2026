"""Phase 56 — agent input profiles, correlation clusters, and fusion diversity scoring."""

from __future__ import annotations

import math
from typing import Any

# Shared input domains per agent (for overlap audit + dampening).
AGENT_INPUT_PROFILES: dict[str, tuple[str, ...]] = {
    "lineup_agent": ("lineups", "fixture_status"),
    "lineup_intelligence_agent": ("lineups", "injuries", "recent_fixtures", "fixture_status"),
    "injury_suspension_agent": ("injuries",),
    "injury_suspension_intelligence_agent": ("injuries", "lineups", "squad_depth"),
    "team_form_agent": ("team_statistics_form", "team_statistics_goals", "recent_fixtures"),
    "elo_team_strength_intelligence_agent": ("recent_fixtures", "team_statistics", "h2h"),
    "xg_chance_quality_intelligence_agent": ("fixture_statistics", "team_statistics", "chance_creation"),
    "tactics_agent": ("lineups", "team_statistics", "supplemental_xg"),
    "sharp_money_intelligence_agent": ("odds", "odds_snapshots"),
    "market_consensus_agent": ("odds",),
    "odds_movement_agent": ("odds", "odds_snapshots"),
    "odds_market_agent": ("odds",),
    "tournament_intelligence_agent": ("standings", "group_context", "fixture_stage"),
    "player_quality_agent": ("top_scorers", "fixture_players", "lineups", "squads"),
    "motivation_psychology_agent": ("fixture_stage", "standings"),
    "weather_agent": ("weather",),
    "referee_agent": ("referee",),
    "first_goal_intelligence_v2": ("lineups", "player_stats", "form", "odds", "xg"),
}

# Clusters of agents that tend to share inputs / correlate in lean direction.
CORRELATION_CLUSTERS: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("lineup_cluster", ("lineup_intelligence_agent", "lineup_agent"), 0.78),
    ("injury_cluster", ("injury_suspension_intelligence_agent", "injury_suspension_agent"), 0.76),
    ("strength_cluster", ("team_form_agent", "elo_team_strength_intelligence_agent"), 0.81),
    ("chance_cluster", ("xg_chance_quality_intelligence_agent", "tactics_agent"), 0.72),
    ("market_cluster", ("sharp_money_intelligence_agent", "market_consensus_agent", "odds_movement_agent"), 0.85),
    ("player_context_cluster", ("player_quality_agent", "lineup_intelligence_agent"), 0.68),
    ("tournament_form_cluster", ("tournament_intelligence_agent", "team_form_agent"), 0.64),
)

# Agents treated as largely independent for explainability display.
INDEPENDENT_AGENT_KEYS: frozenset[str] = frozenset(
    {
        "elo_team_strength_intelligence_agent",
        "xg_chance_quality_intelligence_agent",
        "sharp_money_intelligence_agent",
        "market_consensus_agent",
        "injury_suspension_intelligence_agent",
        "lineup_intelligence_agent",
        "weather_agent",
        "referee_agent",
    }
)

CORRELATED_AGENT_KEYS: frozenset[str] = frozenset(
    {
        "team_form_agent",
        "tournament_intelligence_agent",
        "lineup_agent",
        "injury_suspension_agent",
        "tactics_agent",
        "odds_movement_agent",
        "player_quality_agent",
        "motivation_psychology_agent",
    }
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def input_overlap_pct(agent_a: str, agent_b: str) -> float:
    """Jaccard overlap of declared input domains."""
    a = set(AGENT_INPUT_PROFILES.get(agent_a, ()))
    b = set(AGENT_INPUT_PROFILES.get(agent_b, ()))
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b) * 100, 1)


def structural_correlation(agent_a: str, agent_b: str) -> float:
    """Estimated correlation 0–1 from input overlap and cluster membership."""
    if agent_a == agent_b:
        return 1.0
    overlap = input_overlap_pct(agent_a, agent_b) / 100.0
    cluster_boost = 0.0
    for _name, members, prior in CORRELATION_CLUSTERS:
        if agent_a in members and agent_b in members:
            cluster_boost = max(cluster_boost, prior)
    return round(_clamp(overlap * 0.45 + cluster_boost * 0.55, 0.0, 0.95), 2)


def _agent_vector(row: dict[str, Any]) -> tuple[float, float, float]:
    """1x2 lean vector: home-positive, away-positive, draw-neutral split."""
    h = float(row.get("home_signal") or 0)
    a = float(row.get("away_signal") or 0)
    d = float(row.get("draw_signal") or 0)
    return h, a, d


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def empirical_correlation_matrix(runs: list[list[dict[str, Any]]]) -> dict[str, dict[str, float]]:
    """Pairwise correlation from multiple fusion snapshots (agent home_signal series)."""
    agents: set[str] = set()
    for run in runs:
        for row in run:
            key = str(row.get("agent_key") or "")
            if key:
                agents.add(key)
    agent_list = sorted(agents)
    series: dict[str, list[float]] = {k: [] for k in agent_list}
    for run in runs:
        by_key = {str(r.get("agent_key")): r for r in run}
        for key in agent_list:
            row = by_key.get(key)
            series[key].append(float(row.get("home_signal") or 0) if row else 0.0)

    matrix: dict[str, dict[str, float]] = {a: {} for a in agent_list}
    for i, a in enumerate(agent_list):
        for b in agent_list[i:]:
            if a == b:
                matrix[a][b] = 1.0
                continue
            r = _pearson(series[a], series[b])
            val = round(r, 2) if r is not None else structural_correlation(a, b)
            matrix[a][b] = val
            matrix.setdefault(b, {})[a] = val
    return matrix


def agreement_stats(matrix: dict[str, dict[str, float]], threshold: float = 0.8) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for a, row in matrix.items():
        for b, corr in row.items():
            if a >= b:
                continue
            key = (a, b)
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                {
                    "agent_a": a,
                    "agent_b": b,
                    "correlation": corr,
                    "highly_correlated": corr >= threshold,
                }
            )
    pairs.sort(key=lambda p: p["correlation"], reverse=True)
    return pairs


def apply_correlation_dampening(rows: list[Any]) -> tuple[list[Any], dict[str, float]]:
    """
    Reduce effective weight for redundant agents within the same cluster.
    Returns updated rows (mutates correlation_multiplier on row if present) and multipliers.
    """
    multipliers: dict[str, float] = {}
    by_key = {r.agent_key: r for r in rows}

    for _cluster, members, prior in CORRELATION_CLUSTERS:
        active = [by_key[k] for k in members if k in by_key]
        if len(active) < 2:
            continue
        active.sort(key=lambda r: r.weight * r.quality_multiplier, reverse=True)
        for idx, row in enumerate(active):
            if idx == 0:
                mult = 1.0
            else:
                same_lean = active[0].lean_1x2 == row.lean_1x2 and row.lean_1x2 != "neutral"
                dampen = 0.55 + (1.0 - prior) * 0.25
                mult = dampen if same_lean else 0.85
            multipliers[row.agent_key] = min(multipliers.get(row.agent_key, 1.0), mult)
            if hasattr(row, "correlation_multiplier"):
                row.correlation_multiplier = mult
            else:
                row.correlation_multiplier = mult

    for row in rows:
        multipliers.setdefault(row.agent_key, getattr(row, "correlation_multiplier", 1.0))
    return rows, multipliers


def compute_fusion_diversity_score(
    rows: list[Any],
    *,
    baseline_1x2_lean: str = "neutral",
) -> dict[str, Any]:
    """0–100 diversity score — rewards independent clusters, penalizes redundant agreement."""
    if not rows:
        return {
            "fusion_diversity_score": 45.0,
            "independent_signal_count": 0,
            "correlated_signal_count": 0,
            "active_clusters": [],
            "redundant_agents": [],
        }

    cluster_names = [c[0] for c in CORRELATION_CLUSTERS]
    active_clusters: list[str] = []
    redundant: list[str] = []
    independent_count = 0
    correlated_count = 0

    by_key = {r.agent_key: r for r in rows}
    baseline_x2 = baseline_1x2_lean

    for cluster_name, members, _prior in CORRELATION_CLUSTERS:
        active = [by_key[k] for k in members if k in by_key]
        if not active:
            continue
        active_clusters.append(cluster_name)
        aligned = [r for r in active if r.lean_1x2 == baseline_x2 and r.lean_1x2 != "neutral"]
        if len(active) >= 2 and len(aligned) >= 2:
            redundant.extend([r.agent_key for r in active[1:]])

    for row in rows:
        if row.agent_key in INDEPENDENT_AGENT_KEYS:
            independent_count += 1
        elif row.agent_key in CORRELATED_AGENT_KEYS:
            correlated_count += 1

    unique_clusters = len(active_clusters)
    total_clusters = len(CORRELATION_CLUSTERS)
    cluster_coverage = unique_clusters / max(total_clusters, 1)
    redundancy_penalty = min(len(set(redundant)) * 6, 30)
    diversity_bonus = min(independent_count * 4, 24)
    score = _clamp(cluster_coverage * 55 + diversity_bonus + 15 - redundancy_penalty, 0, 100)

    return {
        "fusion_diversity_score": round(score, 1),
        "independent_signal_count": independent_count,
        "correlated_signal_count": correlated_count,
        "active_clusters": active_clusters,
        "redundant_agents": sorted(set(redundant)),
    }


def classify_signals_for_explainability(
    rows: list[Any],
    *,
    baseline_1x2_lean: str,
) -> dict[str, Any]:
    """Split supporting agents into independent vs correlated buckets."""
    independent: list[str] = []
    correlated: list[str] = []
    for row in rows:
        if row.lean_1x2 != baseline_1x2_lean or row.lean_1x2 == "neutral":
            continue
        label = row.label
        if row.agent_key in INDEPENDENT_AGENT_KEYS:
            independent.append(label)
        else:
            correlated.append(label)
    return {
        "independent_signals": independent,
        "correlated_signals": correlated,
        "independent_count": len(independent),
        "correlated_count": len(correlated),
    }
