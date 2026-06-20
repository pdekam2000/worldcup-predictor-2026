"""Expected Lineup Agent — Phase 22F (benchmark/trace, no WDE changes)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.lineups.expected_lineup_cache import (
    get_cached_expected_lineup,
    get_or_build_expected_lineup,
)
from worldcup_predictor.lineups.expected_lineup_intelligence_engine import (
    build_expected_lineup_intelligence,
    reconcile_expected_with_prior,
)
from worldcup_predictor.lineups.expected_lineup_store import (
    ExpectedLineupAccuracyRecord,
    ExpectedLineupAccuracyStore,
)


class ExpectedLineupAgent(BaseAgent):
    """
    Dedicated expected lineup intelligence — projects XI before confirmation,
    compares vs confirmed when available, stores accuracy history (trace only).
    """

    name = "expected_lineup_agent"
    domain = "expected_lineup_intelligence"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        fixture_id = int(kwargs.get("fixture_id") or report.fixture_id)
        fixture = report.fixture
        kickoff = getattr(fixture, "kickoff_utc", None) if fixture else None
        match_name = ""
        if fixture:
            match_name = f"{getattr(fixture, 'home_team', report.home_team.team_name)} vs {getattr(fixture, 'away_team', report.away_team.team_name)}"

        api_client = None
        try:
            if self.context.settings.api_football_configured:
                from worldcup_predictor.clients.api_football import ApiFootballClient

                api_client = ApiFootballClient(self.context.settings)
        except Exception:
            api_client = None

        signals_map: dict[str, Any] = self.context.shared.get("specialist_signals") or {}

        prior_cached = get_cached_expected_lineup(fixture_id, settings=self.context.settings)

        def _build() -> dict[str, Any]:
            intel = build_expected_lineup_intelligence(
                report,
                api_client=api_client,
                specialist_signals=signals_map,
            )
            intel = reconcile_expected_with_prior(intel, prior_cached)
            return intel.to_dict()

        payload, from_cache = get_or_build_expected_lineup(
            fixture_id,
            kickoff_utc=kickoff,
            build_fn=_build,
            settings=self.context.settings,
        )

        if payload.get("confirmed_available") and prior_cached:
            fresh = reconcile_expected_with_prior(
                build_expected_lineup_intelligence(
                    report,
                    api_client=api_client,
                    specialist_signals=signals_map,
                ),
                prior_cached,
            )
            payload = fresh.to_dict()
            from_cache = False

        has_data = bool(payload.get("data_sources"))
        status = "unavailable" if not has_data else "available"
        if has_data and payload.get("lineup_confidence", 0) < 40:
            status = "partial"
        if payload.get("confirmed_available"):
            status = "available"

        store = ExpectedLineupAccuracyStore()
        record = ExpectedLineupAccuracyRecord(
            fixture_id=fixture_id,
            prediction_timestamp=payload.get("cached_at") or datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            expected_lineup_snapshot=payload.get("expected_snapshot") or {},
            confirmed_lineup_snapshot=payload.get("confirmed_snapshot") if payload.get("confirmed_available") else None,
            comparison_available=bool(payload.get("comparison_available")),
            player_overlap_pct=payload.get("player_overlap_pct"),
            goalkeeper_match=payload.get("goalkeeper_change_flag") is False if payload.get("comparison_available") else None,
            formation_match=_formation_match_from_snapshot(payload),
            surprise_starters=list(payload.get("surprise_starters") or []),
            missed_expected=list(payload.get("missed_expected") or []),
            lineup_confidence=payload.get("lineup_confidence"),
            expected_xi_quality=payload.get("expected_xi_quality"),
            match_name=match_name,
        )
        try:
            store.append(record)
        except Exception:
            pass

        warnings: list[str] = []
        if not has_data:
            warnings.append("Expected lineup data sparse — minimal benchmark.")
        warnings.append(
            "Expected lineup intelligence is trace-only — WDE weights and confidence unchanged."
        )
        if payload.get("goalkeeper_change_flag"):
            warnings.append("Goalkeeper change flag — informational only.")
        if payload.get("late_news_risk") == "high":
            warnings.append("Late news risk elevated — confirmed XI not yet available.")
        if payload.get("comparison_available") and not payload.get("lineup_supports_internal"):
            warnings.append("Expected lineup diverges from Lineup Intelligence V2 — review benchmark.")
        if from_cache:
            warnings.append("Expected lineup served from cache (kickoff-aware TTL).")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            {
                "lineup_confidence": payload["lineup_confidence"],
                "lineup_strength_delta": payload["lineup_strength_delta"],
                "expected_goalkeeper_home": payload["expected_goalkeeper_home"],
                "expected_goalkeeper_away": payload["expected_goalkeeper_away"],
                "goalkeeper_change_flag": payload["goalkeeper_change_flag"],
                "missing_key_players": payload["missing_key_players"],
                "missing_attackers": payload["missing_attackers"],
                "missing_midfielders": payload["missing_midfielders"],
                "missing_defenders": payload["missing_defenders"],
                "rotation_risk": payload["rotation_risk"],
                "expected_formation": payload["expected_formation"],
                "formation_change_risk": payload["formation_change_risk"],
                "expected_xi_quality": payload["expected_xi_quality"],
                "lineup_supports_internal": payload["lineup_supports_internal"],
                "star_player_absence_score": payload["star_player_absence_score"],
                "chemistry_risk": payload["chemistry_risk"],
                "continuity_score": payload["continuity_score"],
                "bench_strength_score": payload["bench_strength_score"],
                "late_news_risk": payload["late_news_risk"],
                "comparison_available": payload["comparison_available"],
                "confirmed_available": payload["confirmed_available"],
                "player_overlap_pct": payload["player_overlap_pct"],
                "surprise_starters": payload.get("surprise_starters") or [],
                "missed_expected": payload.get("missed_expected") or [],
                "expected_snapshot": payload["expected_snapshot"],
                "confirmed_snapshot": payload["confirmed_snapshot"],
                "data_sources": payload["data_sources"],
                "from_cache": from_cache,
                "notes": payload["notes"],
                "version": payload["version"],
                "disclaimer": (
                    "Expected lineup benchmark — does not override scoreline, confidence, or WDE."
                ),
            },
            warnings=warnings,
            missing_data=[] if has_data else ["lineups", "injuries"],
            impact_score=round(float(payload.get("expected_xi_quality") or 50), 1),
            notes="; ".join(payload.get("notes") or []) or "Expected lineup intelligence complete.",
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Expected lineup intelligence complete")


def _formation_match_from_snapshot(payload: dict[str, Any]) -> bool | None:
    if not payload.get("comparison_available"):
        return None
    home_exp = (payload.get("expected_snapshot") or {}).get("home") or {}
    home_conf = (payload.get("confirmed_snapshot") or {}).get("home") or {}
    ef = home_exp.get("formation")
    cf = home_conf.get("formation")
    if ef and cf:
        return str(ef) == str(cf)
    return None
