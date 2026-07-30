"""TeamFormH2HForensicAgent — owner-only prematch forensic validation."""

from worldcup_predictor.research.team_form_h2h_forensic.agent import (
    TeamFormH2HForensicAgent,
    get_fixture_team_forensic_analysis,
    run_forensic_batch,
)
from worldcup_predictor.research.team_form_h2h_forensic.constants import (
    AGENT_NAME,
    CLASSIFICATIONS,
    RULE_VERSION,
)

__all__ = [
    "AGENT_NAME",
    "CLASSIFICATIONS",
    "RULE_VERSION",
    "TeamFormH2HForensicAgent",
    "get_fixture_team_forensic_analysis",
    "run_forensic_batch",
]
