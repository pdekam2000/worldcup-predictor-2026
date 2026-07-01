"""Incremental OddAlerts inbox CSV import — catalog/stage only, no odds snapshots."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.oddalerts_csv_incremental_ddl import ensure_oddalerts_inbox_catalog_tables
from worldcup_predictor.data_import.oddalerts_enrichment_csv_importer import (
    ARCHIVE_DIR,
    INBOX_DIR,
    PROCESSED_DIR,
    REJECTED_DIR,
    detect_csv_type,
    import_csv_file,
    profile_csv_file,
)

PHASE = "ODDALERTS-CSV-INCREMENTAL"
IMPORT_SUMMARY_PATH = Path("artifacts/oddalerts_csv_incremental_import_summary.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_filename_metadata(filename: str) -> dict[str, str | None]:
    """Best-effort parse oddalerts_{market}_{outcome}_{from}_{to}_{ts}_{hash}.csv"""
    stem = Path(filename).stem
    if not stem.startswith("oddalerts_"):
        return {"market": None, "outcome": None, "date_from": None, "date_to": None}
    parts = stem.split("_")
    if len(parts) < 8:
        return {"market": None, "outcome": None, "date_from": None, "date_to": None}
    # last two: ts + hash; before that two ISO dates
    date_to = parts[-3] if len(parts[-3]) == 10 else None
    date_from = parts[-4] if len(parts[-4]) == 10 else None
    body = parts[1:-4]
    if not body:
        return {"market": None, "outcome": None, "date_from": date_from, "date_to": date_to}
    # heuristic: last token of body is outcome slug
    outcome = body[-1]
    market = "_".join(body[:-1]) if len(body) > 1 else body[0]
    return {"market": market, "outcome": outcome, "date_from": date_from, "date_to": date_to}


@dataclass
class IncrementalImportBatch:
    files_scanned: int = 0
    probability_staged: int = 0
    probability_skipped_duplicate: int = 0
    enrichment_imported: int = 0
    enrichment_skipped: int = 0
    rejected: int = 0
    unknown: int = 0
    files: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "generated_at_utc": _utc_now(),
            "files_scanned": self.files_scanned,
            "probability_staged": self.probability_staged,
            "probability_skipped_duplicate": self.probability_skipped_duplicate,
            "enrichment_imported": self.enrichment_imported,
            "enrichment_skipped": self.enrichment_skipped,
            "rejected": self.rejected,
            "unknown": self.unknown,
            "promoted_to_odds_snapshots": False,
            "files": self.files,
        }


def import_inbox_incremental(
    conn,
    *,
    input_dir: Path | None = None,
    dry_run: bool = False,
) -> IncrementalImportBatch:
    inbox = input_dir or INBOX_DIR
    batch = IncrementalImportBatch()
    ensure_oddalerts_inbox_catalog_tables(conn)

    paths = sorted(inbox.glob("*.csv"))
    batch.files_scanned = len(paths)

    for path in paths:
        if path.name.startswith("_"):
            continue

        profile = profile_csv_file(path)
        csv_type = profile["csv_type"]
        digest = _file_sha256(path)
        meta = _parse_filename_metadata(path.name)

        entry: dict[str, Any] = {
            "filename": path.name,
            "csv_type": csv_type,
            "sha256_prefix": digest[:12],
            "row_count": profile.get("row_count", 0),
            "status": "pending",
            "error": None,
        }

        existing = conn.execute(
            "SELECT id, import_status FROM oddalerts_inbox_csv_catalog WHERE source_sha256 = ?",
            (digest,),
        ).fetchone()

        if csv_type == "ODDS_CSV":
            if existing:
                entry["status"] = "skipped_duplicate"
                batch.probability_skipped_duplicate += 1
                batch.files.append(entry)
                continue

            if dry_run:
                entry["status"] = "dry_run_staged"
                batch.probability_staged += 1
                batch.files.append(entry)
                continue

            conn.execute(
                """
                INSERT INTO oddalerts_inbox_csv_catalog (
                    source_file, source_sha256, csv_type, market, outcome,
                    date_from, date_to, row_count, gmail_message_id,
                    import_status, error, cataloged_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    path.name,
                    digest,
                    csv_type,
                    meta.get("market"),
                    meta.get("outcome"),
                    meta.get("date_from"),
                    meta.get("date_to"),
                    int(profile.get("row_count") or 0),
                    None,
                    "staged",
                    None,
                    _utc_now(),
                ),
            )
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, ARCHIVE_DIR / path.name)
            PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(PROCESSED_DIR / path.name))
            entry["status"] = "staged"
            batch.probability_staged += 1

        elif csv_type in {"PLAYER_STATS_CSV", "REFEREE_CARDS_CSV"}:
            if dry_run:
                entry["status"] = "dry_run_enrichment"
                batch.files.append(entry)
                continue
            result = import_csv_file(conn, path, dry_run=False)
            entry["status"] = result.status
            entry["imported"] = result.imported
            entry["skipped_duplicate"] = result.skipped_duplicate
            if result.imported:
                batch.enrichment_imported += result.imported
            elif result.skipped_duplicate:
                batch.enrichment_skipped += result.skipped_duplicate
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, ARCHIVE_DIR / path.name)
            if result.status.startswith("rejected"):
                REJECTED_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(REJECTED_DIR / path.name))
                batch.rejected += 1
            else:
                PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(PROCESSED_DIR / path.name))

        elif csv_type == "UNKNOWN_CSV":
            entry["status"] = "rejected_unknown"
            batch.unknown += 1
            batch.rejected += 1
            if not dry_run:
                REJECTED_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(REJECTED_DIR / path.name))

        batch.files.append(entry)

    if not dry_run:
        conn.commit()

    summary = batch.to_dict()
    IMPORT_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMPORT_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return batch
