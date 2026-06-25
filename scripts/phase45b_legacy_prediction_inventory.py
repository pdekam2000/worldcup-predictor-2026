#!/usr/bin/env python3
"""Phase 45B — inventory historical prediction sources."""

from __future__ import annotations

import json
import runpy
import sqlite3
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())


def _sample_jsonl(path: Path, limit: int = 3) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(rows) >= limit:
            break
    return rows


def _sqlite_count(db: Path, table: str) -> int | None:
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(str(db))
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def main() -> int:
    root = Path(".")
    db = root / "data" / "football_intelligence.db"

    sources: list[dict] = []

    def add(name: str, **kwargs) -> None:
        sources.append({"source": name, **kwargs})

    stored = _sqlite_count(db, "worldcup_stored_predictions")
    add(
        "worldcup_stored_predictions (SQLite)",
        count=stored,
        has_payload=True,
        has_generated_at=True,
        safe_to_import=False,
        user_private=False,
        notes="Current global archive (Phase 33+). Authoritative production store.",
    )

    legacy_preds = _sqlite_count(db, "predictions")
    add(
        "predictions (legacy SQLite)",
        count=legacy_preds,
        has_payload=True,
        has_generated_at=True,
        safe_to_import=False,
        user_private=True,
        notes="Legacy table — may overlap user-scoped rows; admin inventory only unless deduped.",
    )

    hist_jsonl = root / "data" / "prediction_history.jsonl"
    hist_count = _count_jsonl(hist_jsonl)
    samples = _sample_jsonl(hist_jsonl)
    add(
        "prediction_history.jsonl",
        count=hist_count,
        has_payload=any(isinstance(s, dict) and s.get("prediction") for s in samples),
        has_generated_at=any(isinstance(s, dict) and (s.get("generated_at") or s.get("created_at")) for s in samples),
        safe_to_import=False,
        user_private=True,
        notes="User/history JSONL — not for public performance import.",
    )

    verify_jsonl = root / "data" / "verification" / "prediction_verification.jsonl"
    verify_count = _count_jsonl(verify_jsonl)
    add(
        "prediction_verification.jsonl",
        count=verify_count,
        has_payload=True,
        has_generated_at=True,
        safe_to_import=False,
        user_private=False,
        notes="Verification audit trail — not authoritative for public accuracy.",
    )

    cache_dir = root / ".cache" / "predictions"
    cache_files = list(cache_dir.glob("**/*.json")) if cache_dir.is_dir() else []
    add(
        ".cache/predictions/",
        count=len(cache_files),
        has_payload=True,
        has_generated_at=True,
        safe_to_import=False,
        user_private=True,
        notes="Per-fixture cache files — may duplicate stored predictions.",
    )

    report_path = root / "PHASE_45B_LEGACY_PREDICTION_INVENTORY.md"
    lines = [
        "# Phase 45B — Legacy Prediction Inventory",
        "",
        f"Generated from workspace inventory scan.",
        "",
        "| Source | Count | Payload | Timestamp | Finished result | Safe import | User-private | Notes |",
        "|--------|------:|---------|-----------|-----------------|-------------|--------------|-------|",
    ]
    for s in sources:
        lines.append(
            f"| {s['source']} | {s.get('count', 'n/a')} | "
            f"{'yes' if s.get('has_payload') else 'no'} | "
            f"{'yes' if s.get('has_generated_at') else 'no'} | "
            f"partial | "
            f"{'yes' if s.get('safe_to_import') else 'no'} | "
            f"{'yes' if s.get('user_private') else 'no'} | "
            f"{s.get('notes', '')} |"
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "- Do **not** import legacy/cache rows into public performance metrics.",
            "- Global archive (`worldcup_stored_predictions`) is the authoritative count for platform predictions.",
            "- Legacy sources remain visible in admin diagnostics only.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {report_path}")
    print(json.dumps(sources, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
