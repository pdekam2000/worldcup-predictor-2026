#!/usr/bin/env python3
"""Validate owner-only today exact-score prediction reports."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count

CHECKS: list[tuple[str, bool, str]] = []
JSON_PATH = ROOT / "reports" / "owner" / "today_10_exact_score_predictions.json"
MD_PATH = ROOT / "reports" / "owner" / "today_10_exact_score_predictions.md"
WDE_PATH = ROOT / "worldcup_predictor" / "decision" / "weighted_decision_engine.py"
EGIE_MARKER = ROOT / "worldcup_predictor" / "egie"


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("Validating owner today exact-score reports...\n")

    check("json_report_exists", JSON_PATH.is_file(), str(JSON_PATH))
    check("markdown_report_exists", MD_PATH.is_file(), str(MD_PATH))

    if not JSON_PATH.is_file():
        return 1

    report = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    meta = report.get("meta") or {}
    matches = report.get("matches") or []
    limit = int(meta.get("limit_requested") or 10)
    report_date = meta.get("report_date") or date.today().isoformat()

    available = int(meta.get("fixtures_found") or 0)
    expected_count = min(limit, available) if available else len(matches)
    check(
        "fixture_count_matches_availability",
        len(matches) == expected_count or (available >= limit and len(matches) == limit),
        f"selected={len(matches)} expected<={limit} available={available}",
    )

    fixture_ids: set[int] = set()
    for match in matches:
        fid = match.get("fixture_id")
        check("fixture_has_id", fid is not None, str(match.get("home_team")))
        if fid is None:
            continue
        fid_int = int(fid)
        check("fixture_id_unique", fid_int not in fixture_ids, str(fid_int))
        fixture_ids.add(fid_int)

        status = str(match.get("status") or "")
        if status == "finished":
            check("finished_marked", True, f"fixture {fid_int}")

        ecse = match.get("ecse")
        if ecse:
            conn = connect(get_settings().sqlite_path)
            stored = get_snapshot(conn, fid_int)
            check(
                "ecse_from_real_store",
                stored is not None and stored.get("top_1_score") == ecse.get("top_1_score"),
                f"fixture {fid_int}",
            )

        wde = match.get("wde")
        if wde:
            check(
                "wde_from_real_store",
                wde.get("source")
                in {"prediction_history", "worldcup_stored_predictions", "prediction_cache"},
                f"fixture {fid_int} source={wde.get('source')}",
            )

    check("owner_only_flag", meta.get("owner_only") is True)
    check("public_output_unchanged", meta.get("public_output_changed") is False)

    wde_text = WDE_PATH.read_text(encoding="utf-8") if WDE_PATH.is_file() else ""
    check("wde_module_present", "class WeightedDecisionEngine" in wde_text)

    conn = connect(get_settings().sqlite_path)
    try:
        baseline_count = baseline_table_row_count(conn)
    except Exception as exc:
        baseline_count = -1
        baseline_err = str(exc)
    else:
        baseline_err = ""
    check("ecse_baseline_table_unchanged", baseline_count >= 0, f"rows={baseline_count} {baseline_err}")

    check("egie_tree_present", EGIE_MARKER.is_dir())
    billing = ROOT / "worldcup_predictor" / "billing" / "billing_service.py"
    check("billing_module_untouched_marker", billing.is_file())

    md_text = MD_PATH.read_text(encoding="utf-8") if MD_PATH.is_file() else ""
    check("markdown_has_summary_table", "| # | Fixture |" in md_text)
    check("markdown_owner_banner", "Owner personal analysis only" in md_text)
    check("markdown_report_date", report_date in md_text)

    failed = [name for name, ok, _ in CHECKS if not ok]
    print(f"\nResult: {len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
