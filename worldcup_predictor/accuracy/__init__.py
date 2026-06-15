"""Live prediction history and model evaluation accuracy tracking."""

from worldcup_predictor.accuracy.service import AccuracyTrackerService, record_match_prediction

__all__ = ["AccuracyTrackerService", "record_match_prediction"]
