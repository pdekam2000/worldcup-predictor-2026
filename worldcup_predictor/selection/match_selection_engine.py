"""Smart match selection — avoid blind league-wide prediction."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from worldcup_predictor.config.competitions import CompetitionConfig, get_competition
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.selection.models import (
    DailyShortlist,
    MatchSelectionResult,
    MatchSelectionScores,
    SelectionLevel,
)
from worldcup_predictor.schedule.match_center import classify_status


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hours_until(fixture: TournamentFixture, now: datetime) -> float:
    return (fixture.kickoff_time - now).total_seconds() / 3600.0


class MatchSelectionEngine:
    """Score upcoming fixtures and assign selection levels."""

    TOURNAMENT_AUTO_THRESHOLD = 52.0
    LEAGUE_AUTO_THRESHOLD = 68.0
    LEAGUE_MAX_AUTO = 10
    LEAGUE_MAX_WATCHLIST = 15

    def __init__(self, repository: FootballIntelligenceRepository | None = None) -> None:
        self._repo = repository or FootballIntelligenceRepository()

    def evaluate_fixture(
        self,
        fixture: TournamentFixture,
        *,
        competition_key: str,
        data_quality: float = 0.0,
        confidence: float = 0.0,
        lineups_available: bool = False,
        historical_1x2_winrate: float | None = None,
        historical_ou_winrate: float | None = None,
    ) -> MatchSelectionResult:
        comp = get_competition(competition_key)
        now = _utc_now()
        hours = _hours_until(fixture, now) if fixture.kickoff_time else None
        has_odds = self._repo.has_odds_snapshot(fixture.fixture_id)
        has_xg = self._repo.has_xg_snapshot(fixture.fixture_id)

        scores = MatchSelectionScores(
            data_readiness_score=min(100.0, data_quality),
            market_interest_score=self._market_interest(comp, fixture),
            odds_availability_score=100.0 if has_odds else (40.0 if fixture.source == "live" else 0.0),
            model_confidence_score=min(100.0, confidence),
            historical_edge_score=self._historical_edge(historical_1x2_winrate, historical_ou_winrate),
            team_importance_score=self._team_importance(comp, fixture),
            volatility_risk_score=self._volatility_risk(fixture, data_quality),
            lineup_proximity_score=100.0 if lineups_available else (55.0 if hours and hours <= 6 else 25.0),
        )

        level, reason, improvement = self._decide_level(
            comp,
            data_quality=data_quality,
            lineups_available=lineups_available,
            hours=hours,
            has_odds=has_odds,
            has_xg=has_xg,
            total_score=scores.total,
        )

        return MatchSelectionResult(
            fixture_id=fixture.fixture_id,
            competition_key=competition_key,
            match_name=f"{fixture.home_team} vs {fixture.away_team}",
            kickoff_utc=fixture.kickoff_time.isoformat() if fixture.kickoff_time else None,
            level=level,
            scores=scores,
            reason=reason,
            expected_improvement=improvement,
            data_quality=data_quality,
            lineups_available=lineups_available,
            hours_until_kickoff=hours,
        )

    def build_shortlist(
        self,
        fixtures: list[TournamentFixture],
        *,
        competition_key: str,
        days: int = 3,
        data_quality_map: dict[int, float] | None = None,
        confidence_map: dict[int, float] | None = None,
        lineups_map: dict[int, bool] | None = None,
    ) -> DailyShortlist:
        comp = get_competition(competition_key)
        now = _utc_now()
        dq_map = data_quality_map or {}
        conf_map = confidence_map or {}
        lu_map = lineups_map or {}

        perf = self._repo.performance_by_competition()
        comp_1x2 = _market_winrate(perf, competition_key, "1x2")
        comp_ou = _market_winrate(perf, competition_key, "over_under_2_5")

        candidates: list[MatchSelectionResult] = []
        for fixture in fixtures:
            if classify_status(fixture.status) != "upcoming":
                continue
            if fixture.is_placeholder or fixture.source == "placeholder":
                continue
            hours = _hours_until(fixture, now)
            if hours < 0 or hours > days * 24:
                continue
            result = self.evaluate_fixture(
                fixture,
                competition_key=competition_key,
                data_quality=dq_map.get(fixture.fixture_id, 50.0),
                confidence=conf_map.get(fixture.fixture_id, 50.0),
                lineups_available=lu_map.get(fixture.fixture_id, False),
                historical_1x2_winrate=comp_1x2,
                historical_ou_winrate=comp_ou,
            )
            candidates.append(result)
            self._repo.save_selection_decision(
                fixture_id=result.fixture_id,
                competition_key=competition_key,
                selection_level=result.level,
                total_score=result.scores.total,
                scores=result.scores.as_dict(),
                reason=result.reason,
                expected_improvement=result.expected_improvement,
            )

        candidates.sort(key=lambda item: item.scores.total, reverse=True)
        shortlist = DailyShortlist(
            competition_key=competition_key,
            generated_at=now.isoformat(),
        )

        if comp.compensation_type == "tournament":
            for item in candidates:
                if item.level == "AUTO_PREDICT":
                    shortlist.auto_predict.append(item)
                elif item.level == "WAIT_FOR_LINEUPS":
                    shortlist.wait_for_lineups.append(item)
                elif item.level == "WATCHLIST":
                    shortlist.watchlist.append(item)
                else:
                    shortlist.skipped.append(item)
            return shortlist

        auto_pool = [c for c in candidates if c.level in ("AUTO_PREDICT", "WATCHLIST")]
        auto_pool.sort(key=lambda x: x.scores.total, reverse=True)
        for item in auto_pool[: self.LEAGUE_MAX_AUTO]:
            if item.scores.total >= self.LEAGUE_AUTO_THRESHOLD and item.level == "AUTO_PREDICT":
                shortlist.auto_predict.append(item)
            elif item.scores.total >= self.LEAGUE_AUTO_THRESHOLD - 8:
                promoted = replace(
                    item,
                    level="AUTO_PREDICT",
                    reason=item.reason + " (promoted to shortlist top tier)",
                )
                shortlist.auto_predict.append(promoted)
            else:
                shortlist.watchlist.append(item)

        watch_rest = [c for c in candidates if c not in shortlist.auto_predict][: self.LEAGUE_MAX_WATCHLIST]
        for item in watch_rest:
            if item.level == "WAIT_FOR_LINEUPS":
                shortlist.wait_for_lineups.append(item)
            elif item.level == "WATCHLIST" and item not in shortlist.watchlist:
                shortlist.watchlist.append(item)

        for item in candidates:
            if item in shortlist.auto_predict or item in shortlist.watchlist or item in shortlist.wait_for_lineups:
                continue
            shortlist.skipped.append(item)

        return shortlist

    def _decide_level(
        self,
        comp: CompetitionConfig,
        *,
        data_quality: float,
        lineups_available: bool,
        hours: float | None,
        has_odds: bool,
        has_xg: bool,
        total_score: float,
    ) -> tuple[SelectionLevel, str, str]:
        improvement = ""
        if data_quality < 40:
            return (
                "SKIP_LOW_QUALITY",
                f"Data quality {data_quality:.0f}% below minimum threshold (40%).",
                "Improvement expected if API enrichment and standings data become available.",
            )

        is_tournament = comp.compensation_type in ("tournament", "cup")
        auto_threshold = self.TOURNAMENT_AUTO_THRESHOLD if is_tournament else self.LEAGUE_AUTO_THRESHOLD

        if not lineups_available and hours is not None and hours > 6:
            return (
                "WAIT_FOR_LINEUPS",
                "Official lineups not available yet and kickoff is more than 6 hours away.",
                "Selection score likely improves after lineup-final refresh.",
            )

        if is_tournament:
            if total_score >= auto_threshold and data_quality >= 45:
                reason = f"Tournament mode: selection score {total_score:.1f} with data quality {data_quality:.0f}%."
                if has_odds and has_xg:
                    reason += " Odds and xG enrichment available."
                elif has_odds:
                    reason += " Odds available."
                return ("AUTO_PREDICT", reason, improvement or "Monitor live status updates.")
            if total_score >= auto_threshold - 12:
                return ("WATCHLIST", f"Tournament watchlist: score {total_score:.1f}.", "Await higher confidence or lineups.")
            if data_quality < 50:
                return ("SKIP_LOW_QUALITY", f"Data quality {data_quality:.0f}% limits auto analysis.", improvement)
            return ("SKIP_LOW_INTEREST", f"Selection score {total_score:.1f} below tournament auto threshold.", "")

        if total_score >= auto_threshold and data_quality >= 60 and (has_odds or data_quality >= 70):
            reason = f"League shortlist: score {total_score:.1f}, data quality {data_quality:.0f}%."
            if has_odds:
                reason += " Odds confirmation available."
            return ("AUTO_PREDICT", reason, improvement or "Strongest league candidates only.")
        if total_score >= auto_threshold - 10 and data_quality >= 50:
            return ("WATCHLIST", f"League watchlist candidate (score {total_score:.1f}).", "May promote after lineups/odds.")
        if not lineups_available:
            return ("WAIT_FOR_LINEUPS", "League mode: waiting for lineups before auto prediction.", "Lineup-final version recommended.")
        if data_quality < 50:
            return ("SKIP_LOW_QUALITY", f"League mode: data quality {data_quality:.0f}% too low.", "")
        return ("SKIP_LOW_INTEREST", f"League mode: score {total_score:.1f} below auto threshold {auto_threshold:.0f}.", "")

    @staticmethod
    def _market_interest(comp: CompetitionConfig, fixture: TournamentFixture) -> float:
        if comp.compensation_type == "tournament":
            return 85.0 if "Group" in (fixture.round or "") else 75.0
        if comp.compensation_type == "league":
            return 65.0
        return 55.0

    @staticmethod
    def _historical_edge(one_x_two: float | None, ou: float | None) -> float:
        rates = [r for r in (one_x_two, ou) if r is not None]
        if not rates:
            return 50.0
        avg = sum(rates) / len(rates)
        return min(100.0, avg * 100)

    @staticmethod
    def _team_importance(comp: CompetitionConfig, fixture: TournamentFixture) -> float:
        if comp.compensation_type == "tournament":
            return 80.0
        return 60.0

    @staticmethod
    def _volatility_risk(fixture: TournamentFixture, data_quality: float) -> float:
        risk = 30.0
        if data_quality < 50:
            risk += 25.0
        if fixture.status not in ("NS", "TBD", "SCHEDULED", "TIMED"):
            risk += 15.0
        return min(100.0, risk)


def _market_winrate(perf: list[dict], competition_key: str, market: str) -> float | None:
    for row in perf:
        if row.get("competition_key") == competition_key and row.get("market") == market:
            return row.get("winrate")
    return None
