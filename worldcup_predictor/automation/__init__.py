"""Pre-match automation — scan, predict, and refresh before kickoff."""

from worldcup_predictor.automation.models import PreMatchAutomationResult
from worldcup_predictor.automation.prematch_scheduler import PreMatchScheduler

__all__ = ["PreMatchAutomationResult", "PreMatchScheduler"]
