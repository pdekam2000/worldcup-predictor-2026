"""Data quality transparency — phase scores, reasons, display labels (Phase 35A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

MatchPhase = Literal["pre_match", "live", "post_match"]

KICKOFF_NOTE = (
    "Some data is only available close to kickoff or after the match starts."
)

# Core pre-match components (max points)
CORE_WEIGHTS: dict[str, int] = {
    "fixture_identity": 10,
    "team_ids": 10,
    "standings_context": 10,
    "recent_form": 15,
    "injuries": 10,
    "odds": 10,
    "stats": 10,
    "lineups": 15,
    "weather": 5,
    "referee": 5,
}

# Live / post-match only — never penalize pre-match for missing these
LIVE_WEIGHTS: dict[str, int] = {
    "fixture_events": 5,
    "match_statistics_live": 5,
}

# Supplemental RapidAPI bonuses (only when real data returned)
SUPPLEMENTAL_WEIGHTS: dict[str, int] = {
    "supplemental_xg": 10,
    "supplemental_player_stats": 8,
    "supplemental_squad": 5,
    "supplemental_odds": 5,
    "supplemental_weather": 5,
}

DISPLAY_LABELS: dict[str, str] = {
    "fixture_identity": "Fixture identity",
    "team_ids": "Team IDs",
    "recent_form": "Recent form",
    "standings_context": "Standings",
    "injuries": "Injuries",
    "odds": "Odds",
    "stats": "Team stats",
    "lineups": "Lineups",
    "weather": "Weather",
    "referee": "Referee",
    "fixture_events": "Fixture events",
    "match_statistics_live": "Live match statistics",
    "supplemental_xg": "Rapid xG enrichment",
    "supplemental_player_stats": "Rapid player stats",
    "supplemental_squad": "Rapid squad data",
    "supplemental_odds": "Rapid odds enrichment",
    "supplemental_weather": "Rapid weather enrichment",
}

LIVE_STATUS = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})
FINISHED_STATUS = frozenset({"FT", "AET", "PEN", "FINISHED", "AWD", "WO"})


@dataclass
class DataQualityDetail:
    components: dict[str, int] = field(default_factory=dict)
    component_max: dict[str, int] = field(default_factory=dict)
    pre_match_total: int = 0
    live_total: int = 0
    post_match_total: int = 0
    display_total: int = 0
    max_total: int = 100
    match_phase: MatchPhase = "pre_match"
    reason_text: str = ""
    kickoff_note: str = KICKOFF_NOTE

    @property
    def score_ratio(self) -> float:
        return round(self.display_total / self.max_total, 3) if self.max_total else 0.0

    def to_breakdown_dict(self) -> dict[str, int]:
        return dict(self.components)


def detect_match_phase(report: MatchIntelligenceReport) -> MatchPhase:
    fixture = report.fixture
    status = (getattr(fixture, "status", None) or "NS").upper() if fixture else "NS"
    if status in FINISHED_STATUS:
        return "post_match"
    if status in LIVE_STATUS:
        return "live"
    return "pre_match"


def _cap_components(components: dict[str, int]) -> dict[str, int]:
    total = sum(components.values())
    if total <= 100:
        return components
    scale = 100 / total
    return {k: int(v * scale) for k, v in components.items()}


def _sum_keys(components: dict[str, int], keys: set[str]) -> int:
    return sum(components.get(k, 0) for k in keys)


def build_data_quality_reason(
    report: MatchIntelligenceReport,
    detail: DataQualityDetail,
) -> str:
    missing_pre: list[str] = []
    checks = [
        ("lineups", "official lineups"),
        ("injuries", "injuries"),
        ("weather", "weather"),
        ("referee", "referee"),
    ]
    for key, label in checks:
        max_pts = detail.component_max.get(key, 0)
        got = detail.components.get(key, 0)
        if max_pts and got < max_pts:
            if key == "lineups" and got >= max_pts * 2 // 3:
                missing_pre.append("projected lineups (official pending)")
            else:
                missing_pre.append(label)

    rapid_xg = (report.supplemental_sources or {}).get("rapid_xg_statistics") or {}
    rapid_stats = (report.supplemental_sources or {}).get("rapid_football_stats") or {}

    if missing_pre:
        joined = " and ".join(missing_pre[:3])
        base = (
            f"Data Quality is {detail.display_total} because {joined} "
            f"{'are' if len(missing_pre) > 1 else 'is'} not available yet."
        )
    else:
        base = f"Data Quality is {detail.display_total} based on loaded pre-match sources."

    if report.source in ("live", "cache") and not report.is_placeholder:
        base += " Paid API connection is working."
    elif report.is_placeholder:
        base += " Using placeholder/demo fixture data."

    if rapid_xg.get("endpoints_called", 0) and not (
        rapid_xg.get("xg") or rapid_xg.get("npxg") or rapid_xg.get("fixture_detail")
    ):
        base += " RapidAPI XG is configured but returned no matching fixture for this provider."
    elif rapid_stats.get("endpoints_called", 0) and rapid_stats.get("endpoints_loaded", 0) == 0:
        base += " Rapid Football Stats is configured but returned no data for this match."

    return base


def explain_data_quality(report: MatchIntelligenceReport) -> DataQualityDetail:
    """Full transparent data quality detail — no inflation without real data."""
    from worldcup_predictor.data_quality.intelligence_scoring import score_data_quality_components

    components, component_max = score_data_quality_components(report)
    components = _cap_components(components)
    phase = detect_match_phase(report)

    pre_keys = set(CORE_WEIGHTS) | set(SUPPLEMENTAL_WEIGHTS)
    live_keys = set(LIVE_WEIGHTS)

    pre_match_total = _sum_keys(components, pre_keys)
    live_only = _sum_keys(components, live_keys)
    post_match_total = min(100, pre_match_total + live_only)

    if phase == "pre_match":
        display_total = pre_match_total
        live_total = pre_match_total
    elif phase == "live":
        display_total = min(100, pre_match_total + live_only)
        live_total = display_total
    else:
        display_total = post_match_total
        live_total = min(100, pre_match_total + live_only)

    detail = DataQualityDetail(
        components=components,
        component_max=component_max,
        pre_match_total=pre_match_total,
        live_total=live_total,
        post_match_total=post_match_total,
        display_total=display_total,
        match_phase=phase,
    )
    detail.reason_text = build_data_quality_reason(report, detail)
    return detail
