"""Map continuous confidence scores to Tier A–D."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sklearn.isotonic import IsotonicRegression

from worldcup_predictor.egie.confidence.config import TIER_LABELS
from worldcup_predictor.egie.confidence.models import ConfidenceTier, HybridConfidenceUI


@dataclass
class TierCalibration:
    """Quantile boundaries fitted on hold-out train split (raw score scale)."""

    team_q25: float
    team_q50: float
    team_q75: float
    range_q25: float
    range_q50: float
    range_q75: float
    minute_q25: float
    minute_q50: float
    minute_q75: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": {"q25": self.team_q25, "q50": self.team_q50, "q75": self.team_q75},
            "range": {"q25": self.range_q25, "q50": self.range_q50, "q75": self.range_q75},
            "minute": {"q25": self.minute_q25, "q50": self.minute_q50, "q75": self.minute_q75},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TierCalibration:
        team = data.get("team") or {}
        rng = data.get("range") or {}
        minute = data.get("minute") or {}
        return cls(
            team_q25=float(team.get("q25") or 0.25),
            team_q50=float(team.get("q50") or 0.5),
            team_q75=float(team.get("q75") or 0.75),
            range_q25=float(rng.get("q25") or 0.25),
            range_q50=float(rng.get("q50") or 0.5),
            range_q75=float(rng.get("q75") or 0.75),
            minute_q25=float(minute.get("q25") or 0.25),
            minute_q50=float(minute.get("q50") or 0.5),
            minute_q75=float(minute.get("q75") or 0.75),
        )


@dataclass
class MarketTierCalibrator:
    """Isotonic map from raw confidence to calibrated hit probability, then tier."""

    market: str
    x_thresholds: list[float] = field(default_factory=list)
    y_thresholds: list[float] = field(default_factory=list)
    cal_q25: float = 0.25
    cal_q50: float = 0.5
    cal_q75: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "x_thresholds": self.x_thresholds,
            "y_thresholds": self.y_thresholds,
            "cal_q25": self.cal_q25,
            "cal_q50": self.cal_q50,
            "cal_q75": self.cal_q75,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketTierCalibrator:
        return cls(
            market=str(data.get("market") or ""),
            x_thresholds=[float(x) for x in (data.get("x_thresholds") or [])],
            y_thresholds=[float(y) for y in (data.get("y_thresholds") or [])],
            cal_q25=float(data.get("cal_q25") or 0.25),
            cal_q50=float(data.get("cal_q50") or 0.5),
            cal_q75=float(data.get("cal_q75") or 0.75),
        )

    def predict_calibrated(self, score: float) -> float:
        if not self.x_thresholds:
            return float(score)
        xs = self.x_thresholds
        ys = self.y_thresholds
        s = float(score)
        if s <= xs[0]:
            return float(ys[0])
        if s >= xs[-1]:
            return float(ys[-1])
        for i in range(1, len(xs)):
            if s <= xs[i]:
                x0, x1 = xs[i - 1], xs[i]
                y0, y1 = ys[i - 1], ys[i]
                if x1 == x0:
                    return float(y1)
                t = (s - x0) / (x1 - x0)
                return float(y0 + t * (y1 - y0))
        return float(ys[-1])

    def tier_for_score(self, score: float) -> ConfidenceTier:
        calibrated = self.predict_calibrated(score)
        return score_to_tier(calibrated, self.cal_q25, self.cal_q50, self.cal_q75)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.5
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return round(ordered[idx], 4)


def fit_tier_calibration(
    conf_team: list[float],
    conf_range: list[float],
    conf_minute: list[float],
) -> TierCalibration:
    return TierCalibration(
        team_q25=_quantile(conf_team, 0.25),
        team_q50=_quantile(conf_team, 0.50),
        team_q75=_quantile(conf_team, 0.75),
        range_q25=_quantile(conf_range, 0.25),
        range_q50=_quantile(conf_range, 0.50),
        range_q75=_quantile(conf_range, 0.75),
        minute_q25=_quantile(conf_minute, 0.25),
        minute_q50=_quantile(conf_minute, 0.50),
        minute_q75=_quantile(conf_minute, 0.75),
    )


def fit_market_tier_calibrator(
    confidences: list[float],
    hits: list[int],
    *,
    market: str,
) -> MarketTierCalibrator | None:
    if len(confidences) < 20 or len(confidences) != len(hits):
        return None
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(confidences, hits)
    calibrated = [float(v) for v in iso.predict(confidences)]
    return MarketTierCalibrator(
        market=market,
        x_thresholds=[float(x) for x in iso.X_thresholds_],
        y_thresholds=[float(y) for y in iso.y_thresholds_],
        cal_q25=_quantile(calibrated, 0.25),
        cal_q50=_quantile(calibrated, 0.50),
        cal_q75=_quantile(calibrated, 0.75),
    )


def score_to_tier(score: float, q25: float, q50: float, q75: float) -> ConfidenceTier:
    if score >= q75:
        return "A"
    if score >= q50:
        return "B"
    if score >= q25:
        return "C"
    return "D"


def map_tiers(
    *,
    conf_team: float,
    conf_range: float,
    conf_minute: float,
    calibration: TierCalibration,
    team_calibrator: MarketTierCalibrator | None = None,
    range_calibrator: MarketTierCalibrator | None = None,
    minute_calibrator: MarketTierCalibrator | None = None,
) -> tuple[ConfidenceTier, ConfidenceTier, ConfidenceTier, ConfidenceTier]:
    if team_calibrator:
        team_tier = team_calibrator.tier_for_score(conf_team)
    else:
        team_tier = score_to_tier(
            conf_team, calibration.team_q25, calibration.team_q50, calibration.team_q75
        )
    if range_calibrator:
        range_tier = range_calibrator.tier_for_score(conf_range)
    else:
        range_tier = score_to_tier(
            conf_range, calibration.range_q25, calibration.range_q50, calibration.range_q75
        )
    if minute_calibrator:
        minute_tier = minute_calibrator.tier_for_score(conf_minute)
    else:
        minute_tier = score_to_tier(
            conf_minute, calibration.minute_q25, calibration.minute_q50, calibration.minute_q75
        )
    display_score = max(
        team_calibrator.predict_calibrated(conf_team) if team_calibrator else conf_team,
        range_calibrator.predict_calibrated(conf_range) if range_calibrator else conf_range,
    )
    display_q25 = max(calibration.team_q25, calibration.range_q25)
    display_q50 = max(calibration.team_q50, calibration.range_q50)
    display_q75 = max(calibration.team_q75, calibration.range_q75)
    if team_calibrator and range_calibrator:
        display_q25 = max(team_calibrator.cal_q25, range_calibrator.cal_q25)
        display_q50 = max(team_calibrator.cal_q50, range_calibrator.cal_q50)
        display_q75 = max(team_calibrator.cal_q75, range_calibrator.cal_q75)
    display_tier = score_to_tier(display_score, display_q25, display_q50, display_q75)
    return team_tier, range_tier, minute_tier, display_tier


def build_ui(
    *,
    team_tier: ConfidenceTier,
    range_tier: ConfidenceTier,
    minute_tier: ConfidenceTier,
    predicted_team_none: bool,
) -> HybridConfidenceUI:
    team_badge = "Directional Pick"
    if predicted_team_none:
        team_badge = "No Directional Edge"
    return HybridConfidenceUI(
        team_label=f"Tier {team_tier}",
        team_badge=team_badge,
        range_label=f"Tier {range_tier}",
        range_show_probability_bar=True,
        minute_label="Estimate Only",
        minute_badge="Experimental",
    )
