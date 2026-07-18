"""Challenger models package."""

from worldcup_predictor.challenger.models.base import ChallengerModel
from worldcup_predictor.challenger.models.gbgm import GBGMChallenger, available_backends, goals_to_markets

__all__ = ["ChallengerModel", "GBGMChallenger", "available_backends", "goals_to_markets"]
