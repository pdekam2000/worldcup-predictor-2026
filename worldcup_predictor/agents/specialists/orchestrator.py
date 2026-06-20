from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.injury_suspension_intelligence_agent import (
    InjurySuspensionIntelligenceAgent,
)
from worldcup_predictor.agents.specialists.expected_lineup_agent import ExpectedLineupAgent
from worldcup_predictor.agents.specialists.lineup_intelligence_agent import LineupIntelligenceAgent
from worldcup_predictor.agents.specialists.agents import (
    InjurySuspensionAgent,
    LineupAgent,
    MasterAnalysisAgent,
    MotivationPsychologyAgent,
    OddsMarketAgent,
    PlayerQualityAgent,
    RefereeAgent,
    TacticsAgent,
    TeamFormAgent,
    WeatherAgent,
)
from worldcup_predictor.agents.specialists.odds_control_agent import OddsControlAgent
from worldcup_predictor.odds.market_consensus_agent import MarketConsensusAgent
from worldcup_predictor.odds.odds_movement_agent import OddsMovementAgent
from worldcup_predictor.agents.specialists.sharp_money_intelligence_agent import SharpMoneyIntelligenceAgent
from worldcup_predictor.agents.specialists.sportmonks_prediction_agent import SportmonksPredictionAgent
from worldcup_predictor.agents.specialists.xg_intelligence_agent import XGIntelligenceAgent
from worldcup_predictor.agents.specialists.elo_team_strength_intelligence_agent import (
    EloTeamStrengthIntelligenceAgent,
)
from worldcup_predictor.agents.specialists.xg_chance_quality_intelligence_agent import (
    XGChanceQualityIntelligenceAgent,
)
from worldcup_predictor.agents.specialists.tournament_context_agent import TournamentContextAgent
from worldcup_predictor.agents.specialists.tournament_intelligence_agent import (
    TournamentIntelligenceAgent,
)
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.schedule.context_loader import load_tournament_context


class SpecialistOrchestrator(BaseAgent):
    """Runs all specialist agents then MasterAnalysisAgent."""

    name = "specialist_orchestrator"

    AGENT_CLASSES = (
        WeatherAgent,
        RefereeAgent,
        LineupAgent,
        LineupIntelligenceAgent,
        ExpectedLineupAgent,
        InjurySuspensionAgent,
        InjurySuspensionIntelligenceAgent,
        TeamFormAgent,
        TacticsAgent,
        PlayerQualityAgent,
        EloTeamStrengthIntelligenceAgent,
        XGChanceQualityIntelligenceAgent,
        OddsMarketAgent,
        OddsControlAgent,
        MarketConsensusAgent,
        OddsMovementAgent,
        SharpMoneyIntelligenceAgent,
        SportmonksPredictionAgent,
        XGIntelligenceAgent,
        MotivationPsychologyAgent,
        TournamentIntelligenceAgent,
        TournamentContextAgent,
        MasterAnalysisAgent,
    )

    def run(self, **kwargs: Any) -> AgentResult:
        fixture_id = kwargs.get("fixture_id")
        if fixture_id is None:
            return self._fail("fixture_id is required.")

        self.context.shared["specialist_signals"] = {}
        load_tournament_context(self.context)
        results: list[AgentResult] = []

        for agent_cls in self.AGENT_CLASSES:
            agent = agent_cls(self.context)
            result = agent.run(fixture_id=int(fixture_id))
            results.append(result)

        master_result = results[-1]
        if not master_result.success or not isinstance(master_result.data, MatchSpecialistReport):
            return self._fail("Master analysis failed.", [r.message for r in results if not r.success])

        report: MatchSpecialistReport = master_result.data
        self.context.shared.setdefault("specialist_reports", {})[report.fixture_id] = report
        return self._ok(
            data=report,
            message=f"Specialist analysis complete for fixture {fixture_id}",
        )
