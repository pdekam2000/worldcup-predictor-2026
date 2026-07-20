"""Persistence helpers for ECSE timing experiment."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_timing_experiment.hashing import content_hash, stable_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def ensure_experiment(
    conn: sqlite3.Connection,
    *,
    experiment_date: str,
    scope: str,
    timezone: str,
    git_sha: str | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    row = conn.execute(
        "SELECT experiment_id FROM timing_experiments WHERE experiment_date=? AND scope=? LIMIT 1",
        (experiment_date, scope),
    ).fetchone()
    if row:
        return str(row["experiment_id"])
    eid = f"timing_{experiment_date}_{scope}_{uuid.uuid4().hex[:8]}"
    conn.execute(
        """
        INSERT INTO timing_experiments(
            experiment_id, experiment_date, timezone, scope, created_at_utc, status, git_sha, meta_json
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            eid,
            experiment_date,
            timezone,
            scope,
            _utc_now(),
            "ACTIVE",
            git_sha,
            stable_json(meta or {}),
        ),
    )
    conn.commit()
    return eid


def upsert_fixture(
    conn: sqlite3.Connection,
    *,
    experiment_id: str,
    fixture: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO timing_experiment_fixtures(
            experiment_id, fixture_id, home_team, away_team, league, country, competition_key,
            kickoff_utc, kickoff_vienna, tier, prediction_scope, discovery_status, exclusion_reason,
            provider, bookmaker_count, latest_odds_timestamp, meta_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(experiment_id, fixture_id) DO UPDATE SET
            home_team=excluded.home_team,
            away_team=excluded.away_team,
            league=excluded.league,
            country=excluded.country,
            competition_key=excluded.competition_key,
            kickoff_utc=excluded.kickoff_utc,
            kickoff_vienna=excluded.kickoff_vienna,
            tier=excluded.tier,
            prediction_scope=excluded.prediction_scope,
            discovery_status=excluded.discovery_status,
            exclusion_reason=excluded.exclusion_reason,
            provider=excluded.provider,
            bookmaker_count=excluded.bookmaker_count,
            latest_odds_timestamp=excluded.latest_odds_timestamp,
            meta_json=excluded.meta_json
        """,
        (
            experiment_id,
            int(fixture["fixture_id"]),
            fixture.get("home_team"),
            fixture.get("away_team"),
            fixture.get("league"),
            fixture.get("country"),
            fixture.get("competition_key"),
            fixture.get("kickoff_utc"),
            fixture.get("kickoff_vienna"),
            fixture.get("tier"),
            fixture.get("prediction_scope"),
            fixture.get("discovery_status") or "INCLUDED",
            fixture.get("exclusion_reason"),
            fixture.get("provider"),
            fixture.get("bookmaker_count"),
            fixture.get("latest_odds_timestamp"),
            stable_json(fixture.get("meta") or {}),
        ),
    )
    conn.commit()


def get_snapshot(
    conn: sqlite3.Connection,
    *,
    experiment_id: str,
    fixture_id: int,
    snapshot_class: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM timing_prediction_snapshots
        WHERE experiment_id=? AND fixture_id=? AND snapshot_class=?
        LIMIT 1
        """,
        (experiment_id, int(fixture_id), snapshot_class.upper()),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["payload"] = json.loads(d.get("payload_json") or "{}")
    except json.JSONDecodeError:
        d["payload"] = {}
    return d


def insert_snapshot_immutable(
    conn: sqlite3.Connection,
    *,
    experiment_id: str,
    fixture_id: int,
    snapshot_class: str,
    status: str,
    payload: dict[str, Any],
    window_classification: str | None = None,
    hours_to_kickoff: float | None = None,
    captured_at_utc: str | None = None,
    captured_at_vienna: str | None = None,
    block_reason: str | None = None,
    odds_content_hash: str | None = None,
    model_config_hash: str | None = None,
    freeze_id: str | None = None,
    freeze_hash: str | None = None,
    freeze_unchanged: bool | None = None,
    freeze_capture: bool = False,
    wsp_restored: bool | None = None,
    temporary_run_audit_id: str | None = None,
) -> dict[str, Any]:
    """Insert snapshot once. Successful rows are immutable; reruns are idempotent."""
    sc = snapshot_class.upper()
    existing = get_snapshot(conn, experiment_id=experiment_id, fixture_id=fixture_id, snapshot_class=sc)
    if existing:
        # Allow replacing only non-success blocked rows on explicit retry of same block? No —
        # blocked rows are also terminal for that class to keep audit trail. Return existing.
        return {
            "inserted": False,
            "idempotent": True,
            "snapshot_id": existing["snapshot_id"],
            "status": existing["status"],
            "block_reason": existing.get("block_reason"),
            "research_output_hash": existing.get("research_output_hash"),
        }

    captured = captured_at_utc or _utc_now()
    research_hash = content_hash(payload)
    sid = f"snap_{experiment_id}_{fixture_id}_{sc}_{research_hash[:10]}"
    conn.execute(
        """
        INSERT INTO timing_prediction_snapshots(
            snapshot_id, experiment_id, fixture_id, snapshot_class, window_classification,
            hours_to_kickoff, captured_at_utc, captured_at_vienna, status, block_reason,
            payload_json, research_output_hash, odds_content_hash, model_config_hash,
            freeze_id, freeze_hash, freeze_unchanged, freeze_capture, wsp_restored,
            temporary_run_audit_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            sid,
            experiment_id,
            int(fixture_id),
            sc,
            window_classification,
            hours_to_kickoff,
            captured,
            captured_at_vienna,
            status,
            block_reason,
            stable_json(payload),
            research_hash,
            odds_content_hash,
            model_config_hash,
            freeze_id,
            freeze_hash,
            None if freeze_unchanged is None else int(bool(freeze_unchanged)),
            int(bool(freeze_capture)),
            None if wsp_restored is None else int(bool(wsp_restored)),
            temporary_run_audit_id,
        ),
    )
    conn.commit()
    return {
        "inserted": True,
        "idempotent": False,
        "snapshot_id": sid,
        "status": status,
        "block_reason": block_reason,
        "research_output_hash": research_hash,
    }


def upsert_comparison(
    conn: sqlite3.Connection,
    *,
    experiment_id: str,
    fixture_id: int,
    comparison: dict[str, Any],
) -> str:
    cid = f"cmp_{experiment_id}_{fixture_id}_{comparison['from_class']}_{comparison['to_class']}"
    conn.execute(
        """
        INSERT INTO timing_snapshot_comparisons(
            comparison_id, experiment_id, fixture_id, from_class, to_class,
            compared_at_utc, payload_json, primary_stability_label, labels_json
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(experiment_id, fixture_id, from_class, to_class) DO UPDATE SET
            compared_at_utc=excluded.compared_at_utc,
            payload_json=excluded.payload_json,
            primary_stability_label=excluded.primary_stability_label,
            labels_json=excluded.labels_json
        """,
        (
            cid,
            experiment_id,
            int(fixture_id),
            comparison["from_class"],
            comparison["to_class"],
            _utc_now(),
            stable_json(comparison),
            comparison.get("primary_stability_label"),
            stable_json(comparison.get("labels") or []),
        ),
    )
    conn.commit()
    return cid


def upsert_evaluation(
    conn: sqlite3.Connection,
    *,
    experiment_id: str,
    fixture_id: int,
    snapshot_class: str,
    result_status: str,
    actual_score: str | None,
    payload: dict[str, Any],
    event_labels: list[str] | None = None,
) -> str:
    eid = f"eval_{experiment_id}_{fixture_id}_{snapshot_class}"
    conn.execute(
        """
        INSERT INTO timing_result_evaluations(
            evaluation_id, experiment_id, fixture_id, snapshot_class, evaluated_at_utc,
            result_status, actual_score, payload_json, event_labels_json
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(experiment_id, fixture_id, snapshot_class) DO UPDATE SET
            evaluated_at_utc=excluded.evaluated_at_utc,
            result_status=excluded.result_status,
            actual_score=excluded.actual_score,
            payload_json=excluded.payload_json,
            event_labels_json=excluded.event_labels_json
        """,
        (
            eid,
            experiment_id,
            int(fixture_id),
            snapshot_class,
            _utc_now(),
            result_status,
            actual_score,
            stable_json(payload),
            stable_json(event_labels or []),
        ),
    )
    conn.commit()
    return eid


def upsert_stable_union(
    conn: sqlite3.Connection,
    *,
    experiment_id: str,
    fixture_id: int,
    union_payload: dict[str, Any],
) -> str:
    uid = f"union_{experiment_id}_{fixture_id}"
    assert union_payload.get("research_only") is True
    assert union_payload.get("canonical") is False
    assert union_payload.get("final_decision_authority") is False
    conn.execute(
        """
        INSERT INTO timing_stable_union_predictions(
            union_id, experiment_id, fixture_id, built_at_utc, scores_json,
            research_only, canonical, final_decision_authority, payload_json
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(experiment_id, fixture_id) DO UPDATE SET
            built_at_utc=excluded.built_at_utc,
            scores_json=excluded.scores_json,
            payload_json=excluded.payload_json
        """,
        (
            uid,
            experiment_id,
            int(fixture_id),
            _utc_now(),
            stable_json(union_payload.get("scores") or []),
            1,
            0,
            0,
            stable_json(union_payload),
        ),
    )
    conn.commit()
    return uid


def list_experiments(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    q = "SELECT * FROM timing_experiments WHERE 1=1"
    params: list[Any] = []
    if date_from:
        q += " AND experiment_date >= ?"
        params.append(date_from)
    if date_to:
        q += " AND experiment_date <= ?"
        params.append(date_to)
    q += " ORDER BY experiment_date"
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def list_successful_snapshots(
    conn: sqlite3.Connection,
    experiment_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM timing_prediction_snapshots
        WHERE experiment_id=? AND status='CAPTURED'
        ORDER BY fixture_id, snapshot_class
        """,
        (experiment_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload_json") or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
        out.append(d)
    return out
