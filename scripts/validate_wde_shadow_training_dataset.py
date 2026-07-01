#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-1 Part C — Validate WDE shadow training dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.wde_shadow_historical.constants import (
    DATASET_SUMMARY,
    READINESS_ARTIFACT,
    VALIDATION_ARTIFACT,
)
from worldcup_predictor.research.wde_shadow_historical.dataset_validation import validate_shadow_dataset
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists
from worldcup_predictor.research.wde_shadow_historical.prep_report import (
    derive_prep_recommendation,
    write_prep_report,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WDE shadow training dataset")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    settings = get_settings()
    conn = connect_readonly(settings.sqlite_path)

    wde_before = table_count(conn, "worldcup_stored_predictions") if table_exists(conn, "worldcup_stored_predictions") else None
    odds_before = table_count(conn, "odds_snapshots") if table_exists(conn, "odds_snapshots") else None

    validation = validate_shadow_dataset(conn, wde_before=wde_before, odds_before=odds_before)
    conn.close()

    readiness = json.loads(READINESS_ARTIFACT.read_text(encoding="utf-8")) if READINESS_ARTIFACT.exists() else {}
    build = json.loads(DATASET_SUMMARY.read_text(encoding="utf-8")) if DATASET_SUMMARY.exists() else {}
    recommendation = derive_prep_recommendation(readiness=readiness, build=build, validation=validation.to_dict())
    write_prep_report(recommendation=recommendation, readiness=readiness, build=build, validation=validation.to_dict())

    out = {**validation.to_dict(), "recommendation": recommendation}
    VALIDATION_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_ARTIFACT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if validation.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
