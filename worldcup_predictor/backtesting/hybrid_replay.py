"""Phase 31D — production-like hybrid replay from SQLite + cache + MatchIntelligenceBuilder."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import replace
from statistics import mean
from typing import Any
from unittest.mock import patch

from worldcup_predictor.agents.base import AgentContext
from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.api.prediction_output import build_detailed_markets, build_prediction_output
from worldcup_predictor.accuracy.evaluator import actual_1x2, actual_over_under
from worldcup_predictor.backtesting.historical_loader import HistoricalMatchRow, build_form_history
from worldcup_predictor.backtesting.sqlite_historical_replay import (
    CONFIDENCE_BUCKETS,
    CONFIDENCE_THRESHOLDS,
    ActualOutcomes,
    FixtureReplayCore,
    PickEvaluation,
    _actual_btts,
    _apply_enrichment,
    _data_quality_pct,
    _extract_odds_from_snapshot,
    _offline_settings,
    _pick_rows_from_output,
    _specialist_summary_from_report,
    build_ranking_at_threshold,
    is_no_bet_at_threshold,
    load_finished_match_rows,
)
from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_quality.transparency import explain_data_quality
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import DataQualityReport, MatchIntelligenceReport
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.prediction.extended_markets import attach_extended_markets_to_prediction
from worldcup_predictor.prediction.scoring_engine import ScoringEngine
from worldcup_predictor.quota.local_first import load_fixture_api_item_from_db
from worldcup_predictor.quota.quota_tracker import get_quota_tracker

logger = logging.getLogger(__name__)


class HybridReplayStats:
    """Tracks external call attempts during hybrid replay."""

    def __init__(self) -> None:
        self.live_fetch_attempts = 0
        self.http_calls = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "live_fetch_attempts": self.live_fetch_attempts,
            "http_calls": self.http_calls,
            "api_football_live": self.live_fetch_attempts,
            "sportmonks_live": 0,
            "openai_live": 0,
            "total_external_calls": self.live_fetch_attempts + self.http_calls,
        }


class CacheOnlyApiFootballClient(ApiFootballClient):
    """API-Football client that only reads SQLite/disk cache — never hits the network."""

    def __init__(self, settings: Settings, *, stats: HybridReplayStats | None = None) -> None:
        super().__init__(settings)
        self._stats = stats or HybridReplayStats()

    def _fetch_raw(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        self._stats.live_fetch_attempts += 1
        raise RuntimeError(f"Hybrid replay blocked live API call: {endpoint}")

    def _safe_get(  # type: ignore[override]
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        placeholder_factory,
        force_refresh: bool = False,
        ttl_seconds: int | None = None,
    ) -> ApiCallResult:
        tracker = get_quota_tracker()
        cache_key = ApiCache.build_key(endpoint, params)

        local_payload = self._local_first_payload(endpoint, params)
        if local_payload is not None and not force_refresh:
            tracker.record_local_hit()
            return ApiCallResult(
                data=local_payload,
                source="local",
                endpoint=endpoint,
                from_cache=True,
            )

        if not force_refresh:
            sqlite_cached = self._sqlite_cache_get(cache_key)
            if sqlite_cached is not None:
                tracker.record_cache_hit()
                return ApiCallResult(
                    data=sqlite_cached,
                    source="cache",
                    endpoint=endpoint,
                    from_cache=True,
                )

            cached = self._cache.get(endpoint, params)
            if cached is not None:
                tracker.record_cache_hit()
                return ApiCallResult(
                    data=cached,
                    source="cache",
                    endpoint=endpoint,
                    from_cache=True,
                )

        return ApiCallResult(
            data=placeholder_factory(),
            source="placeholder",
            endpoint=endpoint,
            error="cache_miss_offline",
        )


def _hybrid_settings(base: Settings | None = None) -> Settings:
    """Configured-looking settings so MatchIntelligenceBuilder uses cache paths; keys are inert."""
    offline = _offline_settings(base)
    return offline.model_copy(
        update={
            "api_football_key": "offline-hybrid-replay",
            "weather_api_key": "",
            "openweather_api_key": "",
        }
    )


@contextmanager
def _hybrid_offline_guard(settings: Settings, stats: HybridReplayStats):
    """Force offline settings inside production builder paths; block outbound HTTP."""

    def _noop_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    import httpx

    def _guarded_request(client_self, method: str, url: str, **kwargs: Any) -> Any:  # noqa: ANN401
        stats.http_calls += 1
        raise RuntimeError(f"Hybrid replay blocked HTTP {method} {url}")

    patches = [
        patch("worldcup_predictor.config.settings.get_settings", return_value=settings),
        patch(
            "worldcup_predictor.odds.snapshot_service.OddsSnapshotService.persist_from_report",
            _noop_persist,
        ),
        patch.object(httpx.Client, "request", _guarded_request),
    ]
    with patches[0], patches[1], patches[2]:
        yield


def _team_ids_from_lineups(lineups: list[Any], home_name: str, away_name: str) -> tuple[int | None, int | None]:
    home_id: int | None = None
    away_id: int | None = None
    home_l = home_name.lower()
    away_l = away_name.lower()
    for item in lineups:
        if not isinstance(item, dict):
            continue
        team = item.get("team") or {}
        name = str(team.get("name") or "").lower()
        tid = team.get("id")
        try:
            tid_int = int(tid) if tid is not None else None
        except (TypeError, ValueError):
            tid_int = None
        if tid_int is None:
            continue
        if home_l and home_l in name:
            home_id = tid_int
        elif away_l and away_l in name:
            away_id = tid_int
    if home_id is None and len(lineups) >= 1:
        team = (lineups[0].get("team") or {}) if isinstance(lineups[0], dict) else {}
        try:
            home_id = int(team.get("id")) if team.get("id") is not None else None
        except (TypeError, ValueError):
            pass
    if away_id is None and len(lineups) >= 2:
        team = (lineups[1].get("team") or {}) if isinstance(lineups[1], dict) else {}
        try:
            away_id = int(team.get("id")) if team.get("id") is not None else None
        except (TypeError, ValueError):
            pass
    return home_id, away_id


def _hydrate_fixture_api_item(
    repo: FootballIntelligenceRepository,
    fixture_id: int,
) -> dict[str, Any] | None:
    items = load_fixture_api_item_from_db(repo, fixture_id)
    if not items:
        return None
    item = dict(items[0])
    row = repo.get_fixture_row(fixture_id) or {}
    enrich = repo.get_fixture_enrichment_row(fixture_id) or {}

    league = dict(item.get("league") or {})
    if enrich.get("league_id"):
        league["id"] = enrich["league_id"]
    elif row.get("league_id"):
        league["id"] = row["league_id"]
    if enrich.get("season"):
        league["season"] = enrich["season"]
    elif row.get("season"):
        league["season"] = row["season"]
    item["league"] = league

    teams = dict(item.get("teams") or {})
    home_name = str((teams.get("home") or {}).get("name") or row.get("home_team") or "")
    away_name = str((teams.get("away") or {}).get("name") or row.get("away_team") or "")

    lineups_raw = enrich.get("lineups_json")
    if lineups_raw:
        try:
            lineups = json.loads(lineups_raw)
            if isinstance(lineups, list):
                hid, aid = _team_ids_from_lineups(lineups, home_name, away_name)
                if hid:
                    teams.setdefault("home", {})["id"] = hid
                if aid:
                    teams.setdefault("away", {})["id"] = aid
        except (json.JSONDecodeError, TypeError):
            pass

    item["teams"] = teams
    return item


def _load_cached_odds_payload(repo: FootballIntelligenceRepository, fixture_id: int) -> Any | None:
    for endpoint in ("odds", "odds/live"):
        key = ApiCache.build_key(endpoint, {"fixture": fixture_id})
        payload = repo.get_api_cache_payload(key)
        if payload:
            return payload

    enrich = repo.get_fixture_enrichment_row(fixture_id)
    if enrich and enrich.get("odds_json"):
        try:
            return json.loads(enrich["odds_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    snaps = repo.fetch_odds_snapshots(fixture_id, limit=1)
    if snaps:
        try:
            return json.loads(snaps[0]["payload_json"])
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    return None


def _apply_cached_odds(report: MatchIntelligenceReport, repo: FootballIntelligenceRepository) -> None:
    payload = _load_cached_odds_payload(repo, report.fixture_id)
    if not payload:
        return
    bookmakers = payload if isinstance(payload, list) else payload.get("bookmakers") or payload.get("response") or []
    if isinstance(bookmakers, dict):
        bookmakers = bookmakers.get("bookmakers") or []
    if not bookmakers:
        return
    from worldcup_predictor.domain.intelligence import OddsSnapshot

    report.odds = OddsSnapshot(
        fixture_id=report.fixture_id,
        available=True,
        bookmakers=bookmakers if isinstance(bookmakers, list) else [bookmakers],
        source="cache",
    )
    report.missing_data = [m for m in report.missing_data if m != "odds"]


def _inject_form(
    report: MatchIntelligenceReport,
    home_form: list[str],
    away_form: list[str],
) -> MatchIntelligenceReport:
    home_intel = replace(report.home_team, form=home_form or report.home_team.form)
    away_intel = replace(report.away_team, form=away_form or report.away_team.form)
    missing = list(report.missing_data)
    if home_form and "home_form" in missing:
        missing.remove("home_form")
    if away_form and "away_form" in missing:
        missing.remove("away_form")
    return replace(report, home_team=home_intel, away_team=away_intel, missing_data=missing)


def _recompute_data_quality(report: MatchIntelligenceReport) -> MatchIntelligenceReport:
    detail = explain_data_quality(report)
    dq = DataQualityReport(
        score=detail.score_ratio,
        available_fields=sorted(set(report.data_quality.available_fields if report.data_quality else [])),
        missing_fields=sorted(set(report.missing_data)),
        errors=list(report.data_quality.errors if report.data_quality else []),
        breakdown=detail.components,
        breakdown_total=detail.display_total,
        breakdown_max=detail.max_total,
        component_max=detail.component_max,
        pre_match_data_quality=detail.pre_match_total,
        live_data_quality=detail.live_total,
        post_match_data_quality=detail.post_match_total,
        match_phase=detail.match_phase,
        reason_text=detail.reason_text,
        kickoff_note=detail.kickoff_note,
    )
    return replace(report, data_quality=dq)


def build_hybrid_intelligence_report(
    fixture_id: int,
    *,
    repo: FootballIntelligenceRepository,
    api_client: CacheOnlyApiFootballClient,
    settings: Settings,
    home_form: list[str] | None = None,
    away_form: list[str] | None = None,
    competition_key: str = "world_cup_2026",
    stats: HybridReplayStats | None = None,
) -> MatchIntelligenceReport:
    item = _hydrate_fixture_api_item(repo, fixture_id)
    if item is None:
        raise ValueError(f"fixture {fixture_id} not found in SQLite")

    fixture: Fixture = api_client.parse_fixture_item(item, competition_key=competition_key)
    builder = MatchIntelligenceBuilder(api_client)
    replay_stats = stats or api_client._stats
    with _hybrid_offline_guard(settings, replay_stats):
        report = builder.build(fixture, force_odds_api=False)

    _apply_enrichment(report, repo)
    _apply_cached_odds(report, repo)
    report = _inject_form(report, home_form or [], away_form or [])
    report = _recompute_data_quality(report)
    return report


def select_hybrid_replay_sample(
    repo: FootballIntelligenceRepository,
    rows: list[HistoricalMatchRow],
    *,
    sample_size: int = 100,
) -> list[HistoricalMatchRow]:
    """Prioritize fixtures with api_response_cache + enrichment for richer hybrid replay."""
    cache_fixture_ids: set[int] = set()
    cache_endpoints: dict[int, set[str]] = {}
    for row in repo._conn.execute(
        "SELECT endpoint, params_json FROM api_response_cache"
    ).fetchall():
        try:
            params = json.loads(row["params_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        fid = params.get("fixture") or params.get("fixture_id")
        if fid is None:
            continue
        try:
            fixture_id = int(fid)
        except (TypeError, ValueError):
            continue
        cache_fixture_ids.add(fixture_id)
        cache_endpoints.setdefault(fixture_id, set()).add(str(row["endpoint"]))

    def score(row: HistoricalMatchRow) -> tuple[int, float]:
        pts = 0
        if row.fixture_id in cache_fixture_ids:
            pts += 10
            eps = cache_endpoints.get(row.fixture_id, set())
            if any("odds" in e for e in eps):
                pts += 15
            if any("injur" in e for e in eps):
                pts += 5
            if any("head" in e or "h2h" in e for e in eps):
                pts += 5
            if any("standings" in e for e in eps):
                pts += 3
        enrich = repo.get_fixture_enrichment_row(row.fixture_id)
        if enrich:
            if enrich.get("lineups_json"):
                pts += 4
            if enrich.get("statistics_json"):
                pts += 2
            if enrich.get("odds_json"):
                pts += 8
        if row.odds_home:
            pts += 6
        return pts, row.date.timestamp()

    ranked = sorted(rows, key=lambda r: (-score(r)[0], score(r)[1]))
    return ranked[:sample_size]


def replay_hybrid_fixture_core(
    row: HistoricalMatchRow,
    form_history: dict[int, tuple[list[str], list[str]]],
    *,
    repo: FootballIntelligenceRepository,
    api_client: CacheOnlyApiFootballClient,
    settings: Settings | None = None,
    run_specialists: bool = True,
) -> FixtureReplayCore:
    settings = _hybrid_settings()
    stats = HybridReplayStats()
    api_client = CacheOnlyApiFootballClient(settings, stats=stats)
    home_form, away_form = form_history.get(row.fixture_id, ([], []))

    with _hybrid_offline_guard(settings, api_client._stats):
        report = build_hybrid_intelligence_report(
            row.fixture_id,
            repo=repo,
            api_client=api_client,
            settings=settings,
            home_form=home_form,
            away_form=away_form,
            competition_key=row.competition,
            stats=api_client._stats,
        )

        context = AgentContext(
            settings=settings,
            competition_key=report.fixture.competition_key if report.fixture else row.competition,
            locale="en",
        )
        context.shared["intelligence_reports"] = {row.fixture_id: report}
        context.shared["phase31d_hybrid_replay"] = True

        specialist_report: MatchSpecialistReport | None = None
        if run_specialists:
            orchestrator = SpecialistOrchestrator(context)
            specialist_result = orchestrator.run(fixture_id=row.fixture_id)
            if specialist_result.success and isinstance(specialist_result.data, MatchSpecialistReport):
                specialist_report = specialist_result.data
                report.specialist_report = specialist_report

        engine = ScoringEngine()
        prediction = engine.predict(
            report,
            specialist_report=specialist_report,
            use_weighted_decision=True,
        )
        attach_extended_markets_to_prediction(prediction, report)
        detailed = build_detailed_markets(prediction)
        specialist_summary = _specialist_summary_from_report(specialist_report)

    wde_reasons: list[str] = []
    if prediction.audit_report and prediction.audit_report.trace:
        wde_reasons = list(prediction.audit_report.trace.no_bet_reasons or [])

    actual = ActualOutcomes(
        home_goals=row.home_goals,
        away_goals=row.away_goals,
        actual_1x2=actual_1x2(row.home_goals, row.away_goals),
        actual_ou=actual_over_under(row.home_goals, row.away_goals),
        actual_btts=_actual_btts(row.home_goals, row.away_goals),
    )

    dq_pct = _data_quality_pct(prediction)
    if report.data_quality and report.data_quality.score is not None:
        raw = float(report.data_quality.score)
        dq_pct = raw * 100 if raw <= 1.0 else raw

    return FixtureReplayCore(
        fixture_id=row.fixture_id,
        match_name=f"{row.home_team} vs {row.away_team}",
        competition_key=report.fixture.competition_key if report.fixture else row.competition,
        kickoff=row.date.isoformat(),
        confidence=float(prediction.confidence_score or 0.0),
        data_quality=dq_pct,
        wde_no_bet=bool(prediction.no_bet_flag),
        wde_no_bet_reasons=wde_reasons,
        is_placeholder=bool(prediction.is_placeholder),
        confidence_level=str(
            prediction.confidence_level.value
            if hasattr(prediction.confidence_level, "value")
            else prediction.confidence_level
        ),
        prediction=prediction,
        detailed_markets=detailed,
        specialist_summary=specialist_summary,
        actual=actual,
    )


def _summarize_cores(cores: list[FixtureReplayCore], picks: list[PickEvaluation]) -> dict[str, Any]:
    threshold_summary: dict[str, Any] = {}
    for threshold in CONFIDENCE_THRESHOLDS:
        nb = sum(1 for c in cores if is_no_bet_at_threshold(c, float(threshold)))
        total = len(cores) or 1
        th_picks = [p for p in picks if p.threshold == threshold]
        threshold_summary[str(threshold)] = {
            "total_matches": len(cores),
            "no_bet_count": nb,
            "no_bet_rate": round(nb / total, 4),
            "recommendation_rate": round(1 - nb / total, 4),
            "average_confidence": round(mean([c.confidence for c in cores]), 2) if cores else 0.0,
            "max_confidence": round(max((c.confidence for c in cores), default=0.0), 2),
        }

    conf_bucket_stats: dict[str, Any] = {}
    for label, lo, hi in CONFIDENCE_BUCKETS:
        bucket_cores = [c for c in cores if lo <= c.confidence < hi]
        conf_bucket_stats[label] = {"count": len(bucket_cores)}

    return {
        "threshold_matrix": threshold_summary,
        "confidence_bucket_analysis": conf_bucket_stats,
        "average_confidence": round(mean([c.confidence for c in cores]), 2) if cores else 0.0,
        "max_confidence": round(max((c.confidence for c in cores), default=0.0), 2),
        "average_data_quality": round(mean([c.data_quality for c in cores]), 2) if cores else 0.0,
    }


def _missing_enrichment_audit(
    repo: FootballIntelligenceRepository,
    cores: list[FixtureReplayCore],
) -> dict[str, Any]:
    missing_counts: dict[str, int] = {}
    for core in cores:
        report = None
        # fixture-level missing from prediction metadata if available
        meta = core.prediction.metadata or {}
        for field in meta.get("missing_data") or []:
            missing_counts[str(field)] = missing_counts.get(str(field), 0) + 1
        row = repo.get_fixture_enrichment_row(core.fixture_id)
        if not row or not row.get("odds_json"):
            missing_counts["odds_json_enrichment"] = missing_counts.get("odds_json_enrichment", 0) + 1
        payload = _load_cached_odds_payload(repo, core.fixture_id)
        if not payload:
            missing_counts["cached_odds"] = missing_counts.get("cached_odds", 0) + 1
        item = _hydrate_fixture_api_item(repo, core.fixture_id)
        if item:
            teams = item.get("teams") or {}
            if not (teams.get("home") or {}).get("id"):
                missing_counts["home_team_id"] = missing_counts.get("home_team_id", 0) + 1
            if not (teams.get("away") or {}).get("id"):
                missing_counts["away_team_id"] = missing_counts.get("away_team_id", 0) + 1

    total = len(cores) or 1
    ranked = sorted(missing_counts.items(), key=lambda kv: -kv[1])
    return {
        "top_missing": [
            {"field": k, "count": v, "pct": round(v / total, 4)} for k, v in ranked[:10]
        ],
        "total_fixtures": total,
    }


def run_hybrid_replay(
    *,
    db_path: str | None = None,
    sample_size: int = 100,
    run_specialists: bool = True,
    fixture_ids: list[int] | None = None,
) -> dict[str, Any]:
    repo = FootballIntelligenceRepository(path=db_path)
    all_rows = load_finished_match_rows(repo)
    if fixture_ids:
        id_set = set(fixture_ids)
        sample_rows = [r for r in all_rows if r.fixture_id in id_set]
    else:
        sample_rows = select_hybrid_replay_sample(repo, all_rows, sample_size=sample_size)

    form_history = build_form_history(all_rows)
    settings = _hybrid_settings()
    stats = HybridReplayStats()
    api_client = CacheOnlyApiFootballClient(settings, stats=stats)

    cores: list[FixtureReplayCore] = []
    all_picks: list[PickEvaluation] = []
    errors = 0

    for idx, row in enumerate(sample_rows):
        try:
            core = replay_hybrid_fixture_core(
                row,
                form_history,
                repo=repo,
                api_client=api_client,
                settings=settings,
                run_specialists=run_specialists,
            )
            cores.append(core)
            for threshold in CONFIDENCE_THRESHOLDS:
                output = build_ranking_at_threshold(core, float(threshold))
                all_picks.extend(_pick_rows_from_output(core, threshold, output))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.exception("Hybrid replay failed fixture %s: %s", row.fixture_id, exc)
        if (idx + 1) % 25 == 0:
            logger.info("Hybrid replay progress %s/%s", idx + 1, len(sample_rows))

    summary = _summarize_cores(cores, all_picks)
    missing_audit = _missing_enrichment_audit(repo, cores)
    repo.close()

    tracker = get_quota_tracker()
    live_calls = getattr(tracker, "live_calls", None) or getattr(tracker, "_live_calls", 0)

    return {
        "meta": {
            "phase": "31D",
            "sample_size": len(sample_rows),
            "replayed_ok": len(cores),
            "errors": errors,
            "run_specialists": run_specialists,
            "fixture_ids": [r.fixture_id for r in sample_rows],
            "external_api_calls": stats.live_fetch_attempts + stats.http_calls,
            "api_football_blocked": stats.live_fetch_attempts,
            "http_blocked": stats.http_calls,
            "quota_tracker_live": live_calls,
            "validation": stats.to_dict(),
        },
        "summary": summary,
        "missing_enrichment": missing_audit,
        "cores": cores,
        "picks": all_picks,
    }


def compare_with_phase31b(
    hybrid_result: dict[str, Any],
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Run Phase 31B path on the same fixture ids for apples-to-apples comparison."""
    from worldcup_predictor.backtesting.sqlite_historical_replay import replay_fixture_core

    fixture_ids = set(hybrid_result["meta"]["fixture_ids"])
    repo = FootballIntelligenceRepository(path=db_path)
    all_rows = load_finished_match_rows(repo)
    sample_rows = [r for r in all_rows if r.fixture_id in fixture_ids]
    form_history = build_form_history(all_rows)
    settings = _offline_settings()

    cores: list[FixtureReplayCore] = []
    for row in sample_rows:
        try:
            cores.append(replay_fixture_core(row, form_history, settings=settings, run_specialists=True))
        except Exception:
            logger.exception("31B comparison failed fixture %s", row.fixture_id)

    repo.close()
    picks: list[PickEvaluation] = []
    for core in cores:
        for threshold in CONFIDENCE_THRESHOLDS:
            output = build_ranking_at_threshold(core, float(threshold))
            picks.extend(_pick_rows_from_output(core, threshold, output))

    baseline = _summarize_cores(cores, picks)
    hybrid_summary = hybrid_result["summary"]

    def delta(key: str) -> float:
        return round(hybrid_summary.get(key, 0) - baseline.get(key, 0), 2)

    t60_h = hybrid_summary["threshold_matrix"].get("60", {})
    t60_b = baseline["threshold_matrix"].get("60", {})

    return {
        "baseline_31b": baseline,
        "hybrid_31d": hybrid_summary,
        "delta": {
            "average_confidence": delta("average_confidence"),
            "max_confidence": delta("max_confidence"),
            "average_data_quality": delta("average_data_quality"),
            "no_bet_rate_60": round(
                t60_h.get("no_bet_rate", 0) - t60_b.get("no_bet_rate", 0), 4
            ),
            "recommendation_rate_60": round(
                t60_h.get("recommendation_rate", 0) - t60_b.get("recommendation_rate", 0), 4
            ),
        },
        "baseline_cores_count": len(cores),
    }
