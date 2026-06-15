from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.schedule.context_loader import fixture_tournament_context, load_tournament_context
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport


class WeatherAgent(BaseAgent):
    name = "weather_agent"
    domain = "weather"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None or report.fixture is None:
            return self._fail("No fixture intelligence available.")

        fixture = report.fixture
        weather = report.weather or {}
        warnings: list[str] = []
        missing: list[str] = []

        if weather.get("available"):
            temp = weather.get("temperature_c")
            rain = weather.get("rain_probability")
            wind = weather.get("wind_speed_kmh")
            humidity = weather.get("humidity_pct")
            impact = weather.get("weather_impact_score")
            source = weather.get("source") or weather.get("provider") or "live"
            status = "available"
            notes = f"Venue weather from {source} (backup enrichment when primary missing)."
            signal = make_signal(
                self.name,
                self.domain,
                status,
                {
                    "temperature_c": temp,
                    "rain_probability": rain,
                    "wind_speed_kmh": wind,
                    "humidity_pct": humidity,
                    "weather_impact_score": impact,
                    "weather_source": source,
                    "condition": weather.get("condition"),
                    "venue": fixture.venue,
                    "kickoff_utc": fixture.kickoff_utc.isoformat(),
                },
                warnings=warnings,
                missing_data=missing,
                impact_score=float(impact) if impact is not None else 50.0,
                notes=notes,
            )
            self._store(signal)
            return self._ok(data=signal, message="Weather signals prepared from live data")

        missing.append("weather")
        warnings.append("Weather data unavailable — prediction continues without weather factor.")
        signal = make_signal(
            self.name,
            self.domain,
            "unavailable",
            {
                "weather_impact_score": None,
                "weather_source": None,
                "venue": fixture.venue,
                "kickoff_utc": fixture.kickoff_utc.isoformat(),
            },
            warnings=warnings,
            missing_data=missing,
            impact_score=50.0,
            notes="No weather provider data available for this venue.",
        )
        self._store(signal)
        return self._ok(data=signal, message="Weather unavailable")

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class RefereeAgent(BaseAgent):
    name = "referee_agent"
    domain = "referee"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None or report.fixture is None:
            return self._fail("No fixture intelligence available.")

        referee = report.fixture.referee
        if not referee:
            signal = make_signal(
                self.name,
                self.domain,
                "unavailable",
                {},
                warnings=["Referee not assigned or not available in fixture data."],
                missing_data=["referee"],
            )
            self._store(signal)
            return self._ok(data=signal, message="Referee unavailable")

        signal = make_signal(
            self.name,
            self.domain,
            "placeholder" if report.is_placeholder else "partial",
            {
                "referee_name": referee,
                "cards_per_match": 4.2,
                "penalties_per_match": 0.35,
                "fouls_profile": "moderate",
                "strictness_score": 62.0,
                "referee_impact_score": 58.0,
            },
            impact_score=58.0,
            notes="Referee profile estimated from historical placeholder baseline.",
        )
        self._store(signal)
        return self._ok(data=signal, message=f"Referee profile for {referee}")

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class LineupAgent(BaseAgent):
    name = "lineup_agent"
    domain = "lineups"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        items = (report.lineups or {}).get("items") or []
        predicted_available = bool(items)
        official = report.fixture.status if report.fixture else "NS"
        official_available = official in ("1H", "2H", "HT", "FT", "LIVE")

        key_starting: list[str] = []
        missing_key: list[str] = []
        formations: list[str] = []

        for lineup in items:
            formation = lineup.get("formation")
            if formation:
                formations.append(f"{lineup.get('team', {}).get('name', '?')}: {formation}")
            for entry in lineup.get("startXI") or []:
                name = entry.get("player", {}).get("name")
                if name:
                    key_starting.append(name)

        status = "unavailable"
        if official_available:
            status = "available"
        elif predicted_available:
            status = "partial" if report.is_placeholder else "available"
        elif report.is_placeholder:
            status = "placeholder"

        confidence = 75.0 if official_available else (55.0 if predicted_available else 25.0)
        warnings = []
        if not official_available:
            warnings.append("Official lineups not confirmed — wait for published lineups.")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            {
                "official_lineups_available": official_available,
                "predicted_lineups_available": predicted_available,
                "key_players_starting": key_starting[:6],
                "missing_key_players": missing_key,
                "formation_notes": formations,
                "lineup_confidence_score": confidence,
            },
            warnings=warnings,
            impact_score=confidence,
        )
        self._store(signal)
        return self._ok(data=signal, message="Lineup signals prepared")

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class InjurySuspensionAgent(BaseAgent):
    name = "injury_suspension_agent"
    domain = "injuries_suspensions"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        home_inj = report.home_team.injuries.players if report.home_team.injuries else []
        away_inj = report.away_team.injuries.players if report.away_team.injuries else []

        injured = [
            {"team": report.home_team.team_name, **p} for p in home_inj
        ] + [{"team": report.away_team.team_name, **p} for p in away_inj]

        doubtful = [p for p in injured if "doubt" in str(p.get("player", {}).get("type", "")).lower()]
        suspended: list[dict[str, Any]] = []

        absence_score = min(90.0, 30.0 + len(injured) * 12 + len(suspended) * 15)
        status = "placeholder" if report.is_placeholder else "partial"
        if "injuries" in report.missing_data:
            status = "unavailable"

        signal = make_signal(
            self.name,
            self.domain,
            status,
            {
                "injured_players": injured,
                "suspended_players": suspended,
                "doubtful_players": doubtful,
                "key_absence_score": absence_score,
            },
            warnings=["Absence data may be incomplete — not all suspensions reported."],
            missing_data=["injuries"] if "injuries" in report.missing_data else [],
            impact_score=absence_score,
            notes="Higher key_absence_score indicates more squad disruption.",
        )
        self._store(signal)
        return self._ok(data=signal, message="Injury/suspension signals prepared")

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class TeamFormAgent(BaseAgent):
    name = "team_form_agent"
    domain = "form"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        home_form = self._form_score(report.home_team.form)
        away_form = self._form_score(report.away_team.form)
        home_stats = report.home_team.statistics or {}
        away_stats = report.away_team.statistics or {}

        signal = make_signal(
            self.name,
            self.domain,
            "placeholder" if report.is_placeholder else "partial",
            {
                "form_score_home": home_form,
                "form_score_away": away_form,
                "goals_for_avg_home": self._goal_avg(home_stats, "for"),
                "goals_for_avg_away": self._goal_avg(away_stats, "for"),
                "goals_against_avg_home": self._goal_avg(home_stats, "against"),
                "goals_against_avg_away": self._goal_avg(away_stats, "against"),
                "clean_sheet_rate_home": self._clean_sheet_rate(home_stats),
                "clean_sheet_rate_away": self._clean_sheet_rate(away_stats),
                "scoring_trend": "stable" if abs(home_form - away_form) < 10 else "diverging",
            },
            impact_score=round((home_form + away_form) / 2, 1),
        )
        self._store(signal)
        return self._ok(data=signal, message="Team form signals prepared")

    @staticmethod
    def _form_score(form: list[str] | None) -> float:
        if not form:
            return 50.0
        pts = {"W": 3, "D": 1, "L": 0}
        return round(sum(pts.get(r.upper(), 1) for r in form) / max(len(form), 1) * 33.3, 1)

    @staticmethod
    def _goal_avg(stats: dict, side: str) -> float:
        avg = stats.get("goals", {}).get(side, {}).get("total", {}).get("average")
        try:
            return float(avg)
        except (TypeError, ValueError):
            return 1.3

    @staticmethod
    def _clean_sheet_rate(stats: dict) -> float:
        clean = stats.get("clean_sheet", {}).get("total")
        played = stats.get("fixtures", {}).get("played", {}).get("total", 5)
        if clean is not None and played:
            return round(int(clean) / max(int(played), 1), 2)
        return 0.2

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class TacticsAgent(BaseAgent):
    name = "tactics_agent"
    domain = "tactics"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        home_stats = report.home_team.statistics or {}
        away_stats = report.away_team.statistics or {}
        formations = (report.lineups or {}).get("items") or []
        supplemental = getattr(report, "supplemental_sources", None) or {}
        rapid_stats = supplemental.get("rapid_football_stats") or {}
        rapid_xg = supplemental.get("rapid_xg_statistics") or {}

        home_xg, home_xga, home_npxg = self._xg_triplet(home_stats, rapid_stats, rapid_xg, side="home")
        away_xg, away_xga, away_npxg = self._xg_triplet(away_stats, rapid_stats, rapid_xg, side="away")
        home_shots = self._stat_float(home_stats, "shots", "total")
        away_shots = self._stat_float(away_stats, "shots", "total")
        home_poss = self._possession_hint(home_stats, formations, 0, rapid_stats, "home")
        away_poss = self._possession_hint(away_stats, formations, 1, rapid_stats, "away")

        home_attack = self._attack_strength(home_xg, home_shots, home_stats)
        away_attack = self._attack_strength(away_xg, away_shots, away_stats)
        home_def_weak = self._defense_weakness(home_xga, away_stats)
        away_def_weak = self._defense_weakness(away_xga, home_stats)

        combined_goals = self._goal_avg(home_stats) + self._goal_avg(away_stats)
        xg_pressure = round((home_attack + away_attack) / 2, 1)
        if home_xg and away_xg:
            xg_pressure = round(float(home_xg) + float(away_xg), 2)

        over_under = "balanced"
        if combined_goals > 2.6 or xg_pressure >= 2.8:
            over_under = "over_lean"
        elif combined_goals < 2.2 or xg_pressure <= 2.0:
            over_under = "under_lean"

        style_bits = []
        if home_poss >= 52:
            style_bits.append(f"{report.home_team.team_name} control possession")
        else:
            style_bits.append(f"{report.home_team.team_name} direct transitions")
        if away_poss >= 52:
            style_bits.append(f"{report.away_team.team_name} control possession")
        else:
            style_bits.append(f"{report.away_team.team_name} direct transitions")

        signal = make_signal(
            self.name,
            self.domain,
            "partial" if (home_xg or away_xg) else ("placeholder" if report.is_placeholder else "partial"),
            {
                "pressing_style_home": "high" if home_poss < 48 else "medium",
                "pressing_style_away": "high" if away_poss < 48 else "medium",
                "possession_style_home": "control" if home_poss >= 52 else "direct",
                "possession_style_away": "control" if away_poss >= 52 else "direct",
                "possession_pct_home": home_poss,
                "possession_pct_away": away_poss,
                "team_xg_home": home_xg,
                "team_xg_away": away_xg,
                "team_xga_home": home_xga,
                "team_xga_away": away_xga,
                "team_npxg_home": home_npxg,
                "team_npxg_away": away_npxg,
                "shots_home": home_shots,
                "shots_away": away_shots,
                "xg_attack_strength_home": home_attack,
                "xg_attack_strength_away": away_attack,
                "xg_defense_weakness_home": home_def_weak,
                "xg_defense_weakness_away": away_def_weak,
                "recent_attacking_trend_home": self._trend_label(home_stats, "for"),
                "recent_attacking_trend_away": self._trend_label(away_stats, "for"),
                "recent_defensive_trend_home": self._trend_label(home_stats, "against"),
                "recent_defensive_trend_away": self._trend_label(away_stats, "against"),
                "over_under_tendency": over_under,
                "expected_goal_pressure": xg_pressure,
                "tactical_style_summary": "; ".join(style_bits),
                "tactical_matchup_notes": (
                    f"xG attack {home_attack:.0f}/{away_attack:.0f} · "
                    f"defensive weakness {home_def_weak:.0f}/{away_def_weak:.0f} · "
                    f"goal pressure {xg_pressure}"
                ),
            },
            impact_score=round((home_attack + away_attack) / 2, 1),
        )
        self._store(signal)
        return self._ok(data=signal, message="Tactics/xG signals prepared")

    @staticmethod
    def _xg_triplet(
        stats: dict,
        rapid_stats: dict,
        rapid_xg: dict,
        *,
        side: str,
    ) -> tuple[float | None, float | None, float | None]:
        xg_block = rapid_stats.get("xg") or rapid_xg.get("xg") or {}
        if isinstance(xg_block, dict):
            xg = TacticsAgent._float_or_none(xg_block.get(side) or xg_block.get(f"{side}_xg"))
            npxg = TacticsAgent._float_or_none(
                (rapid_stats.get("npxg") or rapid_xg.get("npxg") or {}).get(side)
                if isinstance(rapid_stats.get("npxg") or rapid_xg.get("npxg"), dict)
                else None
            )
        else:
            xg = TacticsAgent._float_or_none(xg_block)
            npxg = None
        xga = TacticsAgent._float_or_none(
            stats.get("goals", {}).get("against", {}).get("total", {}).get("average")
        )
        if xg is None:
            xg = TacticsAgent._float_or_none(
                stats.get("goals", {}).get("for", {}).get("expected", {}).get("total")
            )
        return xg, xga, npxg

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stat_float(stats: dict, group: str, field: str) -> float | None:
        try:
            val = stats.get(group, {}).get(field, {}).get("total")
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _attack_strength(xg: float | None, shots: float | None, stats: dict) -> float:
        base = 50.0
        if xg is not None:
            base += min(xg * 12, 30)
        if shots is not None:
            base += min(shots * 0.8, 15)
        base += TacticsAgent._goal_avg(stats) * 8
        return round(min(base, 95.0), 1)

    @staticmethod
    def _defense_weakness(xga: float | None, opponent_stats: dict) -> float:
        base = 50.0
        if xga is not None:
            base += min(xga * 10, 25)
        base += TacticsAgent._goal_avg(opponent_stats) * 6
        return round(min(base, 95.0), 1)

    @staticmethod
    def _trend_label(stats: dict, side: str) -> str:
        avg = TacticsAgent._goal_avg_side(stats, side)
        if avg >= 1.8:
            return "rising_attack" if side == "for" else "leaky"
        if avg <= 1.0:
            return "low_output" if side == "for" else "solid"
        return "stable"

    @staticmethod
    def _goal_avg_side(stats: dict, side: str) -> float:
        avg = stats.get("goals", {}).get(side, {}).get("total", {}).get("average")
        try:
            return float(avg)
        except (TypeError, ValueError):
            return 1.3

    @staticmethod
    def _goal_avg(stats: dict) -> float:
        return TacticsAgent._goal_avg_side(stats, "for")

    @staticmethod
    def _possession_hint(
        stats: dict,
        formations: list,
        index: int,
        rapid_stats: dict,
        side: str,
    ) -> float:
        match_stats = rapid_stats.get("match_statistics") or {}
        if isinstance(match_stats, dict):
            poss = match_stats.get(f"{side}_possession") or match_stats.get("possession", {}).get(side)
            val = TacticsAgent._float_or_none(poss)
            if val is not None:
                return val
        if index < len(formations):
            form = formations[index].get("formation", "")
            if form.startswith("3") or form.startswith("4-3"):
                return 54.0
        return 48.0

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class PlayerQualityAgent(BaseAgent):
    name = "player_quality_agent"
    domain = "player_quality"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        home_rating = 74.0 if report.home_team.statistics else 60.0
        away_rating = 72.0 if report.away_team.statistics else 60.0
        supplemental = getattr(report, "supplemental_sources", None) or {}
        player_stats = supplemental.get("rapid_football_stats", {}).get("player_statistics") or []

        structured_candidates: list[dict[str, Any]] = []
        for lineup in (report.lineups or {}).get("items") or []:
            team = lineup.get("team", {}).get("name", "")
            for idx, entry in enumerate(lineup.get("startXI") or []):
                name = entry.get("player", {}).get("name")
                if not name:
                    continue
                pos = str(entry.get("player", {}).get("pos") or "").upper()
                score = 58.0 - idx * 3 + (5 if pos in {"F", "FW", "ST", "CF"} else 0)
                structured_candidates.append(
                    {
                        "player": name,
                        "team": team,
                        "score": score,
                        "reason": "Starting XI attacker/midfielder",
                        "data_source": "api_sports_lineups",
                    }
                )

        for row in player_stats if isinstance(player_stats, list) else []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("player") or row.get("name") or "")
            team = str(row.get("team") or row.get("team_name") or "")
            goals = row.get("goals") or row.get("season_goals")
            try:
                goal_count = float(goals) if goals is not None else 0.0
            except (TypeError, ValueError):
                goal_count = 0.0
            if name:
                structured_candidates.append(
                    {
                        "player": name,
                        "team": team,
                        "score": 50.0 + goal_count * 8,
                        "reason": "Supplemental season scoring profile",
                        "data_source": "rapid_football_stats",
                    }
                )

        structured_candidates.sort(key=lambda c: c["score"], reverse=True)
        top_candidates = structured_candidates[:3]
        legacy_labels = [
            f"{c['player']} ({c['team']})" for c in top_candidates
        ] or ["TBD (lineups pending)"]

        signal = make_signal(
            self.name,
            self.domain,
            "partial" if top_candidates else ("placeholder" if report.is_placeholder else "partial"),
            {
                "star_player_rating_home": home_rating,
                "star_player_rating_away": away_rating,
                "attacking_quality_score_home": round(home_rating * 0.9, 1),
                "attacking_quality_score_away": round(away_rating * 0.9, 1),
                "defensive_quality_score_home": round(home_rating * 0.85, 1),
                "defensive_quality_score_away": round(away_rating * 0.85, 1),
                "likely_first_scorer_candidates": legacy_labels,
                "first_goal_scorer_candidates": top_candidates,
            },
            impact_score=round((home_rating + away_rating) / 2, 1),
        )
        self._store(signal)
        return self._ok(data=signal, message="Player quality signals prepared")

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class OddsMarketAgent(BaseAgent):
    name = "odds_market_agent"
    domain = "odds_market"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        odds = report.odds
        if odds is None or not odds.available:
            signal = make_signal(
                self.name,
                self.domain,
                "unavailable",
                {"informational_disclaimer": "Odds are informational only — not betting advice."},
                warnings=["Odds snapshot unavailable."],
                missing_data=["odds"],
            )
            self._store(signal)
            return self._ok(data=signal, message="Odds market unavailable")

        implied = self._implied_probs(odds.bookmakers)
        favorite = "home"
        if implied:
            favorite = max(implied, key=implied.get)

        signal = make_signal(
            self.name,
            self.domain,
            "placeholder" if report.is_placeholder else "partial",
            {
                "market_favorite": favorite,
                "implied_probabilities": implied,
                "odds_movement_placeholder": "stable",
                "market_confidence_signal": round(max(implied.values()) * 100, 1) if implied else 50.0,
                "informational_disclaimer": "Odds are informational only — not betting advice.",
            },
            warnings=["Market odds are context signals only — not a betting recommendation."],
            impact_score=round(max(implied.values()) * 100, 1) if implied else 50.0,
        )
        self._store(signal)
        return self._ok(data=signal, message="Odds market signals prepared")

    @staticmethod
    def _implied_probs(bookmakers: list) -> dict[str, float]:
        for bookmaker in bookmakers:
            for bet in bookmaker.get("bets", []):
                if bet.get("name") != "Match Winner":
                    continue
                probs: dict[str, float] = {}
                for value in bet.get("values", []):
                    try:
                        odd = float(value.get("odd", 0))
                        label = value.get("value", "").lower()
                        if odd > 0:
                            key = {"home": "home", "draw": "draw", "away": "away"}.get(label, label)
                            probs[key] = 1 / odd
                    except (TypeError, ValueError):
                        continue
                if probs:
                    total = sum(probs.values())
                    return {k: round(v / total, 3) for k, v in probs.items()}
        return {}

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class MotivationPsychologyAgent(BaseAgent):
    name = "motivation_psychology_agent"
    domain = "motivation"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None or report.fixture is None:
            return self._fail("No fixture intelligence available.")

        stage = report.fixture.stage.lower()
        is_knockout = "round" in stage or "final" in stage or "semi" in stage
        is_opener = "matchday 1" in stage

        load_tournament_context(self.context)
        tctx = fixture_tournament_context(self.context, report.fixture_id)

        home_mot = 70.0 if is_opener else 65.0
        away_mot = 68.0 if is_opener else 63.0
        pressure = "high" if is_knockout else "medium"
        rotation_risk = "low" if is_knockout else "medium"
        warnings: list[str] = []
        notes: list[str] = []

        if tctx:
            home_status = str(tctx.get("home_qualification_status", "unknown"))
            away_status = str(tctx.get("away_qualification_status", "unknown"))
            home_mot, away_mot, rotation_risk, pressure = self._apply_table_context(
                home_mot, away_mot, rotation_risk, pressure, home_status, away_status
            )
            if home_status == "must_win" or away_status == "must_win":
                notes.append("Must-win group pressure detected from table context.")
            if home_status == "likely_qualified" or away_status == "likely_qualified":
                notes.append("Possible rotation risk for already-qualified team.")
            if home_status == "eliminated" or away_status == "eliminated":
                notes.append("Elimination pressure may affect motivation.")
            if tctx.get("is_placeholder"):
                warnings.append("Group table is placeholder/unconfirmed — motivation context limited.")

        signal = make_signal(
            self.name,
            self.domain,
            "placeholder" if report.is_placeholder or (tctx and tctx.get("is_placeholder")) else "partial",
            {
                "motivation_score_home": home_mot,
                "motivation_score_away": away_mot,
                "pressure_level": pressure,
                "rotation_risk": rotation_risk,
                "morale_notes": " ".join(notes) if notes else f"Group stage context for {report.fixture.stage}.",
                "qualification_context": report.fixture.stage,
                "group_pressure": tctx.get("match_importance", "standard") if tctx else "standard",
                "home_qualification_status": tctx.get("home_qualification_status", "unknown") if tctx else "unknown",
                "away_qualification_status": tctx.get("away_qualification_status", "unknown") if tctx else "unknown",
                "goal_difference_importance": "high" if tctx and tctx.get("group") != "TBD" else "unknown",
            },
            warnings=warnings,
            impact_score=round((home_mot + away_mot) / 2, 1),
        )
        self._store(signal)
        return self._ok(data=signal, message="Motivation/psychology signals prepared")

    @staticmethod
    def _apply_table_context(
        home_mot: float,
        away_mot: float,
        rotation_risk: str,
        pressure: str,
        home_status: str,
        away_status: str,
    ) -> tuple[float, float, str, str]:
        if home_status == "must_win":
            home_mot += 8
            pressure = "high"
        if away_status == "must_win":
            away_mot += 8
            pressure = "high"
        if home_status == "eliminated":
            home_mot -= 5
        if away_status == "eliminated":
            away_mot -= 5
        if home_status == "likely_qualified":
            home_mot -= 3
            rotation_risk = "medium"
        if away_status == "likely_qualified":
            away_mot -= 3
            rotation_risk = "medium"
        if home_status == "rotation_risk" or away_status == "rotation_risk":
            rotation_risk = "high"
        return home_mot, away_mot, rotation_risk, pressure

    def _store(self, signal) -> None:
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal


class MasterAnalysisAgent(BaseAgent):
    name = "master_analysis_agent"
    domain = "master_synthesis"

    SPECIALIST_NAMES = (
        "weather_agent",
        "referee_agent",
        "lineup_agent",
        "lineup_intelligence_agent",
        "injury_suspension_agent",
        "injury_suspension_intelligence_agent",
        "team_form_agent",
        "tactics_agent",
        "player_quality_agent",
        "elo_team_strength_intelligence_agent",
        "xg_chance_quality_intelligence_agent",
        "odds_market_agent",
        "odds_control_agent",
        "market_consensus_agent",
        "odds_movement_agent",
        "sharp_money_intelligence_agent",
        "motivation_psychology_agent",
        "tournament_intelligence_agent",
    )

    def run(self, **kwargs: Any) -> AgentResult:
        fixture_id = kwargs.get("fixture_id")
        signals: dict[str, Any] = self.context.shared.get("specialist_signals") or {}

        if not signals:
            return self._fail("No specialist signals to synthesize.")

        load_tournament_context(self.context)
        overview = self.context.shared.get("tournament_context")
        tournament_note = ""
        if overview and overview.health.groups_available:
            tournament_note = "Tournament group context included in synthesis."
            if overview.health.is_placeholder:
                tournament_note = "Placeholder tournament tables included — unconfirmed."

        strongest: list[str] = []
        weakest: list[str] = []
        conflicts: list[str] = []
        adjustments: list[str] = []

        scored = [
            (name, sig.impact_score)
            for name, sig in signals.items()
            if name != self.name and sig.impact_score is not None
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        if scored:
            strongest = [s[0] for s in scored[:3]]
            weakest = [s[0] for s in scored[-2:]]

        if overview and overview.health.groups_available:
            if "motivation_psychology_agent" not in strongest:
                strongest.append("tournament_group_context")
            if overview.health.is_placeholder and "schedule_placeholder" not in weakest:
                weakest.append("schedule_placeholder")

        form_sig = signals.get("team_form_agent")
        odds_sig = signals.get("odds_market_agent")
        odds_control = signals.get("odds_control_agent")
        market_consensus = signals.get("market_consensus_agent")
        odds_movement = signals.get("odds_movement_agent")
        if form_sig and odds_sig and form_sig.is_usable and odds_sig.is_usable:
            form_home = form_sig.signals.get("form_score_home", 50)
            form_away = form_sig.signals.get("form_score_away", 50)
            implied = odds_sig.signals.get("implied_probabilities") or {}
            home_implied = implied.get("home", 0.33)
            if form_home > form_away + 10 and home_implied < 0.35:
                conflicts.append("Form favours home but market implied probability is lower.")
            elif form_away > form_home + 10 and implied.get("away", 0.33) < 0.35:
                conflicts.append("Form favours away but market implied probability is lower.")

        if odds_control and odds_control.signals.get("strong_disagreement_warning"):
            conflicts.append("Odds sources disagree strongly across providers.")

        if market_consensus and market_consensus.signals.get("model_market_agreement") == "low":
            conflicts.append("Market consensus disagrees with model selection — analysis only.")

        if market_consensus and market_consensus.signals.get("disagreement_warning"):
            adjustments.append("Reduce confidence when bookmaker disagreement is elevated.")

        if odds_movement and odds_movement.signals.get("steam_move_detected"):
            conflicts.append("Steam move detected in odds — market shifting quickly (informational).")

        if odds_movement and odds_movement.signals.get("suspicious_volatility"):
            adjustments.append("Treat prediction cautiously during volatile odds movement.")

        sharp_v2 = signals.get("sharp_money_intelligence_agent")
        if sharp_v2 and sharp_v2.signals:
            sv2 = sharp_v2.signals
            if sv2.get("steam_move_detected"):
                conflicts.append("Sharp money steam move detected — market shifting quickly (informational).")
            if sv2.get("reverse_line_movement"):
                conflicts.append("Reverse line movement detected — possible sharp vs public split (analysis only).")
            if "high_market_disagreement" in (sv2.get("risk_flags") or []):
                adjustments.append("Reduce confidence when bookmaker disagreement is elevated (V2).")
            if "extreme_odds_shift" in (sv2.get("risk_flags") or []):
                adjustments.append("Extreme odds shift — treat market signals cautiously.")
            if "low_market_confidence" in (sv2.get("risk_flags") or []):
                adjustments.append("Low market data confidence — minimal sharp-money weight applied.")

        lineup_sig = signals.get("lineup_agent")
        lineup_v2 = signals.get("lineup_intelligence_agent")
        if lineup_sig and lineup_sig.status != "available":
            adjustments.append("Reduce confidence until official lineups confirmed.")
        if lineup_v2 and lineup_v2.signals:
            home_flags = (lineup_v2.signals.get("home") or {}).get("risk_flags") or []
            away_flags = (lineup_v2.signals.get("away") or {}).get("risk_flags") or []
            if "many_rotations" in home_flags + away_flags:
                adjustments.append("Heavy squad rotation — treat lineup-based edges cautiously.")
            if "backup_goalkeeper" in home_flags + away_flags:
                adjustments.append("Backup goalkeeper in XI — possible goal volatility (analysis only).")
            if "key_player_missing" in home_flags + away_flags:
                adjustments.append("Key absences detected — lineup strength reduced.")

        injury_v2 = signals.get("injury_suspension_intelligence_agent")
        if injury_v2 and injury_v2.signals:
            ih = (injury_v2.signals.get("home") or {}).get("risk_flags") or []
            ia = (injury_v2.signals.get("away") or {}).get("risk_flags") or []
            if "severe_injury_crisis" in ih + ia:
                adjustments.append("Severe injury crisis — reduce confidence (analysis only).")
            if "key_goalkeeper_missing" in ih + ia:
                adjustments.append("Key goalkeeper missing — goal volatility elevated (analysis only).")
            if "multiple_absences" in ih + ia:
                adjustments.append("Multiple absences detected — squad depth reduced.")

        tour_v2 = signals.get("tournament_intelligence_agent")
        if tour_v2 and tour_v2.signals:
            flags = tour_v2.signals.get("risk_flags") or []
            if "must_win_match" in flags:
                adjustments.append("Must-win tournament context — motivation elevated (analysis only).")
            if "high_rotation_risk" in flags:
                adjustments.append("High rotation risk from qualification status — treat lineup edges cautiously.")
            if "final_match_pressure" in flags:
                adjustments.append("Final match pressure — reduce overconfidence (analysis only).")
            if "elimination_risk_high" in flags:
                adjustments.append("High elimination risk — tournament volatility elevated.")
            if "low_tournament_data_confidence" in flags:
                adjustments.append("Limited tournament data — minimal tournament weight applied.")

        elo_v2 = signals.get("elo_team_strength_intelligence_agent")
        if elo_v2 and elo_v2.signals:
            ev2 = elo_v2.signals
            flags = ev2.get("risk_flags") or []
            if "large_elo_gap" in flags:
                adjustments.append("Large ELO gap — favourite profile clear (analysis only).")
            if "close_strength_matchup" in flags:
                adjustments.append("Close strength matchup — outcome uncertainty elevated.")
            if "form_mismatch" in flags:
                conflicts.append("Recent form diverges from ELO-based strength expectation.")
            if "defensive_weakness" in flags:
                adjustments.append("Defensive weakness detected — goal volatility possible.")
            if "attacking_advantage" in flags:
                adjustments.append("Attacking advantage profile detected (analysis only).")
            if "recent_decline" in flags:
                adjustments.append("Recent form decline — momentum caution advised.")
            if "unreliable_history" in flags or "low_data_confidence" in flags:
                adjustments.append("Limited team history — minimal ELO weight applied.")

        xg_v2 = signals.get("xg_chance_quality_intelligence_agent")
        if xg_v2 and xg_v2.signals:
            xv2 = xg_v2.signals
            flags = xv2.get("risk_flags") or []
            if "high_chance_creation" in flags:
                adjustments.append("High chance creation profile — goal pressure elevated (analysis only).")
            if "defensive_leak" in flags:
                adjustments.append("Defensive leak in chance prevention — goal volatility possible.")
            if "unsustainable_finishing" in flags:
                adjustments.append("Unsustainably clinical finishing — regression risk noted.")
            if "strong_defensive_prevention" in flags:
                adjustments.append("Strong defensive chance prevention — under lean possible.")
            if "low_xg_data_confidence" in flags or "limited_statistics" in flags:
                adjustments.append("Limited xG/shooting data — minimal chance-quality weight applied.")
            if xv2.get("goals_pressure_score", 50) >= 72:
                adjustments.append("Elevated goals pressure from chance quality metrics (analysis only).")

        weather_sig = signals.get("weather_agent")
        if weather_sig and weather_sig.signals.get("rain_probability", 0) > 0.4:
            adjustments.append("Slightly favour under goals in wet conditions.")

        agg_scores = [s for _, s in scored]
        aggregated = round(sum(agg_scores) / len(agg_scores), 1) if agg_scores else 50.0

        summary_parts = [
            f"Aggregated from {len(scored)} specialist domains.",
            f"Strongest inputs: {', '.join(strongest) or 'none'}.",
        ]
        if tournament_note:
            summary_parts.append(tournament_note)
        if conflicts:
            summary_parts.append(f"Conflicts detected: {len(conflicts)}.")

        master = make_signal(
            self.name,
            self.domain,
            "partial" if conflicts else "available",
            {
                "aggregated_signal_score": aggregated,
                "strongest_factors": strongest,
                "weakest_factors": weakest,
                "conflicts_between_agents": conflicts,
                "recommended_prediction_adjustments": adjustments,
                "final_context_summary": " ".join(summary_parts),
                "tournament_context_included": bool(overview and overview.health.groups_available),
                "schedule_is_placeholder": bool(overview and overview.health.is_placeholder),
            },
            warnings=["Master synthesis is analytical context only — not a final prediction."],
            impact_score=aggregated,
        )
        signals[self.name] = master
        self.context.shared["specialist_signals"] = signals

        from worldcup_predictor.domain.specialist import MatchSpecialistReport

        intel_reports = self.context.shared.get("intelligence_reports") or {}
        fid = int(fixture_id) if fixture_id is not None else (
            next(iter(intel_reports)) if intel_reports else 0
        )

        report_obj = MatchSpecialistReport(
            fixture_id=fid,
            signals={k: v for k, v in signals.items() if k != self.name},
            master=master,
            source="placeholder",
        )
        self.context.shared.setdefault("specialist_reports", {})[fid] = report_obj

        intel_reports = self.context.shared.get("intelligence_reports") or {}
        if fid in intel_reports:
            intel_reports[fid].specialist_report = report_obj

        return self._ok(data=report_obj, message="Master analysis complete")
