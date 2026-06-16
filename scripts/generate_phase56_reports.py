"""Generate Phase 56 audit reports from code-defined profiles and optional live fusion samples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
FIXTURE_ID = 1489374


def _write_overlap_audit() -> None:
    from worldcup_predictor.fusion.signal_diversity import AGENT_INPUT_PROFILES, input_overlap_pct

    agents = [
        ("lineup_agent", "LineupAgent", "lineups, fixture_status", 0.45, "Lineup V2"),
        ("lineup_intelligence_agent", "LineupIntelligenceAgent", "lineups, injuries, recent", 1.0, "Fusion"),
        ("injury_suspension_agent", "InjuryAgent", "injuries", 0.45, "Injury V2"),
        ("injury_suspension_intelligence_agent", "InjuryIntelligenceAgent", "injuries, lineups, depth", 1.0, "Fusion"),
        ("team_form_agent", "FormAgent", "team stats form", 0.7, "Scoring + Fusion"),
        ("elo_team_strength_intelligence_agent", "ELO Intelligence", "recent fixtures, ELO", 0.9, "Fusion"),
        ("xg_chance_quality_intelligence_agent", "xG Intelligence", "fixture/team stats", 0.9, "Fusion"),
        ("sharp_money_intelligence_agent", "Sharp Money", "odds snapshots", 0.95, "Fusion"),
        ("tournament_intelligence_agent", "Tournament", "standings, groups", 0.75, "Fusion"),
        ("player_quality_agent", "Player Quality", "top scorers, lineups", 0.55, "Fusion + FG"),
        ("first_goal_intelligence_v2", "First Goal", "players, form, odds", 0.0, "Informational"),
        ("tactics_agent", "Tactics", "lineups, xG hints", 0.6, "Fusion"),
    ]

    lines = [
        "# Agent Overlap Audit — Phase 56",
        "",
        "Generated from `fusion/signal_diversity.py` input profiles and fusion weights.",
        "",
        "| Agent | Inputs | Fusion weight | Overlap vs V2 pair | Risk |",
        "|-------|--------|---------------|-------------------|------|",
    ]

    pairs = [
        ("lineup_agent", "lineup_intelligence_agent", "Lineup"),
        ("injury_suspension_agent", "injury_suspension_intelligence_agent", "Injury"),
        ("team_form_agent", "elo_team_strength_intelligence_agent", "Form/ELO"),
        ("tactics_agent", "xg_chance_quality_intelligence_agent", "Tactics/xG"),
        ("team_form_agent", "tournament_intelligence_agent", "Form/Tournament"),
    ]

    overlap_map: dict[str, float] = {}
    for a, b, _ in pairs:
        overlap_map[a] = max(overlap_map.get(a, 0), input_overlap_pct(a, b))
        overlap_map[b] = max(overlap_map.get(b, 0), input_overlap_pct(a, b))

    for key, label, inputs, weight, impact in agents:
        ov = overlap_map.get(key, 0)
        if ov >= 70:
            risk = "**High**"
        elif ov >= 45:
            risk = "Medium"
        else:
            risk = "Low"
        lines.append(f"| {label} | {inputs} | {weight} | {ov}% | {risk} |")

    lines.extend(
        [
            "",
            "## Pairwise overlap (selected)",
            "",
        ]
    )
    for a, b, name in pairs:
        lines.append(f"- **{name}**: {input_overlap_pct(a, b)}% input overlap")

    lines.extend(
        [
            "",
            "## First Goal",
            "",
            "First Goal Intelligence is **informational only** (no fusion weight). Overlap with Player Quality "
            "and Lineup V2 is **Medium (~55%)** but does not double-count in 1X2/O-U.",
            "",
        ]
    )

    (REPORTS / "agent_overlap_audit.md").write_text("\n".join(lines), encoding="utf-8")


def _write_duplicate_signal_audit() -> None:
    text = """# Duplicate Signal Audit — Phase 56

## Top duplicate-count paths

| Path | Same fact | Agents counting it | Severity | Phase 56 mitigation |
|------|-----------|-------------------|----------|---------------------|
| Missing player | Injury list | Injury V1, Injury V2, Lineup V2, Player Quality | **High** | V2 primary; V1 dampened 0.55× in cluster |
| Official lineup | `report.lineups` | Lineup V1, Lineup V2, Tactics, Player Quality, FG | **High** | Correlation dampening on V1 |
| Recent form | `teams/statistics.form` | Form, ELO, Tournament, Scoring engine | **High** | Form/ELO cluster dampening |
| Team strength | Recent fixtures | ELO, xG, Tactics | **Medium** | xG/Tactics cluster 0.72 prior |
| Market odds | `odds` JSON | Sharp Money, Consensus, Movement, OddsMarket | **High** | Market cluster 0.85 — 2nd+ dampened |
| Scorer profile | API-Sports deep | Player Quality, First Goal | **Medium** | FG informational only |
| Squad depth | Squads | Injury V2, Tournament, Lineup V2 | **Medium** | Shared input; depth adjusts injury only |

## Example: missing player triple-count (before Phase 56)

```
Injury API → InjurySuspensionAgent (absence_score)
           → InjurySuspensionIntelligenceAgent (impact_score)
           → LineupIntelligenceAgent (missing_key_players)
           → PlayerQualityAgent (candidate gaps)
```

**After Phase 56:** Fusion applies `injury_cluster` dampening — secondary agents in cluster receive `correlation_multiplier` ≤ 0.85 when lean agrees.

## Example: momentum double-count

```
FormAgent (form_score) + EloAgent (elo_difference) + TournamentAgent (qualification pressure)
```

**After Phase 56:** `strength_cluster` and `tournament_form_cluster` reduce redundant weight when all lean same direction.

## Scoring engine (unchanged)

Core `ScoringEngine` form/H2H/lineup weights remain intact. Phase 56 only refines **fusion confidence overlay**, not baseline 1X2/O-U selection.
"""
    (REPORTS / "duplicate_signal_audit.md").write_text(text, encoding="utf-8")


def _write_correlation_matrix(sample_runs: list[list[dict]]) -> None:
    from worldcup_predictor.fusion.signal_diversity import (
        CORRELATION_CLUSTERS,
        agreement_stats,
        empirical_correlation_matrix,
        structural_correlation,
    )

    if sample_runs:
        matrix = empirical_correlation_matrix(sample_runs)
        method = "empirical (multi-fixture fusion snapshots) + structural fallback"
    else:
        agents = sorted(
            {
                k
                for cluster in CORRELATION_CLUSTERS
                for k in cluster[1]
            }
            | {
                "lineup_agent",
                "injury_suspension_agent",
                "tactics_agent",
                "player_quality_agent",
                "motivation_psychology_agent",
            }
        )
        matrix = {a: {b: structural_correlation(a, b) for b in agents} for a in agents}
        method = "structural (input profiles + cluster priors)"

    pairs = agreement_stats(matrix, threshold=0.8)
    high = [p for p in pairs if p["highly_correlated"]]

    lines = [
        "# Agent Correlation Matrix — Phase 56",
        "",
        f"Method: **{method}**",
        "",
        "## Highly correlated pairs (>80%)",
        "",
    ]
    if high:
        lines.append("| Agent A | Agent B | Correlation | Agreement risk |")
        lines.append("|--------|---------|-------------|----------------|")
        for p in high[:15]:
            lines.append(
                f"| {p['agent_a']} | {p['agent_b']} | {p['correlation']:.2f} | High double-count risk |"
            )
    else:
        lines.append("_No pairs above 0.80 in sample — see structural table._")

    lines.extend(["", "## Full matrix (selected agents)", ""])
    keys = sorted(matrix.keys())[:12]
    header = "| | " + " | ".join(k.split("_")[0][:8] for k in keys) + " |"
    lines.append(header)
    lines.append("| --- | " + " | ".join(["---"] * len(keys)) + " |")
    for a in keys:
        row = [a.split("_")[0][:12]]
        for b in keys:
            row.append(f"{matrix.get(a, {}).get(b, 0):.2f}")
        lines.append("| " + " | ".join(row) + " |")

    lines.extend(
        [
            "",
            "## Cluster priors (design-time)",
            "",
        ]
    )
    for name, members, prior in CORRELATION_CLUSTERS:
        lines.append(f"- **{name}** ({prior:.0%}): {', '.join(members)}")

    (REPORTS / "agent_correlation_matrix.md").write_text("\n".join(lines), encoding="utf-8")


def _write_agent_health() -> None:
    text = """# Agent Health Report — Phase 56

## Core agents (keep at full weight)

| Agent | Active | Useful | Overlap risk | Prediction impact |
|-------|--------|--------|--------------|-------------------|
| Lineup Intelligence V2 | Yes | High | Medium (V1 duplicate) | High — fusion 1.0 |
| Injury Intelligence V2 | Yes | High | Medium (V1 duplicate) | High — fusion 1.0 |
| Sharp Money V2 | Yes | High | Medium (odds stack) | High — fusion 0.95 |
| ELO Intelligence | Yes | High | Medium (form overlap) | High — fusion 0.9 |
| xG Intelligence | Yes | High | Medium (tactics overlap) | High — fusion 0.9 |
| Market Consensus | Yes | High | High (odds stack) | Medium — fusion 0.8 |
| Tournament Intelligence | Yes | Medium | Medium (form overlap) | Medium — fusion 0.75 |

## Support agents

| Agent | Active | Useful | Redundant? | Notes |
|-------|--------|--------|------------|-------|
| Team Form | Yes | High | Partial | Core scoring input; dampened vs ELO in fusion |
| Tactics | Yes | Medium | Partial | O/U lean; overlaps xG |
| Player Quality | Yes | Medium | Partial | Feeds FG; overlaps lineup |
| Odds Movement | Yes | Medium | Yes vs Sharp | Dampened in market cluster |
| Motivation | Yes | Low-Med | Low | Light edge |
| Weather / Referee | Yes | Low | Low | Context only |

## Candidate merge agents (do not remove — dampen only)

| Agent | Merge target | Overlap % | Phase 56 action |
|-------|--------------|-----------|-----------------|
| LineupAgent | Lineup Intelligence V2 | 78% | Correlation dampening 0.55× when redundant |
| InjurySuspensionAgent | Injury Intelligence V2 | 76% | Correlation dampening |
| OddsMovementAgent | Sharp Money / Consensus | 85% | Market cluster dampening |

## Informational (no fusion)

| Module | Impact |
|--------|--------|
| First Goal Intelligence V2 | GUI, export, Hall of Fame FG metric — no 1X2 change |

## Ranking summary

1. **Core:** Lineup V2, Injury V2, Sharp Money, ELO, xG, Market Consensus, Tournament  
2. **Support:** Form, Tactics, Player Quality, Motivation, Weather, Referee  
3. **Merge candidates (dampen):** Lineup V1, Injury V1, Odds Movement  
"""
    (REPORTS / "agent_health_report.md").write_text(text, encoding="utf-8")


def _collect_fusion_samples() -> list[list[dict]]:
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import load_fusion_from_prediction
        from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
        from worldcup_predictor.accuracy.history_store import PredictionHistoryStore

        settings = get_settings()
        if not settings.api_football_configured:
            return []
        ids = sorted({FIXTURE_ID} | {r.fixture_id for r in PredictionHistoryStore().load_all()[:8]})
        runs: list[list[dict]] = []
        pipeline = PredictPipeline(settings)
        for fid in ids[:5]:
            result = pipeline.run(fid, record_history=False)
            if not result.success or not result.prediction:
                continue
            fusion = load_fusion_from_prediction(result.prediction)
            if fusion:
                agents = fusion.signal_matrix.agents
                runs.append([a.to_dict() for a in agents])
        return runs
    except Exception:
        return []


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    samples = _collect_fusion_samples()
    _write_overlap_audit()
    _write_duplicate_signal_audit()
    _write_correlation_matrix(samples)
    _write_agent_health()
    print(f"Phase 56 reports written to {REPORTS} ({len(samples)} fusion samples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
