"""Phase 60C — Goal event historical backfill (cache-first, research-safe)."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.guards import ingest_mode
from worldcup_predictor.egie.readers.api_football_raw import load_goal_events_from_egie
from worldcup_predictor.egie.uefa_club.feature_extractors import _fixture_data, parse_uefa_goal_events
from worldcup_predictor.outcomes.event_parser import parse_api_football_goal_events
from worldcup_predictor.outcomes.models import GoalEvent
from worldcup_predictor.research.first_goal_timing_distribution import FirstGoalTimingResearch

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "phase60c_goal_event_backfill"
PHASE60B_SUMMARY = ROOT / "artifacts" / "phase60b_first_goal_timing_distribution" / "first_goal_timing_summary.json"

FINISHED_STATUSES = ("FT", "AET", "PEN", "FINISHED")
PRIORITY_COMPETITIONS = (
    "world_cup_2026",
    "world_cup",
    "champions_league",
    "europa_league",
    "conference_league",
    "premier_league",
)
UEFA_KEYS = frozenset({"champions_league", "europa_league", "conference_league"})


@dataclass
class BackfillCandidate:
    fixture_id: int
    competition_key: str
    season: int | None
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    priority_rank: int
    has_sqlite_events: bool
    has_egie_events: bool
    has_cache_events: bool
    has_enrichment_events: bool

    def to_csv_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "season": self.season if self.season is not None else "",
            "home_team": self.home_team,
            "away_team": self.away_team,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "priority_rank": self.priority_rank,
            "has_sqlite_events": int(self.has_sqlite_events),
            "has_egie_events": int(self.has_egie_events),
            "has_cache_events": int(self.has_cache_events),
            "has_enrichment_events": int(self.has_enrichment_events),
        }


@dataclass
class BackfillResult:
    fixture_id: int
    competition_key: str
    provider: str
    events_added: int
    source: str
    api_call: bool = False
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "provider": self.provider,
            "events_added": self.events_added,
            "source": self.source,
            "api_call": self.api_call,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class GoalEventBackfillRunner:
    settings: Settings | None = None
    max_api_calls: int = 20
    max_backfill_attempts: int = 100
    api_calls_used: int = 0
    results: list[BackfillResult] = field(default_factory=list)
    candidates: list[BackfillCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self._cache_events_index: dict[int, list[dict[str, Any]]] | None = None
        self._egie_fixture_ids: set[int] | None = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.repo._conn)
        conn.row_factory = sqlite3.Row
        return conn

    def _priority_rank(self, competition_key: str) -> int:
        key = str(competition_key or "").lower()
        if key in PRIORITY_COMPETITIONS:
            return PRIORITY_COMPETITIONS.index(key)
        if "world_cup" in key:
            return 0
        if key in UEFA_KEYS:
            return 3
        return 99

    def find_candidates(self) -> list[BackfillCandidate]:
        cache_index = self._build_cache_events_index()
        egie_ids = self._egie_fixture_ids_with_events()
        ph = ",".join("?" * len(FINISHED_STATUSES))
        rows = self.repo._conn.execute(
            f"""
            SELECT f.fixture_id, f.competition_key, f.season, f.home_team, f.away_team,
                   r.home_goals, r.away_goals
            FROM fixtures f
            JOIN fixture_results r ON r.fixture_id = f.fixture_id
            LEFT JOIN (
                SELECT fixture_id, COUNT(*) AS n FROM fixture_goal_events GROUP BY fixture_id
            ) g ON g.fixture_id = f.fixture_id
            WHERE f.status IN ({ph})
              AND COALESCE(r.home_goals, 0) + COALESCE(r.away_goals, 0) > 0
              AND COALESCE(g.n, 0) = 0
            ORDER BY f.kickoff_utc DESC
            """,
            FINISHED_STATUSES,
        ).fetchall()

        enrichment_ids = self._fixtures_with_enrichment_events()
        out: list[BackfillCandidate] = []
        for row in rows:
            fid = int(row["fixture_id"])
            comp = str(row["competition_key"] or "")
            out.append(
                BackfillCandidate(
                    fixture_id=fid,
                    competition_key=comp,
                    season=int(row["season"]) if row["season"] is not None else None,
                    home_team=str(row["home_team"] or ""),
                    away_team=str(row["away_team"] or ""),
                    home_goals=int(row["home_goals"] or 0),
                    away_goals=int(row["away_goals"] or 0),
                    priority_rank=self._priority_rank(comp),
                    has_sqlite_events=False,
                    has_egie_events=fid in egie_ids,
                    has_cache_events=fid in cache_index,
                    has_enrichment_events=fid in enrichment_ids,
                )
            )
        out.sort(key=lambda c: (c.priority_rank, -c.fixture_id))
        self.candidates = out
        return out

    def _fixtures_with_enrichment_events(self) -> set[int]:
        ids: set[int] = set()
        try:
            rows = self.repo._conn.execute(
                """
                SELECT fixture_id, events_json FROM fixture_enrichment
                WHERE events_json IS NOT NULL AND events_json != '' AND events_json != '[]'
                """
            ).fetchall()
            for row in rows:
                ids.add(int(row[0]))
        except sqlite3.Error:
            pass
        try:
            rows = self.repo._conn.execute(
                """
                SELECT fixture_id_api_football, raw_json FROM sportmonks_fixture_enrichment
                WHERE raw_json IS NOT NULL AND raw_json != ''
                """
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row[1] or "{}")
                    data = payload.get("data") if isinstance(payload, dict) else payload
                    if isinstance(data, dict) and data.get("events"):
                        ids.add(int(row[0]))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        except sqlite3.Error:
            pass
        return ids

    def _egie_fixture_ids_with_events(self) -> set[int]:
        if self._egie_fixture_ids is not None:
            return self._egie_fixture_ids
        self._egie_fixture_ids = set()
        return self._egie_fixture_ids

    def _build_cache_events_index(self) -> dict[int, list[dict[str, Any]]]:
        if self._cache_events_index is not None:
            return self._cache_events_index
        out: dict[int, list[dict[str, Any]]] = {}
        try:
            rows = self.repo._conn.execute(
                """
                SELECT params_json, payload_json FROM api_response_cache
                WHERE endpoint LIKE '%event%' OR endpoint LIKE '%fixtures/events%'
                """
            ).fetchall()
        except sqlite3.Error:
            self._cache_events_index = out
            return out
        for row in rows:
            try:
                params = json.loads(row[0] or "{}")
                payload = json.loads(row[1] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            fid = params.get("fixture") or params.get("fixture_id") or params.get("id")
            if fid is None:
                resp = payload.get("response") if isinstance(payload, dict) else payload
                if isinstance(resp, list) and resp and isinstance(resp[0], dict):
                    fid = (resp[0].get("fixture") or {}).get("id")
            if fid is None:
                continue
            events = self._parse_api_football_payload(payload)
            if events:
                out[int(fid)] = events
        self._cache_events_index = out
        return out

    def _parse_api_football_payload(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and "response" in payload:
            resp = payload["response"]
        elif isinstance(payload, list):
            resp = payload
        else:
            return []
        items = resp if isinstance(resp, list) else [resp]
        for block in items:
            if isinstance(block, dict) and block.get("events"):
                evs = block["events"]
                return evs if isinstance(evs, list) else []
        return []

    def _load_enrichment_events(self, fixture_id: int) -> tuple[list[Any], str]:
        row = self.repo._conn.execute(
            "SELECT events_json FROM fixture_enrichment WHERE fixture_id = ? LIMIT 1",
            (fixture_id,),
        ).fetchone()
        if row and row[0]:
            try:
                data = json.loads(row[0])
                if isinstance(data, list) and data:
                    return data, "fixture_enrichment"
            except json.JSONDecodeError:
                pass
        row = self.repo._conn.execute(
            "SELECT raw_json FROM sportmonks_fixture_enrichment WHERE fixture_id_api_football = ? LIMIT 1",
            (fixture_id,),
        ).fetchone()
        if row and row[0]:
            try:
                payload = json.loads(row[0])
                data = payload.get("data") if isinstance(payload, dict) else payload
                if isinstance(data, dict):
                    events = data.get("events")
                    if isinstance(events, list) and events:
                        return events, "sportmonks_enrichment"
                    raw = _fixture_data(data)
                    if raw:
                        return raw, "sportmonks_uefa_payload"
            except json.JSONDecodeError:
                pass
        return [], ""

    def _sportmonks_to_goal_events(
        self,
        payload: Any,
        *,
        home_team: str,
        away_team: str,
    ) -> list[GoalEvent]:
        raw = _fixture_data(payload) if not isinstance(payload, list) else {"events": payload}
        if not raw:
            return []
        parsed: list[GoalEvent] = []
        for idx, g in enumerate(parse_uefa_goal_events(raw)):
            side = g.get("scoring_side")
            team_name = home_team if side == "home" else away_team if side == "away" else home_team
            kind = g.get("goal_kind") or "goal"
            detail = "Own Goal" if kind == "own_goal" else "Penalty" if kind == "penalty" else "Goal"
            parsed.append(
                GoalEvent(
                    sort_index=idx,
                    minute=int(g["minute"]) if g.get("minute") is not None else None,
                    extra_minute=None,
                    team=team_name,
                    team_id=g.get("team_id"),
                    player=None,
                    assist=None,
                    is_penalty=kind == "penalty",
                    is_own_goal=kind == "own_goal",
                    detail=detail,
                )
            )
        return parsed

    def _persist_events(
        self,
        fixture_id: int,
        events: list[GoalEvent],
        *,
        provider: str,
        source: str,
        raw_payload: Any | None = None,
    ) -> int:
        if not events:
            return 0
        existing = self.repo.count_fixture_goal_events(fixture_id)
        if existing > 0:
            return 0
        self.repo.replace_fixture_goal_events(fixture_id, events)
        first = events[0]
        self.repo.update_fixture_outcome_detail(
            fixture_id,
            first_goal_team=first.team,
            first_goal_player=first.player,
            first_goal_minute=first.minute,
            first_goal_extra_minute=first.extra_minute,
            outcome_source=provider,
            outcome_persisted_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        )
        return len(events)

    def backfill_fixture(self, candidate: BackfillCandidate) -> BackfillResult:
        fid = candidate.fixture_id
        if self.repo.count_fixture_goal_events(fid) > 0:
            return BackfillResult(fid, candidate.competition_key, "none", 0, "already_present", skipped_reason="already_present")

        home, away = candidate.home_team, candidate.away_team
        cache_index = self._build_cache_events_index()
        if fid in cache_index:
            raw = cache_index[fid]
            parsed = parse_api_football_goal_events(raw, home_team=home, away_team=away)
            n = self._persist_events(fid, parsed, provider="api_football", source="api_response_cache", raw_payload=raw)
            if n:
                return BackfillResult(fid, candidate.competition_key, "api_football", n, "api_response_cache")

        egie_events: list[GoalEvent] = []
        if candidate.has_egie_events:
            try:
                egie_events = load_goal_events_from_egie(fid, home_team=home, away_team=away) or []
            except Exception:
                logger.debug("EGIE goal events unavailable fixture_id=%s", fid, exc_info=True)
        if egie_events:
            n = self._persist_events(fid, egie_events, provider="api_football", source="egie_postgres")
            if n:
                return BackfillResult(fid, candidate.competition_key, "api_football", n, "egie_postgres")

        enrich_raw, enrich_src = self._load_enrichment_events(fid)
        if enrich_raw:
            if enrich_src == "fixture_enrichment":
                parsed = parse_api_football_goal_events(enrich_raw, home_team=home, away_team=away)
                provider = "api_football"
            else:
                parsed = self._sportmonks_to_goal_events(enrich_raw, home_team=home, away_team=away)
                provider = "sportmonks"
            n = self._persist_events(fid, parsed, provider=provider, source=enrich_src, raw_payload=enrich_raw)
            if n:
                return BackfillResult(fid, candidate.competition_key, provider, n, enrich_src)

        allow_live = candidate.priority_rank < 99
        if not allow_live:
            return BackfillResult(fid, candidate.competition_key, "none", 0, "skipped", skipped_reason="non_priority_no_cache")

        if self.api_calls_used >= self.max_api_calls:
            return BackfillResult(fid, candidate.competition_key, "none", 0, "skipped", skipped_reason="api_budget_exhausted")

        if not self.settings.api_football_configured:
            return BackfillResult(fid, candidate.competition_key, "none", 0, "skipped", skipped_reason="api_not_configured")

        client = ApiFootballClient(self.settings)
        result = client.get_fixture_events(fid)
        if result.source == "live":
            self.api_calls_used += 1
        raw = result.data if isinstance(result.data, list) else []
        parsed = parse_api_football_goal_events(raw, home_team=home, away_team=away)
        n = self._persist_events(fid, parsed, provider="api_football", source=result.source, raw_payload=raw)
        return BackfillResult(
            fid,
            candidate.competition_key,
            "api_football",
            n,
            result.source,
            api_call=result.source == "live",
            skipped_reason=None if n else "no_events_in_response",
        )

    def run(self) -> dict[str, Any]:
        candidates = self.find_candidates()
        cache_first = [c for c in candidates if c.has_cache_events or c.has_enrichment_events]
        priority_live = [c for c in candidates if c.priority_rank < 99 and c not in cache_first]
        attempt_list = (cache_first + priority_live)[: self.max_backfill_attempts]

        before_summary = self._load_before_summary()
        with ingest_mode():
            for candidate in attempt_list:
                if self.repo.count_fixture_goal_events(candidate.fixture_id) > 0:
                    continue
                if self.api_calls_used >= self.max_api_calls and not (
                    candidate.has_cache_events or candidate.has_enrichment_events
                ):
                    continue
                res = self.backfill_fixture(candidate)
                self.results.append(res)

        after_research = FirstGoalTimingResearch(db_path=self.settings.sqlite_path).run()
        comparison = self._compare_summaries(before_summary, after_research["summary"])
        return {
            "candidates": candidates,
            "results": self.results,
            "api_calls_used": self.api_calls_used,
            "before_summary": before_summary,
            "after_summary": after_research["summary"],
            "comparison": comparison,
            "after_research": after_research,
        }

    def _load_before_summary(self) -> dict[str, Any]:
        if PHASE60B_SUMMARY.is_file():
            return json.loads(PHASE60B_SUMMARY.read_text(encoding="utf-8"))
        research = FirstGoalTimingResearch(db_path=self.settings.sqlite_path)
        return research.run()["summary"]

    def _compare_summaries(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        b = before.get("overall") or {}
        a = after.get("overall") or {}
        return {
            "reliable_fixtures_before": b.get("total_reliable_fixtures"),
            "reliable_fixtures_after": a.get("total_reliable_fixtures"),
            "reliable_delta": (a.get("total_reliable_fixtures") or 0) - (b.get("total_reliable_fixtures") or 0),
            "excluded_before": b.get("data_missing_fixtures"),
            "excluded_after": a.get("data_missing_fixtures"),
            "excluded_delta": (a.get("data_missing_fixtures") or 0) - (b.get("data_missing_fixtures") or 0),
            "with_goal_before": b.get("with_at_least_one_goal"),
            "with_goal_after": a.get("with_at_least_one_goal"),
            "pct_1_30_with_goal_before": (before.get("main_answer") or {}).get("among_fixtures_with_at_least_one_goal", {}).get("first_goal_1_30_pct"),
            "pct_1_30_with_goal_after": (after.get("main_answer") or {}).get("among_fixtures_with_at_least_one_goal", {}).get("first_goal_1_30_pct"),
            "pct_31_plus_with_goal_before": (before.get("main_answer") or {}).get("among_fixtures_with_at_least_one_goal", {}).get("first_goal_31_plus_pct"),
            "pct_31_plus_with_goal_after": (after.get("main_answer") or {}).get("among_fixtures_with_at_least_one_goal", {}).get("first_goal_31_plus_pct"),
            "pct_no_goal_before": b.get("pct_B_no_goal"),
            "pct_no_goal_after": a.get("pct_B_no_goal"),
            "bucket_counts_before": b.get("bucket_counts"),
            "bucket_counts_after": a.get("bucket_counts"),
        }


def write_backfill_artifacts(run_output: dict[str, Any]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    candidates: list[BackfillCandidate] = run_output["candidates"]
    results: list[BackfillResult] = run_output["results"]

    with (ARTIFACT_DIR / "backfill_candidates.csv").open("w", newline="", encoding="utf-8") as fh:
        if candidates:
            writer = csv.DictWriter(fh, fieldnames=list(candidates[0].to_csv_dict().keys()))
            writer.writeheader()
            for c in candidates:
                writer.writerow(c.to_csv_dict())

    backfill_result = {
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "candidate_count": len(candidates),
        "attempted": len(results),
        "events_added_total": sum(r.events_added for r in results),
        "fixtures_backfilled": sum(1 for r in results if r.events_added > 0),
        "api_calls_used": run_output["api_calls_used"],
        "results": [r.to_dict() for r in results],
        "comparison": run_output["comparison"],
    }
    (ARTIFACT_DIR / "backfill_result.json").write_text(json.dumps(backfill_result, indent=2), encoding="utf-8")

    after = run_output["after_summary"]
    (ARTIFACT_DIR / "first_goal_distribution_after_backfill.json").write_text(
        json.dumps(after, indent=2), encoding="utf-8"
    )
    quality = {
        "api_calls_used": run_output["api_calls_used"],
        "candidate_count": len(candidates),
        "fixtures_backfilled": backfill_result["fixtures_backfilled"],
        "comparison": run_output["comparison"],
        "warnings": [
            "Bundesliga bulk fixtures may still lack events if not cached",
            "Live API used only for priority competitions within budget",
        ],
    }
    (ARTIFACT_DIR / "data_quality_report.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    return ARTIFACT_DIR
