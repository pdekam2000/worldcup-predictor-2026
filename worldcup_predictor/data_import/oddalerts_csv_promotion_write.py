"""OddAlerts CSV → odds_snapshots controlled write (owner/internal)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import parse_snapshot_payload
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import (
    ECSE_REQUIRED_KEYS,
    PROCESS_DATE,
    build_ecse_readiness_summary,
    build_policy_market_matrix,
)
from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import (
    SOURCE_DETAIL,
    SOURCE_PROVIDER,
    _fetch_existing_snapshots,
    _parse_snapshot_time,
    artifact_paths as dryrun_artifact_paths,
    classify_promotion_action,
)

PHASE = "ODDALERTS-CSV-PROMOTION-3"
GENERATED_FROM = "oddalerts_csv_promotion_3"
REPORT_PATH = Path("ODDALERTS_CSV_PROMOTION_WRITE_REPORT.md")
BACKUP_DIR = Path("data/backups")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _iso_snapshot_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _date_tag(process_date: str | None = None) -> str:
    return (process_date or PROCESS_DATE).replace("-", "")


def write_artifact_paths(process_date: str | None = None) -> dict[str, Path]:
    tag = _date_tag(process_date)
    return {
        "dryrun": dryrun_artifact_paths(process_date)["dryrun_out"],
        "write_out": Path(f"artifacts/oddalerts_csv_promotion_write_{tag}.json"),
        "post_ecse": Path(f"artifacts/oddalerts_csv_post_write_ecse_readiness_{tag}.json"),
        "validation_out": Path(f"artifacts/oddalerts_csv_promotion_write_validation_{tag}.json"),
    }


def create_pre_write_backup(db_path: Path, *, backup_dir: Path | None = None) -> dict[str, Any]:
    """Create SQLite backup before promotion write. Aborts write if this fails."""
    out_dir = backup_dir or BACKUP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"football_intelligence_before_oddalerts_csv_promotion_{stamp}.db"

    settings = get_settings()
    result: dict[str, Any] = {
        "db_type": "sqlite",
        "backup_path": str(dest),
        "backup_size_bytes": 0,
        "backup_success": False,
        "postgres_dump_path": None,
    }

    if not db_path.exists():
        result["error"] = f"database not found: {db_path}"
        return result

    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(dest))
        src.backup(dst)
        dst.close()
        src.close()
        result["backup_success"] = True
        result["backup_size_bytes"] = dest.stat().st_size
    except Exception as exc:
        result["error"] = str(exc)
        if dest.exists():
            dest.unlink(missing_ok=True)
        return result

    if settings.postgres_configured and settings.database_url:
        pg_stamp = stamp
        pg_dest = out_dir / f"postgres_before_oddalerts_csv_promotion_{pg_stamp}.sql"
        try:
            proc = subprocess.run(
                ["pg_dump", settings.database_url.strip()],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode == 0 and proc.stdout:
                pg_dest.write_text(proc.stdout, encoding="utf-8")
                result["postgres_dump_path"] = str(pg_dest)
                result["postgres_dump_size_bytes"] = pg_dest.stat().st_size
        except Exception as exc:
            result["postgres_dump_note"] = f"skipped_or_failed: {exc}"

    return result


def _probabilities_valid(probs: dict[str, Any]) -> bool:
    for key in ECSE_REQUIRED_KEYS:
        val = probs.get(key)
        if val is None:
            return False
        try:
            p = float(val)
        except (TypeError, ValueError):
            return False
        if not (0 < p <= 100):
            return False
    return True


def _has_existing_oddalerts_write(conn: sqlite3.Connection, fixture_id: int, policy_version: str) -> bool:
    rows = conn.execute(
        """
        SELECT payload_json FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY snapshot_at DESC
        LIMIT 5
        """,
        (int(fixture_id),),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if payload.get("source_provider") == SOURCE_PROVIDER and str(payload.get("policy_version")) == policy_version:
            if payload.get("generated_from") == GENERATED_FROM or (
                (payload.get("metadata") or {}).get("generated_from") == GENERATED_FROM
            ):
                return True
        if payload.get("generated_from") == GENERATED_FROM and str(payload.get("policy_version")) == policy_version:
            return True
    return False


def build_insert_payload(
    candidate: dict[str, Any],
    *,
    snapshot_time: str,
    enriched_from: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preview = candidate.get("snapshot_payload_preview") or {}
    metadata = dict(preview.get("metadata") or {})
    metadata["generated_from"] = GENERATED_FROM
    metadata.setdefault("source_row_hashes", [])
    metadata.setdefault("source_files", [])
    metadata.setdefault("source_bookmakers", [])

    oddalerts_block = (preview.get("payload_json_preview") or {}).get("oddalerts_csv_policy") or {}
    if not oddalerts_block:
        oddalerts_block = {
            "probabilities_pct": preview.get("normalized_probabilities") or {},
            "metadata": {
                "bookmaker_count_avg": metadata.get("bookmaker_count_avg"),
                "selected_methods": metadata.get("selected_methods"),
                "source_row_hash_count": len(metadata.get("source_row_hashes") or []),
                "source_file_count": len(metadata.get("source_files") or []),
            },
        }

    payload: dict[str, Any] = {
        "snapshot_at": snapshot_time,
        "source_provider": SOURCE_PROVIDER,
        "source_detail": SOURCE_DETAIL,
        "policy_version": preview.get("policy_version"),
        "generated_from": GENERATED_FROM,
        "oddalerts_csv_policy": oddalerts_block,
        "markets": preview.get("markets") or {},
        "normalized_probabilities": preview.get("normalized_probabilities") or {},
        "metadata": metadata,
    }
    if enriched_from:
        payload["enriched_from"] = enriched_from
        payload["enrichment_mode"] = "new_snapshot_version"
    return payload


def filter_write_candidates(
    dryrun: dict[str, Any],
    *,
    fixture_id: int | None = None,
    limit: int | None = None,
    allow_enrich_placeholders: bool = True,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cand in dryrun.get("candidates") or []:
        if cand.get("ecse_readiness_status") != "READY_FULL":
            continue
        action = cand.get("promotion_action")
        if action == "WOULD_INSERT":
            pass
        elif action == "WOULD_ENRICH" and allow_enrich_placeholders:
            pass
        else:
            continue
        if fixture_id is not None and int(cand.get("fixture_id", 0)) != int(fixture_id):
            continue
        preview = cand.get("snapshot_payload_preview") or {}
        probs = preview.get("normalized_probabilities") or {}
        if not _probabilities_valid(probs):
            continue
        meta = preview.get("metadata") or {}
        if meta.get("crosswalk_confidence") != "MATCHED_HIGH_CONFIDENCE":
            continue
        completeness = meta.get("market_completeness") or {}
        if completeness.get("ecse_required_complete") is False:
            continue
        out.append(cand)
        if limit is not None and len(out) >= limit:
            break
    return out


def run_promotion_write(
    conn: sqlite3.Connection,
    *,
    dryrun: dict[str, Any],
    write: bool = False,
    fixture_id: int | None = None,
    limit: int | None = None,
    allow_enrich_placeholders: bool = True,
    no_overwrite_fresh_provider: bool = True,
    batch_size: int = 50,
    process_date: str | None = None,
    backup_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot_time = _iso_snapshot_at()
    ref_time = _parse_snapshot_time(dryrun.get("generated_at_utc")) or datetime.now(timezone.utc)
    policy_version = str(dryrun.get("policy_version") or PROCESS_DATE)

    odds_before = int(conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"])
    ecse_before = int(conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"])
    wde_before = int(conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"])

    candidates = filter_write_candidates(
        dryrun,
        fixture_id=fixture_id,
        limit=limit,
        allow_enrich_placeholders=allow_enrich_placeholders,
    )

    stats = {
        "candidates_processed": 0,
        "inserted_count": 0,
        "enriched_count": 0,
        "skipped_count": 0,
        "conflicts_count": 0,
        "duplicate_skip_count": 0,
        "revalidated_skip_count": 0,
    }
    written: list[dict[str, Any]] = []
    written_fixture_ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    pending_writes: list[tuple[int, str, str, str, dict[str, Any], str]] = []

    for cand in candidates:
        stats["candidates_processed"] += 1
        fid = int(cand["fixture_id"])
        action = cand.get("promotion_action")
        preview = cand.get("snapshot_payload_preview") or {}
        competition_key = preview.get("competition_key") or cand.get("competition_key") or "unknown"

        if _has_existing_oddalerts_write(conn, fid, policy_version):
            stats["duplicate_skip_count"] += 1
            stats["skipped_count"] += 1
            skipped.append({"fixture_id": fid, "reason": "ALREADY_WRITTEN_THIS_POLICY"})
            continue

        existing = _fetch_existing_snapshots(conn, fid)
        live_action, live_detail = classify_promotion_action(
            existing_snapshots=existing,
            oddalerts_reference_time=ref_time,
        )

        if live_action in ("SKIP_EXISTING_FRESH", "CONFLICT_REVIEW"):
            if no_overwrite_fresh_provider or live_action == "CONFLICT_REVIEW":
                if live_action == "CONFLICT_REVIEW":
                    stats["conflicts_count"] += 1
                else:
                    stats["skipped_count"] += 1
                skipped.append({"fixture_id": fid, "reason": live_action, "detail": live_detail})
                continue

        if live_action == "WOULD_ENRICH" and action != "WOULD_ENRICH" and not allow_enrich_placeholders:
            stats["revalidated_skip_count"] += 1
            stats["skipped_count"] += 1
            skipped.append({"fixture_id": fid, "reason": "ENRICH_NOT_ALLOWED"})
            continue

        if live_action not in ("WOULD_INSERT", "WOULD_ENRICH"):
            stats["revalidated_skip_count"] += 1
            stats["skipped_count"] += 1
            skipped.append({"fixture_id": fid, "reason": live_action, "detail": live_detail})
            continue

        enriched_from = None
        if live_action == "WOULD_ENRICH" and existing:
            latest = existing[-1]
            enriched_from = {
                "snapshot_at": latest.get("snapshot_at"),
                "source": (latest.get("payload") or {}).get("source") or (latest.get("payload") or {}).get("source_provider"),
                "original_preserved": True,
                "note": "placeholder/partial snapshot retained; new oddalerts_csv_policy snapshot appended",
            }

        payload = build_insert_payload(cand, snapshot_time=snapshot_time, enriched_from=enriched_from)
        pending_writes.append((fid, competition_key, snapshot_time, json.dumps(payload, ensure_ascii=False), payload, live_action))

    if write and pending_writes:
        try:
            conn.execute("BEGIN")
            for i, (fid, comp, snap_at, payload_json, payload_dict, live_action) in enumerate(pending_writes, 1):
                conn.execute(
                    """
                    INSERT INTO odds_snapshots (fixture_id, competition_key, snapshot_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (fid, comp, snap_at, payload_json),
                )
                if live_action == "WOULD_INSERT":
                    stats["inserted_count"] += 1
                else:
                    stats["enriched_count"] += 1
                written_fixture_ids.append(fid)
                written.append(
                    {
                        "fixture_id": fid,
                        "match": next((c.get("match") for c in candidates if int(c["fixture_id"]) == fid), ""),
                        "competition_key": comp,
                        "promotion_action": live_action,
                        "snapshot_at": snap_at,
                        "source_provider": SOURCE_PROVIDER,
                        "source_detail": SOURCE_DETAIL,
                        "ecse_markets": list(ECSE_REQUIRED_KEYS),
                        "payload_preview": {
                            "markets": payload_dict.get("markets"),
                            "metadata": {
                                "source_row_hash_count": len((payload_dict.get("metadata") or {}).get("source_row_hashes") or []),
                                "generated_from": GENERATED_FROM,
                            },
                        },
                    }
                )
                if batch_size > 0 and i % batch_size == 0:
                    conn.commit()
                    conn.execute("BEGIN")
            conn.commit()
        except Exception as exc:
            conn.rollback()
            errors.append({"fatal": True, "error": str(exc)})
            raise
    elif not write:
        for fid, comp, snap_at, _payload_json, payload_dict, live_action in pending_writes:
            if live_action == "WOULD_INSERT":
                stats["inserted_count"] += 1
            else:
                stats["enriched_count"] += 1
            written_fixture_ids.append(fid)
            written.append(
                {
                    "fixture_id": fid,
                    "match": next((c.get("match") for c in candidates if int(c["fixture_id"]) == fid), ""),
                    "competition_key": comp,
                    "promotion_action": live_action,
                    "snapshot_at": snap_at,
                    "dry_run_only": True,
                    "payload_preview": {"markets": payload_dict.get("markets")},
                }
            )

    odds_after = int(conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"])
    ecse_after = int(conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"])
    wde_after = int(conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"])

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "date_processed": process_date or dryrun.get("date_processed") or PROCESS_DATE,
        "write_mode": write,
        "dry_run_only": not write,
        "policy_version": policy_version,
        "backup": backup_info,
        "odds_snapshots_before": odds_before,
        "odds_snapshots_after": odds_after,
        "odds_snapshots_delta": odds_after - odds_before,
        "ecse_snapshots_before": ecse_before,
        "ecse_snapshots_after": ecse_after,
        "wde_predictions_before": wde_before,
        "wde_predictions_after": wde_after,
        "expected_writes": stats["inserted_count"] + stats["enriched_count"] if not write else None,
        **stats,
        "written_fixtures": written[:50],
        "written_fixture_ids": written_fixture_ids,
        "written_sample_count": len(written),
        "skipped_fixtures": skipped[:100],
        "errors": errors,
        "enrichment_behavior": (
            "New odds_snapshots row appended per fixture; original placeholder/partial rows preserved (immutable)."
        ),
        "rollback_command": (
            f"cp {backup_info['backup_path']} {get_settings().sqlite_path}"
            if backup_info and backup_info.get("backup_success")
            else "Restore from data/backups/football_intelligence_before_oddalerts_csv_promotion_*.db"
        ),
    }


def build_post_write_ecse_readiness(conn: sqlite3.Connection, written_fixture_ids: list[int]) -> dict[str, Any]:
    matrix = build_policy_market_matrix(conn)
    ecse_summary = build_ecse_readiness_summary(matrix)

    fixture_rows = []
    if written_fixture_ids:
        placeholders = ",".join("?" * len(written_fixture_ids))
        for row in conn.execute(
            f"""
            SELECT f.fixture_id, f.home_team, f.away_team, f.competition_key, f.kickoff_utc
            FROM fixtures f
            WHERE f.fixture_id IN ({placeholders})
            """,
            written_fixture_ids,
        ).fetchall():
            fid = int(row["fixture_id"])
            snaps = conn.execute(
                """
                SELECT snapshot_at, payload_json FROM odds_snapshots
                WHERE fixture_id = ?
                ORDER BY snapshot_at DESC LIMIT 1
                """,
                (fid,),
            ).fetchone()
            ecse_odds_ready = False
            missing_fields: list[str] = []
            if snaps:
                try:
                    payload = json.loads(snaps["payload_json"])
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                if payload.get("source_provider") == SOURCE_PROVIDER:
                    probs = payload.get("normalized_probabilities") or {}
                    if _probabilities_valid(probs):
                        ecse_odds_ready = True
                    else:
                        missing_fields = sorted(ECSE_REQUIRED_KEYS - set(probs.keys()))
                else:
                    parsed = parse_snapshot_payload(payload, fixture_id=fid, captured_at=snaps["snapshot_at"])
                    for label, keys in (
                        ("1x2", ("odds_implied_home", "odds_implied_draw", "odds_implied_away")),
                        ("ou25", ("odds_implied_over_25", "odds_implied_under_25")),
                        ("btts", ("odds_implied_btts_yes", "odds_implied_btts_no")),
                    ):
                        if not all(parsed.get(k) is not None for k in keys):
                            missing_fields.append(label)
                    ecse_odds_ready = not missing_fields

            fixture_rows.append(
                {
                    "fixture_id": fid,
                    "match": f"{row['home_team']} vs {row['away_team']}",
                    "competition_key": row["competition_key"],
                    "ecse_odds_snapshot_ready": ecse_odds_ready,
                    "missing_fields": missing_fields,
                }
            )

    ready_rows = [r for r in fixture_rows if r["ecse_odds_snapshot_ready"]]
    wc = [r for r in ready_rows if (r.get("competition_key") or "").startswith("world_cup")]
    uefa = [
        r
        for r in ready_rows
        if any(x in (r.get("competition_key") or "") for x in ("uefa", "euro", "champions", "europa", "conference", "premier"))
    ]

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "fixtures_written_count": len(written_fixture_ids),
        "fixtures_ecse_odds_ready_count": len(ready_rows),
        "policy_ready_full_count": ecse_summary.get("ready_full_count", 0),
        "competitions_covered": sorted({r["competition_key"] for r in ready_rows if r.get("competition_key")}),
        "world_cup_fixtures": wc,
        "uefa_fixtures": uefa[:50],
        "fixtures": fixture_rows[:100],
        "missing_fields_summary": sorted({f for r in fixture_rows for f in r.get("missing_fields") or []}),
        "note": "ECSE snapshot generation not performed — odds_snapshots readiness check only.",
    }


def write_final_recommendation(result: dict[str, Any], *, validation: dict[str, Any] | None = None) -> str:
    if result.get("backup") and result.get("write_mode") and not result["backup"].get("backup_success"):
        return "WRITE_ABORTED_BACKUP_FAILED"

    if validation and validation.get("failed", 0) > 0 and result.get("write_mode"):
        return "WRITE_ABORTED_VALIDATION_FAILED"

    if result.get("conflicts_count", 0) > 0:
        return "CONFLICT_REVIEW_REQUIRED"

    if not result.get("write_mode"):
        expected = (result.get("inserted_count") or 0) + (result.get("enriched_count") or 0)
        if expected > 0:
            return "ODDALERTS_ODDS_PROMOTION_DRYRUN_READY"
        return "DO_NOT_USE_WRITTEN_ODDS"

    delta = int(result.get("odds_snapshots_delta") or 0)
    inserted = int(result.get("inserted_count") or 0)
    enriched = int(result.get("enriched_count") or 0)
    expected = inserted + enriched

    if result.get("errors"):
        return "WRITE_ABORTED_VALIDATION_FAILED"

    if delta == 0 and expected > 0:
        return "WRITE_ABORTED_VALIDATION_FAILED"

    if delta < expected:
        return "PARTIAL_WRITE_COMPLETED"

    if delta == expected and expected > 0:
        return "ODDALERTS_ODDS_SNAPSHOTS_WRITTEN"

    if delta > 0:
        return "PARTIAL_WRITE_COMPLETED"

    return "DO_NOT_USE_WRITTEN_ODDS"


def build_write_report_markdown(result: dict[str, Any], *, ecse: dict[str, Any] | None = None, validation: dict[str, Any] | None = None) -> str:
    ecse = ecse or {}
    validation = validation or {}
    rec = result.get("final_recommendation") or write_final_recommendation(result, validation=validation)
    backup = result.get("backup") or {}

    sample_lines = []
    for w in (result.get("written_fixtures") or [])[:10]:
        sample_lines.append(
            f"| {w.get('fixture_id')} | {(w.get('match') or '')[:36]} | {w.get('promotion_action')} | {w.get('competition_key')} |"
        )

    val_lines = []
    for c in validation.get("checks") or []:
        mark = "pass" if c.get("passed") else "FAIL"
        val_lines.append(f"- [{mark}] {c.get('check')}: {c.get('detail', '')}")

    return f"""# OddAlerts CSV Promotion Write Report

**Phase:** {PHASE}  
**Date:** {result.get('date_processed', PROCESS_DATE)}  
**Generated:** {result.get('generated_at_utc', _utc_now())}  
**Mode:** {'WRITE' if result.get('write_mode') else 'DRY-RUN'} — no ECSE/WDE generation

---

## Summary

**Final recommendation:** `{rec}`

---

## Part A — Backup

| Field | Value |
|-------|-------|
| DB type | {backup.get('db_type', 'sqlite')} |
| Backup path | `{backup.get('backup_path', 'n/a')}` |
| Backup size | {backup.get('backup_size_bytes', 0):,} bytes |
| Backup success | {backup.get('backup_success', False)} |

---

## Part B — Write results

| Metric | Value |
|--------|-------|
| Candidates processed | {result.get('candidates_processed', 0)} |
| Inserted | {result.get('inserted_count', 0)} |
| Enriched (new snapshot version) | {result.get('enriched_count', 0)} |
| Skipped | {result.get('skipped_count', 0)} |
| Conflicts | {result.get('conflicts_count', 0)} |
| Duplicate skip (re-run) | {result.get('duplicate_skip_count', 0)} |
| odds_snapshots before | {result.get('odds_snapshots_before', 0):,} |
| odds_snapshots after | {result.get('odds_snapshots_after', 0):,} |
| odds_snapshots delta | {result.get('odds_snapshots_delta', 0)} |

**Enrichment behavior:** {result.get('enrichment_behavior', '')}

---

## Part C — Sample written fixtures

| Fixture ID | Match | Action | Competition |
|------------|-------|--------|-------------|
{chr(10).join(sample_lines) if sample_lines else '| — | — | — | — |'}

---

## Part D — Post-write ECSE readiness (check only)

| Metric | Value |
|--------|-------|
| Fixtures written | {ecse.get('fixtures_written_count', 0)} |
| ECSE odds-snapshot ready | {ecse.get('fixtures_ecse_odds_ready_count', 0)} |
| Policy READY_FULL | {ecse.get('policy_ready_full_count', 0)} |
| WC fixtures | {len(ecse.get('world_cup_fixtures') or [])} |
| UEFA/PL fixtures (sample) | {len(ecse.get('uefa_fixtures') or [])} |

---

## Part E — Validation

{chr(10).join(val_lines) if val_lines else '- Run validate_oddalerts_csv_promotion_write.py'}

Passed: **{validation.get('passed', '?')}** / **{(validation.get('passed') or 0) + (validation.get('failed') or 0)}**

---

## Rollback

If rollback is required:

```bash
{result.get('rollback_command', 'cp data/backups/football_intelligence_before_oddalerts_csv_promotion_*.db data/football_intelligence.db')}
```

Stop the app/services first, restore the backup file, then restart.
"""
