"""Phase 6 storage growth estimates and retention policy (research evidence preserved)."""

from __future__ import annotations

from typing import Any

# Conservative per-fixture storage (SQLite rows + modest JSON artifacts), bytes
BYTES_PER_FIXTURE_DB = 45_000  # freeze + shadow lambda/exact + job + eval stubs
BYTES_PER_FIXTURE_ARTIFACT = 25_000  # compact item JSON; avoid full payload dumps
BYTES_PER_DAY_LOGS = 2_000_000  # operational logs before rotation
BYTES_PER_DAY_REPORT = 150_000

DEFAULT_DAILY_FIXTURES = 100
MIN_FREE_GB = 8.0
ALERT_FREE_GB = 10.0


def estimate_growth(
    *,
    fixtures_per_day: int = DEFAULT_DAILY_FIXTURES,
    days: int = 30,
) -> dict[str, Any]:
    n = max(0, int(fixtures_per_day)) * max(0, int(days))
    db = n * BYTES_PER_FIXTURE_DB
    art = n * BYTES_PER_FIXTURE_ARTIFACT + max(0, int(days)) * BYTES_PER_DAY_REPORT
    logs = max(0, int(days)) * BYTES_PER_DAY_LOGS
    total = db + art + logs
    return {
        "fixtures_per_day": fixtures_per_day,
        "days": days,
        "fixture_events": n,
        "db_bytes": db,
        "artifact_bytes": art,
        "log_bytes_before_rotation": logs,
        "total_bytes": total,
        "total_gb": round(total / (1024**3), 3),
        "assumptions": {
            "bytes_per_fixture_db": BYTES_PER_FIXTURE_DB,
            "bytes_per_fixture_artifact": BYTES_PER_FIXTURE_ARTIFACT,
            "bytes_per_day_logs": BYTES_PER_DAY_LOGS,
            "bytes_per_day_report": BYTES_PER_DAY_REPORT,
            "no_duplicate_full_payload_json_dumps": True,
        },
    }


def retention_policy() -> dict[str, Any]:
    return {
        "keep_forever_until_archival_policy": [
            "canonical predictions (worldcup_stored_predictions)",
            "immutable freezes (frozen_predictions)",
            "L2F shadow outputs (lambda/exact shadow tables)",
            "l2f_forward_shadow_jobs",
            "l2f_shadow_evaluations",
            "phase6 sampling/universe artifacts (compressed after 30d ok)",
        ],
        "rotate_or_compress": [
            "verbose operational logs (gzip after 7d, delete after 45d)",
            "generated daily markdown reports older than 90d (keep latest cumulative)",
            "job-store transient JSON after successful terminal state (30d)",
        ],
        "never_delete_without_explicit_archival": [
            "immutable research evidence freezes",
            "true_forward evaluation rows",
            "preregistration documents",
        ],
        "runtime_disk_rules": {
            "check_before_each_batch": True,
            "stop_new_batch_if_free_gb_below": MIN_FREE_GB,
            "alert_if_free_gb_below": ALERT_FREE_GB,
            "no_large_uncompressed_db_backups": True,
            "no_duplicate_complete_payload_json_dumps": True,
        },
    }


def storage_outlook(*, fixtures_per_day: int = DEFAULT_DAILY_FIXTURES) -> dict[str, Any]:
    return {
        "d30": estimate_growth(fixtures_per_day=fixtures_per_day, days=30),
        "d90": estimate_growth(fixtures_per_day=fixtures_per_day, days=90),
        "d180": estimate_growth(fixtures_per_day=fixtures_per_day, days=180),
        "retention": retention_policy(),
        "pilot_note": (
            "At ~9.8G free, run caps 20→50 before 100/day. "
            "100/day × 180d ≈ see d180.total_gb; enforce 8G stop gate."
        ),
    }
