"""Part B — modular orchestration graph design."""

from __future__ import annotations

from worldcup_predictor.elite_orchestrator.models import GraphNode, INPUT_SOURCES, MARKET_IDS


def build_orchestration_graph() -> dict[str, object]:
    """Design-time DAG — shadow integration only, no production wiring."""
    input_nodes = [
        GraphNode(node_id=f"input_{src}", node_type="input", outputs=[src])
        for src in INPUT_SOURCES
    ]

    component_nodes = [
        GraphNode(
            node_id="node_lineup_intel",
            node_type="component",
            inputs=["lineups", "player_store"],
            outputs=["lineup_features", "starter_probs"],
            component_id="lineup_intelligence",
        ),
        GraphNode(
            node_id="node_player_form",
            node_type="component",
            inputs=["player_store"],
            outputs=["player_form_features"],
            component_id="player_form_store",
        ),
        GraphNode(
            node_id="node_goalscorer_intel",
            node_type="component",
            inputs=["lineup_features", "starter_probs", "player_form_features"],
            outputs=["goalscorer_rankings", "team_attack_proxy"],
            component_id="goalscorer_intelligence",
        ),
        GraphNode(
            node_id="node_odds_intel",
            node_type="component",
            inputs=["odds"],
            outputs=["implied_probs", "odds_movement", "odds_confidence"],
            component_id="odds_intelligence",
        ),
        GraphNode(
            node_id="node_mbi_prior",
            node_type="component",
            inputs=["odds", "market_behavior_intelligence"],
            outputs=["mbi_bucket_prior", "mbi_calibration_gap"],
            component_id="market_behavior_intelligence",
        ),
        GraphNode(
            node_id="node_egie_baseline",
            node_type="component",
            inputs=["historical_models", "lineup_features"],
            outputs=["egie_fgt", "egie_timing", "egie_range"],
            component_id="egie_historical_baseline",
        ),
        GraphNode(
            node_id="node_fgt_v2",
            node_type="component",
            inputs=["team_attack_proxy", "implied_probs", "egie_fgt"],
            outputs=["fgt_v2_prediction", "fgt_v2_probs"],
            component_id="first_goal_team_v2",
        ),
    ]

    fusion_nodes = [
        GraphNode(
            node_id="fuse_1x2",
            node_type="fusion",
            inputs=["implied_probs", "mbi_bucket_prior", "odds_confidence"],
            outputs=["1x2"],
        ),
        GraphNode(
            node_id="fuse_first_goal_team",
            node_type="fusion",
            inputs=["fgt_v2_prediction", "egie_fgt", "mbi_bucket_prior", "implied_probs", "team_attack_proxy"],
            outputs=["first_goal_team"],
        ),
        GraphNode(
            node_id="fuse_team_to_score_first",
            node_type="fusion",
            inputs=["fgt_v2_prediction", "egie_fgt", "implied_probs"],
            outputs=["team_to_score_first"],
        ),
        GraphNode(
            node_id="fuse_anytime_goalscorer",
            node_type="fusion",
            inputs=["goalscorer_rankings", "implied_probs", "starter_probs"],
            outputs=["anytime_goalscorer"],
        ),
        GraphNode(
            node_id="fuse_first_goalscorer",
            node_type="fusion",
            inputs=["goalscorer_rankings", "implied_probs"],
            outputs=["first_goalscorer"],
        ),
        GraphNode(
            node_id="fuse_goal_timing",
            node_type="fusion",
            inputs=["egie_timing", "egie_range", "implied_probs"],
            outputs=["goal_timing"],
        ),
    ]

    confidence_node = GraphNode(
        node_id="node_confidence_fusion",
        node_type="confidence",
        inputs=[m for m in MARKET_IDS],
        outputs=["tier_a_d", "fusion_scores"],
        component_id="hybrid_confidence_engine",
    )

    output_node = GraphNode(
        node_id="output_elite_shadow",
        node_type="output",
        inputs=[m for m in MARKET_IDS] + ["tier_a_d", "fusion_scores"],
        outputs=["elite_shadow_prediction"],
    )

    all_nodes = input_nodes + component_nodes + fusion_nodes + [confidence_node, output_node]
    edges: list[dict[str, str]] = []
    for node in all_nodes:
        for inp in node.inputs:
            edges.append({"from": inp, "to": node.node_id})

    return {
        "version": "elite_orchestrator_v1_shadow",
        "inputs": list(INPUT_SOURCES),
        "outputs": list(MARKET_IDS),
        "nodes": [n.to_dict() for n in all_nodes],
        "edges": edges,
        "execution_order": [
            "input_layer",
            "parallel_components",
            "market_fusion",
            "confidence_fusion",
            "shadow_output",
        ],
        "mermaid": _mermaid_diagram(),
    }


def _mermaid_diagram() -> str:
    return """flowchart TB
    subgraph inputs [Input Layer]
        L[lineups]
        PS[player_store]
        GS[goalscorer_intelligence]
        MBI[market_behavior_intelligence]
        OD[odds]
        HM[historical_models]
    end

    subgraph components [Validated Components]
        LI[lineup_intelligence]
        PF[player_form_store]
        GI[goalscorer_intelligence]
        OI[odds_intelligence]
        MP[mbi_prior]
        EB[egie_baseline]
        FV[first_goal_team_v2]
    end

    subgraph fusion [Market Fusion]
        F1[1X2]
        F2[first_goal_team]
        F3[team_to_score_first]
        F4[anytime_goalscorer]
        F5[first_goalscorer]
        F6[goal_timing]
    end

    CF[confidence_fusion A-D]
    OUT[elite_shadow_prediction]

    L --> LI
    PS --> LI
    PS --> PF
    LI --> GI
    PF --> GI
    OD --> OI
    OD --> MP
    MBI --> MP
    HM --> EB
    LI --> EB
    GI --> FV
    OI --> FV
    EB --> FV
    OI --> F1
    MP --> F1
    FV --> F2
    EB --> F2
    MP --> F2
    FV --> F3
    EB --> F3
    GI --> F4
    OI --> F4
    GI --> F5
    EB --> F6
    F1 & F2 & F3 & F4 & F5 & F6 --> CF
    CF --> OUT"""
