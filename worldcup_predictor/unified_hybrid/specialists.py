"""Specialist adapters — read-only wrappers around existing engines."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.database.postgres.session import postgres_configured
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository
from worldcup_predictor.predops.egie_snapshot import build_egie_snapshot
from worldcup_predictor.predops.markets import build_market_snapshot


def _parse_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    raw = row.get("payload_json") or row.get("payload")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _gt_payload_from_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    for key in ("prediction_payload", "payload_json", "payload"):
        val = row.get(key)
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                continue
    return {
        k: row[k]
        for k in (
            "first_goal_team",
            "first_goal_time_range",
            "estimated_first_goal_minute",
            "next_goal_team",
            "team_goals_home",
            "team_goals_away",
            "confidence",
            "tier",
            "no_prediction_flag",
        )
        if row.get(k) is not None
    }


class ClassicSpecialist:
    """Reads cached Classic/WDE production output — does not invoke PredictPipeline."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)

    def load(self, fixture_id: int, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload is not None:
            classic_payload = payload
        else:
            row = self.repo.get_worldcup_stored_prediction(int(fixture_id))
            classic_payload = _parse_payload(row)

        if not classic_payload:
            return {"status": "missing", "markets": {}, "payload": {}}

        snapshot = build_market_snapshot(classic_payload)
        return {
            "status": "ok",
            "payload": classic_payload,
            "market_snapshot": snapshot,
            "engine_version": classic_payload.get("prediction_engine_version") or "classic-wde",
        }


class EGIESpecialist:
    """Reads cached EGIE output from goal_timing store — does not re-run engine by default."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = GoalTimingRepository(self.settings)

    def load(self, fixture_id: int, *, classic_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not postgres_configured(self.settings):
            return {"status": "missing", "snapshot": {"status": "missing", "reason": "postgres_unavailable"}, "payload": {}}

        row = self.repo.get_prediction_by_fixture(int(fixture_id))
        gt_payload = _gt_payload_from_row(row)
        merged = dict(classic_payload or {})
        if gt_payload:
            merged["goal_timing"] = gt_payload
        snapshot = build_egie_snapshot(merged)

        if snapshot.get("status") in ("missing", "unavailable") and not gt_payload:
            return {"status": snapshot.get("status", "missing"), "snapshot": snapshot, "payload": {}}

        return {
            "status": "ok" if snapshot.get("status") not in ("missing",) else snapshot.get("status"),
            "snapshot": snapshot,
            "payload": gt_payload,
            "engine_version": snapshot.get("model_version") or "egie-goal-timing",
        }


class OddsMarketSpecialist:
    @staticmethod
    def summarize(provider_fields: dict[str, Any]) -> dict[str, Any]:
      home = provider_fields.get("odds_implied_home")
      draw = provider_fields.get("odds_implied_draw")
      away = provider_fields.get("odds_implied_away")
      movement = provider_fields.get("odds_movement_signal") or provider_fields.get("odds_drift")
      if home is None and draw is None and away is None:
          return {"status": "missing"}
      top = max(
          [("home", home or 0), ("draw", draw or 0), ("away", away or 0)],
          key=lambda x: x[1],
      )
      return {
          "status": "ok",
          "implied_home": home,
          "implied_draw": draw,
          "implied_away": away,
          "implied_favorite": top[0],
          "odds_movement": movement,
      }


class LineupInjurySpecialist:
    @staticmethod
    def summarize(features: dict[str, Any]) -> dict[str, Any]:
      return {
          "lineup_strength_home": features.get("lineup_strength", {}).get("home"),
          "lineup_strength_away": features.get("lineup_strength", {}).get("away"),
          "injuries_home": features.get("injuries_impact", {}).get("home"),
          "injuries_away": features.get("injuries_impact", {}).get("away"),
      }
