"""HOTFIX WC-RESULT-SYNC-2 — ECSE snapshot result candidate scan + provider sync."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.outcomes.outcome_persistence import normalize_match_outcome_type
from worldcup_predictor.results.match_results_store import MatchResultsStore, save_finished_fixtures
from worldcup_predictor.research.ecse_live.evaluator import run_ecse_evaluations
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, classify_status

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS

PHASE = "WC-RESULT-SYNC-2"

SUPPORTED_ECSE_COMPETITIONS: tuple[str, ...] = ("world_cup_2026",) + UEFA_CUP_KEYS

UNFINISHED_LOCAL_STATUSES = frozenset(
    {"NS", "TBD", "SCHEDULED", "TIMED", "NOT_STARTED", "NOT STARTED"}
)

PROVIDER_FINISHED_SHORT = frozenset({"FT", "AET", "PEN", "FT_PEN", "FTP"})
PROVIDER_FINISHED_LONG = frozenset(
    {
        "FINISHED",
        "COMPLETED",
        "AFTER_EXTRA_TIME",
        "AFTER_PENALTIES",
        "FULL TIME",
        "FULL-TIME",
    }
)

DEFAULT_SAFETY_HOURS = 2.0
SYNC_LOG_PATH = Path("artifacts/ecse_snapshot_result_sync_log.jsonl")
SUMMARY_PATH = Path("artifacts/ecse_wc_evaluation_summary_latest.json")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def provider_status_is_finished(status: str | None) -> bool:
    code = str(status or "").upper().strip()
    if code in PROVIDER_FINISHED_SHORT:
        return True
    if code in PROVIDER_FINISHED_LONG:
        return True
    return classify_status(code) == "finished"


def final_score_type_from_status(status: str | None) -> str:
    return normalize_match_outcome_type(status)


def _penalty_score_from_item(item: dict[str, Any]) -> str | None:
    score = item.get("score") or {}
    penalty = score.get("penalty") or {}
    home = penalty.get("home")
    away = penalty.get("away")
    if home is None or away is None:
        return None
    try:
        return f"{int(home)}-{int(away)}"
    except (TypeError, ValueError):
        return None


def _provider_mapping(
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    kickoff_date: str | None,
    settings: Settings,
) -> dict[str, Any]:
    mapping: dict[str, Any] = {"api_football_fixture_id": fixture_id}
    try:
        from worldcup_predictor.providers.sportmonks_fixture_lookup import lookup_world_cup_fixture

        lookup = lookup_world_cup_fixture(
            api_fixture_id=fixture_id,
            home_team=home_team,
            away_team=away_team,
            kickoff_date=kickoff_date,
            settings=settings,
        )
        if lookup.found and lookup.sportmonks_fixture_id:
            mapping["sportmonks_fixture_id"] = int(lookup.sportmonks_fixture_id)
            mapping["sportmonks_from_cache"] = lookup.from_cache
    except Exception:
        pass
    return mapping


@dataclass(frozen=True)
class EcseResultSyncCandidate:
    fixture_id: int
    competition_key: str
    kickoff_time: str
    snapshot_id: int
    existing_local_status: str | None
    has_ecse_evaluation: bool
    evaluation_status: str | None
    provider_mapping: dict[str, Any] = field(default_factory=dict)
    home_team: str | None = None
    away_team: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def scan_ecse_snapshot_result_candidates(
    conn: sqlite3.Connection,
    *,
    competition_key: str = "world_cup_2026",
    past_only: bool = True,
    min_hours_since_kickoff: float | None = DEFAULT_SAFETY_HOURS,
    fixture_ids: list[int] | None = None,
    settings: Settings | None = None,
) -> list[EcseResultSyncCandidate]:
    """Find ECSE snapshots that need provider result sync."""
    settings = settings or get_settings()
    ensure_ecse_live_tables(conn)

    if competition_key not in SUPPORTED_ECSE_COMPETITIONS:
        return []

    now = _utc_now()
    cutoff = now
    if past_only:
        cutoff_iso = cutoff.isoformat()
    else:
        cutoff_iso = (now + timedelta(days=365)).isoformat()

    safety_cutoff = now
    if min_hours_since_kickoff is not None and min_hours_since_kickoff > 0:
        safety_cutoff = now - timedelta(hours=float(min_hours_since_kickoff))

    unfinished_placeholders = ",".join("?" for _ in UNFINISHED_LOCAL_STATUSES)
    params: list[Any] = [
        competition_key,
        cutoff_iso,
        competition_key,
        competition_key,
        *sorted(UNFINISHED_LOCAL_STATUSES),
    ]

    fixture_filter = ""
    if fixture_ids:
        placeholders = ",".join("?" for _ in fixture_ids)
        fixture_filter = f" AND s.fixture_id IN ({placeholders})"
        params.extend(int(x) for x in fixture_ids)

    rows = conn.execute(
        f"""
        SELECT
            s.id AS snapshot_id,
            s.fixture_id,
            COALESCE(s.competition_key, ?) AS competition_key,
            s.kickoff_utc AS kickoff_time,
            s.home_team,
            s.away_team,
            f.status AS existing_local_status,
            CASE WHEN e.id IS NOT NULL THEN 1 ELSE 0 END AS has_ecse_evaluation,
            e.status AS evaluation_status
        FROM ecse_prediction_snapshots s
        LEFT JOIN fixtures f ON f.fixture_id = s.fixture_id
        LEFT JOIN fixture_results r ON r.fixture_id = s.fixture_id
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id = s.id
        WHERE s.kickoff_utc IS NOT NULL
          AND s.kickoff_utc < ?
          AND COALESCE(s.competition_key, ?) = ?
          AND (
                r.fixture_id IS NULL
                OR COALESCE(f.status, 'NS') IN ({unfinished_placeholders})
                OR (r.fixture_id IS NOT NULL AND e.id IS NULL)
              )
          AND (e.id IS NULL OR LOWER(COALESCE(e.status, 'pending')) = 'pending')
          {fixture_filter}
        ORDER BY s.kickoff_utc ASC
        """,
        params,
    ).fetchall()

    candidates: list[EcseResultSyncCandidate] = []
    for row in rows:
        kickoff = _parse_kickoff(row["kickoff_time"])
        if kickoff is None:
            continue
        if past_only and kickoff >= now:
            continue
        if min_hours_since_kickoff is not None and kickoff > safety_cutoff:
            continue

        fid = int(row["fixture_id"])
        mapping = _provider_mapping(
            fixture_id=fid,
            home_team=str(row["home_team"] or ""),
            away_team=str(row["away_team"] or ""),
            kickoff_date=str(row["kickoff_time"])[:10],
            settings=settings,
        )
        candidates.append(
            EcseResultSyncCandidate(
                fixture_id=fid,
                competition_key=str(row["competition_key"] or competition_key),
                kickoff_time=str(row["kickoff_time"]),
                snapshot_id=int(row["snapshot_id"]),
                existing_local_status=row["existing_local_status"],
                has_ecse_evaluation=bool(row["has_ecse_evaluation"]),
                evaluation_status=row["evaluation_status"],
                provider_mapping=mapping,
                home_team=row["home_team"],
                away_team=row["away_team"],
            )
        )
    return candidates


def _has_valid_finished_result(
    repo: FootballIntelligenceRepository,
    fixture_id: int,
) -> bool:
    result_row = repo.get_fixture_result_row(fixture_id)
    fixture_row = repo.get_fixture_row(fixture_id) or {}
    status = str(fixture_row.get("status") or "NS").upper()
    if result_row and classify_status(status) == "finished":
        return True
    return False


@dataclass
class EcseSnapshotSyncOutcome:
    phase: str = PHASE
    scanned: int = 0
    synced: int = 0
    skipped: int = 0
    pending_provider: int = 0
    errors: int = 0
    ecse_evaluated: int = 0
    api_fetches: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "scanned": self.scanned,
            "synced": self.synced,
            "skipped": self.skipped,
            "pending_provider": self.pending_provider,
            "errors": self.errors,
            "ecse_evaluated": self.ecse_evaluated,
            "api_fetches": self.api_fetches,
            "details": self.details[:100],
        }


def sync_ecse_snapshot_results(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    fixture_ids: list[int] | None = None,
    past_only: bool = True,
    min_hours_since_kickoff: float | None = DEFAULT_SAFETY_HOURS,
    dry_run: bool = False,
    force: bool = False,
    run_ecse_backfill: bool = True,
    limit: int | None = None,
) -> EcseSnapshotSyncOutcome:
    """Force-refresh and persist provider results for ECSE snapshot fixtures."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    api = ApiFootballClient(settings)
    conn = connect(get_db_path(settings.sqlite_path))
    outcome = EcseSnapshotSyncOutcome()
    finished_for_jsonl: list[Any] = []

    try:
        ensure_ecse_live_tables(conn)
        candidates = scan_ecse_snapshot_result_candidates(
            conn,
            competition_key=competition_key,
            past_only=past_only,
            min_hours_since_kickoff=min_hours_since_kickoff,
            fixture_ids=fixture_ids,
            settings=settings,
        )
        if limit is not None:
            candidates = candidates[: max(0, int(limit))]

        if not api.is_configured:
            outcome.errors = len(candidates)
            outcome.details.append({"status": "error", "reason": "api_football_not_configured"})
            return outcome

        for candidate in candidates:
            outcome.scanned += 1
            fixture_id = candidate.fixture_id
            detail: dict[str, Any] = candidate.to_dict()

            if not force and _has_valid_finished_result(repo, fixture_id):
                if candidate.has_ecse_evaluation:
                    outcome.skipped += 1
                    detail["status"] = "skipped_already_finished"
                    outcome.details.append(detail)
                    continue
                outcome.skipped += 1
                detail["status"] = "result_exists_awaiting_ecse_eval"
                outcome.details.append(detail)
                continue

            try:
                call = api._safe_get(
                    "fixtures",
                    {"id": fixture_id},
                    placeholder_factory=lambda: None,
                    force_refresh=True,
                )
                outcome.api_fetches += 1
                detail["api_source"] = call.source

                if not call.data:
                    outcome.pending_provider += 1
                    detail["status"] = "no_provider_data"
                    outcome.details.append(detail)
                    continue

                item = call.data[0] if isinstance(call.data, list) else call.data
                if not isinstance(item, dict):
                    outcome.errors += 1
                    detail["status"] = "invalid_payload"
                    outcome.details.append(detail)
                    continue

                fixture_meta = item.get("fixture") or {}
                status_obj = fixture_meta.get("status") or {}
                provider_short = str(status_obj.get("short") or "NS")
                provider_long = str(status_obj.get("long") or "")
                provider_status = provider_short
                if not provider_status_is_finished(provider_short):
                    if provider_status_is_finished(provider_long):
                        provider_status = provider_long
                    else:
                        outcome.pending_provider += 1
                        detail["provider_status"] = provider_short
                        detail["provider_status_long"] = provider_long
                        detail["status"] = "provider_not_finished"
                        outcome.details.append(detail)
                        continue

                fixture = parse_api_fixture_item(item, source=str(call.source or "api-football"))
                if fixture is None:
                    outcome.errors += 1
                    detail["status"] = "parse_failed"
                    outcome.details.append(detail)
                    continue

                if fixture.home_goals is None or fixture.away_goals is None:
                    outcome.pending_provider += 1
                    detail["status"] = "provider_missing_goals"
                    outcome.details.append(detail)
                    continue

                score_type = final_score_type_from_status(fixture.status)
                penalty_score = _penalty_score_from_item(item)
                detail.update(
                    {
                        "provider_status": fixture.status,
                        "final_score_type": score_type,
                        "final_score": f"{fixture.home_goals}-{fixture.away_goals}",
                        "penalty_score": penalty_score,
                    }
                )

                if dry_run:
                    detail["status"] = "dry_run"
                    outcome.details.append(detail)
                    continue

                repo.upsert_fixture(fixture, competition_key=competition_key)
                if repo.upsert_fixture_result(
                    fixture,
                    competition_key=competition_key,
                    match_outcome_type=score_type,
                    penalty_score=penalty_score,
                ):
                    outcome.synced += 1
                    finished_for_jsonl.append(fixture)
                    detail["status"] = "synced"
                else:
                    outcome.errors += 1
                    detail["status"] = "upsert_result_failed"
                outcome.details.append(detail)

            except Exception as exc:
                outcome.errors += 1
                detail["status"] = "error"
                detail["reason"] = str(exc)
                outcome.details.append(detail)

        if finished_for_jsonl and not dry_run:
            save_finished_fixtures(finished_for_jsonl, MatchResultsStore())

        if run_ecse_backfill and not dry_run:
            ecse_result = run_ecse_evaluations(conn, settings=settings, limit=500)
            outcome.ecse_evaluated = ecse_result.evaluated
            outcome.details.append(
                {
                    "status": "ecse_backfill",
                    "evaluated": ecse_result.evaluated,
                    "pending": ecse_result.pending,
                    "scanned": ecse_result.scanned,
                }
            )

        if not dry_run:
            _append_sync_log(outcome.to_dict())
            build_ecse_wc_evaluation_summary(
                conn,
                competition_key=competition_key,
                output_path=SUMMARY_PATH,
            )
    finally:
        repo.close()
        conn.close()

    return outcome


def _append_sync_log(payload: dict[str, Any]) -> None:
    SYNC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"logged_at": _utc_now_iso(), **payload}
    with SYNC_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")


def build_ecse_wc_evaluation_summary(
    conn: sqlite3.Connection,
    *,
    competition_key: str = "world_cup_2026",
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Build owner/internal ECSE WC evaluation summary."""
    ensure_ecse_live_tables(conn)

    total = conn.execute(
        """
        SELECT COUNT(*) AS c FROM ecse_prediction_snapshots
        WHERE COALESCE(competition_key, ?) = ?
        """,
        (competition_key, competition_key),
    ).fetchone()["c"]

    finished_rows = conn.execute(
        """
        SELECT s.fixture_id, s.kickoff_utc, s.home_team, s.away_team, s.top_1_score,
               f.status AS fixture_status,
               r.final_score, r.match_outcome_type, r.penalty_score,
               e.id AS eval_id, e.top1_correct, e.top3_correct, e.top5_correct,
               e.top10_correct, e.rank_of_actual_score, e.status AS eval_status
        FROM ecse_prediction_snapshots s
        LEFT JOIN fixtures f ON f.fixture_id = s.fixture_id
        LEFT JOIN fixture_results r ON r.fixture_id = s.fixture_id
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id = s.id
        WHERE COALESCE(s.competition_key, ?) = ?
        ORDER BY s.kickoff_utc ASC
        """,
        (competition_key, competition_key),
    ).fetchall()

    now = _utc_now()
    finished_count = 0
    evaluated_count = 0
    pending_count = 0
    top1_hits = top3_hits = top5_hits = top10_hits = 0
    rank_sum = 0
    rank_n = 0
    by_outcome_type: dict[str, dict[str, int]] = {}
    knockout_draw_pen = 0
    pending_fixtures: list[dict[str, Any]] = []

    for row in finished_rows:
        kickoff = _parse_kickoff(row["kickoff_utc"])
        status = str(row["fixture_status"] or "NS").upper()
        has_result = row["final_score"] is not None
        is_finished = has_result or classify_status(status) == "finished"
        is_past = kickoff is not None and kickoff < now

        if is_finished:
            finished_count += 1
            outcome_type = str(row["match_outcome_type"] or status or "UNKNOWN").upper()
            bucket = by_outcome_type.setdefault(
                outcome_type,
                {"count": 0, "evaluated": 0, "top1_hits": 0},
            )
            bucket["count"] += 1
            if outcome_type == "PEN" or (row["penalty_score"] and row["final_score"] and "-" in str(row["final_score"])):
                parts = str(row["final_score"]).split("-", 1)
                try:
                    if int(parts[0].strip()) == int(parts[1].strip()):
                        knockout_draw_pen += 1
                except ValueError:
                    pass

        if row["eval_id"] and str(row["eval_status"] or "evaluated") == "evaluated":
            evaluated_count += 1
            if row["top1_correct"]:
                top1_hits += 1
            if row["top3_correct"]:
                top3_hits += 1
            if row["top5_correct"]:
                top5_hits += 1
            if row["top10_correct"]:
                top10_hits += 1
            if row["rank_of_actual_score"] is not None:
                rank_sum += int(row["rank_of_actual_score"])
                rank_n += 1
            outcome_type = str(row["match_outcome_type"] or row["fixture_status"] or "UNKNOWN").upper()
            bucket = by_outcome_type.setdefault(
                outcome_type,
                {"count": 0, "evaluated": 0, "top1_hits": 0},
            )
            bucket["evaluated"] += 1
            if row["top1_correct"]:
                bucket["top1_hits"] += 1
        elif is_past and not is_finished:
            pending_count += 1
            pending_fixtures.append(
                {
                    "fixture_id": row["fixture_id"],
                    "kickoff_utc": row["kickoff_utc"],
                    "match": f"{row['home_team']} vs {row['away_team']}",
                    "reason": "missing_finished_result",
                }
            )
        elif is_finished and not row["eval_id"]:
            pending_count += 1
            pending_fixtures.append(
                {
                    "fixture_id": row["fixture_id"],
                    "kickoff_utc": row["kickoff_utc"],
                    "match": f"{row['home_team']} vs {row['away_team']}",
                    "reason": "awaiting_ecse_evaluation",
                }
            )

    def _rate(hits: int, denom: int) -> float | None:
        return round(hits / denom, 4) if denom else None

    summary = {
        "phase": PHASE,
        "generated_at": _utc_now_iso(),
        "competition_key": competition_key,
        "total_ecse_snapshots": int(total),
        "finished_fixtures": finished_count,
        "evaluated_fixtures": evaluated_count,
        "pending_fixtures": pending_count,
        "hit_rates": {
            "top1": _rate(top1_hits, evaluated_count),
            "top3": _rate(top3_hits, evaluated_count),
            "top5": _rate(top5_hits, evaluated_count),
            "top10": _rate(top10_hits, evaluated_count),
        },
        "average_actual_rank": round(rank_sum / rank_n, 2) if rank_n else None,
        "by_outcome_type": by_outcome_type,
        "knockout_draw_pen_cases": knockout_draw_pen,
        "pending_fixture_details": pending_fixtures[:50],
    }

    target = output_path or SUMMARY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def refresh_ecse_snapshot_results(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int | None = 50,
    dry_run: bool = False,
) -> EcseSnapshotSyncOutcome:
    """Quota-safe hook for background refresh — owner/internal only."""
    return sync_ecse_snapshot_results(
        settings=settings,
        competition_key=competition_key,
        past_only=True,
        min_hours_since_kickoff=DEFAULT_SAFETY_HOURS,
        dry_run=dry_run,
        force=False,
        run_ecse_backfill=True,
        limit=limit,
    )


def backfill_penalty_metadata_for_fixtures(
    *,
    settings: Settings | None = None,
    fixture_ids: list[int],
    competition_key: str = "world_cup_2026",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill match_outcome_type and penalty_score without changing ECSE evaluation scores."""
    settings = settings or get_settings()
    api = ApiFootballClient(settings)
    conn = connect(get_db_path(settings.sqlite_path))
    outcome: dict[str, Any] = {
        "phase": PHASE,
        "fixture_ids": fixture_ids,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }
    try:
        if not api.is_configured:
            outcome["errors"] = len(fixture_ids)
            outcome["details"].append({"status": "error", "reason": "api_football_not_configured"})
            return outcome

        for fixture_id in fixture_ids:
            detail: dict[str, Any] = {"fixture_id": int(fixture_id)}
            existing = conn.execute(
                """
                SELECT final_score, home_goals, away_goals, match_outcome_type, penalty_score
                FROM fixture_results WHERE fixture_id = ?
                """,
                (int(fixture_id),),
            ).fetchone()
            if not existing:
                outcome["skipped"] += 1
                detail["status"] = "no_fixture_result"
                outcome["details"].append(detail)
                continue

            try:
                call = api._safe_get(
                    "fixtures",
                    {"id": int(fixture_id)},
                    placeholder_factory=lambda: None,
                    force_refresh=True,
                )
                if not call.data:
                    outcome["errors"] += 1
                    detail["status"] = "no_provider_data"
                    outcome["details"].append(detail)
                    continue

                item = call.data[0] if isinstance(call.data, list) else call.data
                if not isinstance(item, dict):
                    outcome["errors"] += 1
                    detail["status"] = "invalid_payload"
                    outcome["details"].append(detail)
                    continue

                fixture = parse_api_fixture_item(item, source=str(call.source or "api-football"))
                if fixture is None:
                    outcome["errors"] += 1
                    detail["status"] = "parse_failed"
                    outcome["details"].append(detail)
                    continue

                score_type = final_score_type_from_status(fixture.status)
                penalty_score = _penalty_score_from_item(item)
                detail.update(
                    {
                        "provider_status": fixture.status,
                        "match_outcome_type": score_type,
                        "penalty_score": penalty_score,
                        "existing_final_score": dict(existing)["final_score"],
                    }
                )

                if dry_run:
                    detail["status"] = "dry_run"
                    outcome["details"].append(detail)
                    continue

                conn.execute(
                    """
                    UPDATE fixture_results
                    SET match_outcome_type = ?,
                        penalty_score = COALESCE(?, penalty_score)
                    WHERE fixture_id = ?
                    """,
                    (score_type, penalty_score, int(fixture_id)),
                )
                conn.execute(
                    "UPDATE fixtures SET status = ? WHERE fixture_id = ?",
                    (fixture.status, int(fixture_id)),
                )
                conn.commit()
                outcome["updated"] += 1
                detail["status"] = "updated"
                outcome["details"].append(detail)
            except Exception as exc:
                outcome["errors"] += 1
                detail["status"] = "error"
                detail["reason"] = str(exc)
                outcome["details"].append(detail)
    finally:
        conn.close()
    return outcome
