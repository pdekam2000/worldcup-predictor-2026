"""OddAlerts dashboard CSV request planning and optional Playwright submission."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PHASE = "ODDALERTS-CSV-COMPLETE-COVERAGE-1"
PLAN_PATH = Path("config/oddalerts_csv_request_plan.json")
QUEUE_PATH = Path("artifacts/oddalerts_ecse_complete_csv_request_queue.json")
SUBMITTED_PATH = Path("artifacts/oddalerts_ecse_complete_csv_submitted.jsonl")
RANGE_TEST_PATH = Path("artifacts/oddalerts_probability_range_ui_test.json")
READINESS_PATH = Path("artifacts/oddalerts_ecse_complete_coverage_readiness.json")
BASELINE_ECSE_PATH = Path("artifacts/oddalerts_policy_ecse_readiness_20260630.json")

ECSE_REQUIRED_KEYS = frozenset(
    {
        "match_result_home",
        "match_result_draw",
        "match_result_away",
        "goals_over_2_5",
        "goals_under_2_5",
        "btts_yes",
        "btts_no",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_request_plan(path: Path | None = None) -> dict[str, Any]:
    p = path or PLAN_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def request_id(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def split_date_windows(
    start: str,
    end: str,
    *,
    max_months: int = 6,
) -> list[dict[str, str]]:
    """Split [start, end] into chunks of at most max_months calendar months."""

    def add_months(d: date, months: int) -> date:
        y = d.year + (d.month - 1 + months) // 12
        m = (d.month - 1 + months) % 12 + 1
        return date(y, m, min(d.day, 28))

    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    windows: list[dict[str, str]] = []
    cur = s
    while cur <= e:
        nxt = add_months(cur, max_months)
        chunk_end = min(e, nxt - timedelta(days=1))
        windows.append({"start": cur.isoformat(), "end": chunk_end.isoformat()})
        cur = chunk_end + timedelta(days=1)
    return windows


def build_ecse_complete_request_queue(
    plan: dict[str, Any] | None = None,
    *,
    bookmakers: list[str] | None = None,
    probability_min: int | None = None,
    probability_max: int | None = None,
) -> dict[str, Any]:
    plan = plan or load_request_plan()
    ecse = plan.get("ecse_complete_coverage") or {}
    prob_min = probability_min if probability_min is not None else int(ecse.get("probability_min", 0))
    prob_max = probability_max if probability_max is not None else int(ecse.get("probability_max", 100))
    bms = bookmakers or ecse.get("bookmakers") or plan.get("bookmakers_ecse_default") or []
    date_windows = plan.get("date_windows_historical") or []

    requests: list[dict[str, Any]] = []
    for window in date_windows:
        for market_block in ecse.get("markets") or []:
            export_market = market_block.get("export_market")
            for outcome in market_block.get("outcomes") or []:
                payload = {
                    "export_market": export_market,
                    "export_outcome": outcome.get("export_outcome"),
                    "normalized_key": outcome.get("normalized_key"),
                    "date_start": window.get("start"),
                    "date_end": window.get("end"),
                    "date_label": window.get("label"),
                    "probability_min_pct": prob_min,
                    "probability_max_pct": prob_max,
                    "bookmakers": sorted(bms),
                    "coverage_tag": ecse.get("coverage_tag", "ecse_complete"),
                }
                rid = request_id(payload)
                requests.append({"request_id": rid, **payload, "status": "queued"})

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "coverage_tag": ecse.get("coverage_tag", "ecse_complete"),
        "probability_range": f"{prob_min}% - {prob_max}%",
        "request_count": len(requests),
        "requests": requests,
    }


def load_submitted_ids(path: Path | None = None) -> set[str]:
    p = path or SUBMITTED_PATH
    if not p.is_file():
        return set()
    ids: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row.get("request_id"):
                ids.add(row["request_id"])
        except json.JSONDecodeError:
            continue
    return ids


def append_submitted(record: dict[str, Any], path: Path | None = None) -> None:
    p = path or SUBMITTED_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _parse_range_min_pct(probability_range: str) -> int | None:
    pr = (probability_range or "").strip()
    if not pr:
        return None
    head = pr.split("-", 1)[0].strip().replace("%", "").strip()
    try:
        return int(float(head))
    except ValueError:
        return None


def analyze_probability_ranges_from_gmail_summary(summary_path: Path) -> dict[str, Any]:
    if not summary_path.is_file():
        return {"ranges_found": {}, "partial_50_100_only": None, "full_coverage_exports": 0}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ranges: dict[str, int] = {}
    full = 0
    partial = 0
    for rec in summary.get("records") or []:
        pr = (rec.get("probability_range") or "unknown").strip()
        ranges[pr] = ranges.get(pr, 0) + 1
        min_pct = _parse_range_min_pct(pr)
        if min_pct is None:
            continue
        if min_pct >= 50:
            partial += 1
        else:
            full += 1
    return {
        "ranges_found": ranges,
        "partial_50_100_only": partial,
        "full_coverage_exports": full,
        "emails_found": summary.get("emails_found", 0),
    }


def load_baseline_ecse_readiness(path: Path | None = None) -> dict[str, Any]:
    p = path or BASELINE_ECSE_PATH
    if not p.is_file():
        return {"ready_full_count": 0, "ready_partial_count": 0, "status_counts": {}}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        "ready_full_count": data.get("ready_full_count", 0),
        "ready_partial_count": data.get("ready_partial_count", 0),
        "status_counts": data.get("status_counts", {}),
        "source": str(p),
    }


def build_coverage_readiness_after_policy(conn) -> dict[str, Any]:
    from worldcup_predictor.data_import.oddalerts_bookmaker_policy import (
        build_ecse_readiness_summary,
        build_policy_market_matrix,
    )

    matrix = build_policy_market_matrix(conn)
    ecse = build_ecse_readiness_summary(matrix)

    missing_by_key: dict[str, int] = {}
    fixtures_missing: list[dict[str, Any]] = []

    for fx in matrix.get("fixtures") or []:
        ecse_r = fx.get("ecse_readiness") or {}
        missing = ecse_r.get("missing_keys") or []
        if missing:
            fixtures_missing.append(
                {
                    "fixture_id": fx.get("fixture_id"),
                    "match": fx.get("match"),
                    "missing_keys": missing,
                }
            )
        for k in missing:
            missing_by_key[k] = missing_by_key.get(k, 0) + 1

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "ready_full_count": ecse.get("ready_full_count", 0),
        "ready_partial_count": ecse.get("ready_partial_count", 0),
        "status_counts": ecse.get("status_counts", {}),
        "missing_keys_aggregate": missing_by_key,
        "fixtures_with_missing_keys_sample": fixtures_missing[:30],
        "fixture_count": matrix.get("fixture_count", 0),
    }


def compare_readiness_before_after(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ready_full_before": before.get("ready_full_count", 0),
        "ready_full_after": after.get("ready_full_count", 0),
        "ready_partial_before": before.get("ready_partial_count", 0),
        "ready_partial_after": after.get("ready_partial_count", 0),
        "delta_ready_full": after.get("ready_full_count", 0) - before.get("ready_full_count", 0),
        "improved": after.get("ready_full_count", 0) > before.get("ready_full_count", 0),
    }


def final_coverage_recommendation(
    *,
    range_test: dict[str, Any],
    queue: dict[str, Any],
    submitted_count: int,
    comparison: dict[str, Any],
    range_analysis: dict[str, Any],
    after: dict[str, Any],
) -> str:
    accepted = range_test.get("accepted_ranges") or []
    has_full_range = any(r.get("label") in ("0_to_100", "1_to_100") and r.get("accepted") for r in accepted)

    if range_test.get("dashboard_rejects_full_range"):
        return "DASHBOARD_REJECTS_FULL_RANGE"

    if not has_full_range and range_test.get("playwright_available") and not range_test.get("manual_only"):
        if any(r.get("accepted") for r in accepted if "50" in r.get("label", "")):
            return "NEED_LOWER_PROBABILITY_BAND_EXPORTS"

    if after.get("ready_full_count", 0) > 0 and comparison.get("improved"):
        return "READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN"

    if after.get("ready_full_count", 0) > 0:
        return "ODDALERTS_COMPLETE_COVERAGE_READY"

    if submitted_count == 0 and queue.get("request_count", 0) > 0:
        if range_analysis.get("partial_50_100_only", 0) > 0 and range_analysis.get("full_coverage_exports", 0) == 0:
            return "NEED_LOWER_PROBABILITY_BAND_EXPORTS"
        return "DO_NOT_PROMOTE_YET"

    return "STILL_NO_ECSE_READY_FIXTURES"


def run_probability_range_ui_test(
    plan: dict[str, Any] | None = None,
    *,
    headed: bool = False,
    pause_for_login: bool = False,
) -> dict[str, Any]:
    plan = plan or load_request_plan()
    tests = plan.get("probability_range_ui_tests") or []
    result: dict[str, Any] = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "playwright_available": False,
        "manual_only": True,
        "dashboard_url": plan.get("dashboard_url"),
        "tests_run": [],
        "accepted_ranges": [],
        "dashboard_rejects_full_range": False,
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["error"] = "playwright not installed — run: pip install playwright && playwright install chromium"
        for t in tests:
            result["tests_run"].append({**t, "accepted": None, "status": "skipped_no_playwright"})
        result["manual_checklist"] = [
            "Log into OddAlerts dashboard export page",
            "Try probability min=0 max=100 — note if UI accepts",
            "If min=0 rejected, try min=1 max=100",
            "If min still rejected at 50, submit paired bands 0-50 and 50-100",
        ]
        return result

    result["playwright_available"] = True
    result["manual_only"] = False
    url = plan.get("dashboard_url", "https://oddalerts.com")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if pause_for_login:
            page.pause()

        for t in tests:
            entry = {**t, "accepted": None, "status": "manual_validation_required"}
            try:
                min_sel = page.locator('input[name*="min" i], input[id*="min" i], input[placeholder*="min" i]').first
                max_sel = page.locator('input[name*="max" i], input[id*="max" i], input[placeholder*="max" i]').first
                if min_sel.count() and max_sel.count():
                    min_sel.fill(str(t["min_pct"]))
                    max_sel.fill(str(t["max_pct"]))
                    invalid = page.locator(".error, .invalid, [aria-invalid='true']").count()
                    entry["accepted"] = invalid == 0
                    entry["status"] = "tested_input_fill"
                else:
                    entry["status"] = "selectors_not_found"
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = str(exc)[:200]
            result["tests_run"].append(entry)
            if entry.get("accepted"):
                result["accepted_ranges"].append(entry)

        browser.close()

    if result["accepted_ranges"]:
        labels = {r.get("label") for r in result["accepted_ranges"]}
        result["dashboard_rejects_full_range"] = "0_to_100" not in labels and "1_to_100" not in labels

    return result


def write_coverage_readiness_artifact(conn, *, before: dict | None = None) -> dict:
    before = before or load_baseline_ecse_readiness()
    after = build_coverage_readiness_after_policy(conn)
    comparison = compare_readiness_before_after(before, after)
    payload = {
        **after,
        "baseline": before,
        "comparison": comparison,
    }
    READINESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    READINESS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def submit_ecse_requests(
    queue: dict[str, Any],
    plan: dict[str, Any] | None = None,
    *,
    dry_run: bool = True,
    headed: bool = False,
    pause_for_login: bool = False,
    max_requests: int = 50,
    delay_seconds: float | None = None,
) -> dict[str, Any]:
    plan = plan or load_request_plan()
    delay = delay_seconds if delay_seconds is not None else float(plan.get("request_delay_seconds", 3.0))
    submitted_ids = load_submitted_ids()
    stats = {"queued": 0, "skipped_duplicate": 0, "submitted": 0, "failed": 0, "dry_run": dry_run}

    pending = [r for r in queue.get("requests") or [] if r.get("request_id") not in submitted_ids]
    pending = pending[:max_requests]

    if dry_run:
        stats["queued"] = len(pending)
        return stats

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        stats["error"] = "playwright required for live submit — use --dry-run to generate queue only"
        stats["queued"] = len(pending)
        return stats

    url = plan.get("dashboard_url", "https://oddalerts.com")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if pause_for_login:
            page.pause()

        for req in pending:
            stats["queued"] += 1
            try:
                page.pause()
                record = {
                    "request_id": req["request_id"],
                    "submitted_at_utc": _utc_now(),
                    "status": "submitted_manual_confirm",
                    "export_market": req.get("export_market"),
                    "export_outcome": req.get("export_outcome"),
                    "probability_range": f"{req.get('probability_min_pct')}% - {req.get('probability_max_pct')}%",
                }
                append_submitted(record)
                stats["submitted"] += 1
            except Exception as exc:
                stats["failed"] += 1
                append_submitted(
                    {
                        "request_id": req["request_id"],
                        "submitted_at_utc": _utc_now(),
                        "status": "failed",
                        "error": str(exc)[:300],
                    }
                )
            time.sleep(delay)

        browser.close()

    return stats
