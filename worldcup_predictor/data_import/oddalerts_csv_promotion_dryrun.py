"""OddAlerts CSV → odds_snapshots promotion dry-run (owner/internal)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import parse_snapshot_payload
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import (
    ECSE_REQUIRED_KEYS,
    PHASE as POLICY_PHASE,
    PROCESS_DATE,
    load_policy_config,
)

PHASE = "ODDALERTS-CSV-PROMOTION-2"
SOURCE_PROVIDER = "oddalerts_csv_policy"
SOURCE_DETAIL = "lower_band_complete_coverage"
REPORT_PATH = Path("ODDALERTS_CSV_PROMOTION_DRYRUN_REPORT.md")

ECSE_MARKET_GROUPS = {
    "1x2": ("match_result_home", "match_result_draw", "match_result_away"),
    "over_under_2_5": ("goals_over_2_5", "goals_under_2_5"),
    "btts": ("btts_yes", "btts_no"),
}

OPTIONAL_MARKET_PREFIXES = (
    "goals_over_1_5",
    "goals_under_1_5",
    "goals_over_3_5",
    "goals_under_3_5",
    "goals_over_4_5",
    "goals_under_4_5",
    "double_chance_",
    "first_half_",
    "corners_",
)

PROVIDER_SOURCES = frozenset(
    {
        "live",
        "cache",
        "api_football",
        "api-football",
        "sportmonks",
        "the_odds_api",
        "odds_api",
    }
)

NON_PROVIDER_PLACEHOLDER_SOURCES = frozenset({"api_gap_cache_import", "gap_cache", "placeholder"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _date_tag(process_date: str | None = None) -> str:
    return (process_date or PROCESS_DATE).replace("-", "")


def artifact_paths(process_date: str | None = None) -> dict[str, Path]:
    tag = _date_tag(process_date)
    return {
        "matrix": Path(f"artifacts/oddalerts_policy_market_matrix_{tag}.json"),
        "ecse_readiness": Path(f"artifacts/oddalerts_policy_ecse_readiness_{tag}.json"),
        "policy_preview": Path(f"artifacts/oddalerts_policy_odds_snapshot_preview_{tag}.json"),
        "dual_band_coverage": Path(f"artifacts/oddalerts_lower_band_ecse_market_coverage_{tag}.json"),
        "dryrun_out": Path(f"artifacts/oddalerts_csv_odds_snapshot_promotion_dryrun_{tag}.json"),
        "validation_out": Path(f"artifacts/oddalerts_csv_promotion_dryrun_validation_{tag}.json"),
    }


def _parse_snapshot_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S UTC",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(value.replace("Z", ""), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _payload_source(payload: dict[str, Any]) -> str:
    for key in ("source_provider", "source", "provider"):
        val = payload.get(key)
        if val:
            return str(val).lower()
    return "unknown"


def _has_provider_bookmaker_data(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    api = payload.get("api_sports") or {}
    if isinstance(api, dict):
        bms = api.get("bookmakers") or []
        if any(isinstance(b, dict) and b.get("bets") for b in bms):
            return True
    bms = payload.get("bookmakers") or []
    if any(isinstance(b, dict) and b.get("bets") for b in bms):
        return True
    if payload.get("sportmonks") or payload.get("response"):
        return True
    return False


def _existing_market_coverage(parsed: dict[str, Any]) -> dict[str, bool]:
    return {
        "1x2": all(parsed.get(k) is not None for k in ("odds_implied_home", "odds_implied_draw", "odds_implied_away")),
        "over_under_2_5": all(
            parsed.get(k) is not None for k in ("odds_implied_over_25", "odds_implied_under_25")
        ),
        "btts": all(parsed.get(k) is not None for k in ("odds_implied_btts_yes", "odds_implied_btts_no")),
    }


def _ecse_complete(coverage: dict[str, bool]) -> bool:
    return all(coverage.values())


def classify_existing_snapshot(
    *,
    fixture_id: int,
    snapshot_at: str,
    payload: dict[str, Any],
    oddalerts_reference_time: datetime,
) -> dict[str, Any]:
    source = _payload_source(payload)
    parsed = parse_snapshot_payload(payload, fixture_id=fixture_id, captured_at=snapshot_at)
    coverage = _existing_market_coverage(parsed)
    has_provider_data = _has_provider_bookmaker_data(payload)
    is_placeholder = source in NON_PROVIDER_PLACEHOLDER_SOURCES and not has_provider_data
    is_provider_backed = has_provider_data or source in PROVIDER_SOURCES

    snap_time = _parse_snapshot_time(snapshot_at) or _parse_snapshot_time(str(payload.get("snapshot_at") or ""))
    fresher_than_oddalerts = bool(snap_time and snap_time >= oddalerts_reference_time)

    return {
        "snapshot_at": snapshot_at,
        "source": source,
        "is_provider_backed": is_provider_backed,
        "is_placeholder": is_placeholder,
        "market_coverage": coverage,
        "ecse_complete": _ecse_complete(coverage),
        "fresher_than_oddalerts": fresher_than_oddalerts,
        "parsed_implied_probs_present": sum(1 for v in parsed.values() if v is not None),
    }


def classify_promotion_action(
    *,
    existing_snapshots: list[dict[str, Any]],
    oddalerts_reference_time: datetime,
) -> tuple[str, dict[str, Any]]:
    if not existing_snapshots:
        return "WOULD_INSERT", {"reason": "no_existing_snapshot"}

    latest = existing_snapshots[-1]
    info = classify_existing_snapshot(
        fixture_id=int(latest.get("fixture_id") or 0),
        snapshot_at=str(latest.get("snapshot_at") or ""),
        payload=latest.get("payload") or {},
        oddalerts_reference_time=oddalerts_reference_time,
    )

    if info["is_provider_backed"] and info["ecse_complete"] and info["fresher_than_oddalerts"]:
        return "SKIP_EXISTING_FRESH", {"reason": "provider_snapshot_complete_and_fresher", **info}

    if info["is_provider_backed"] and info["ecse_complete"] and not info["fresher_than_oddalerts"]:
        return "CONFLICT_REVIEW", {"reason": "provider_complete_but_older_than_oddalerts", **info}

    if info["is_provider_backed"] and not info["ecse_complete"]:
        return "WOULD_ENRICH", {"reason": "provider_partial_coverage", **info}

    if info["is_placeholder"] or not info["ecse_complete"]:
        return "WOULD_ENRICH", {"reason": "placeholder_or_incomplete_existing", **info}

    if info["is_provider_backed"]:
        return "CONFLICT_REVIEW", {"reason": "provider_backed_ambiguous", **info}

    return "WOULD_INSERT", {"reason": "non_provider_existing_replaceable", **info}


def _build_markets_block(normalized_probs: dict[str, float | None]) -> dict[str, Any]:
    markets: dict[str, Any] = {
        "1x2": {
            "home": normalized_probs.get("match_result_home"),
            "draw": normalized_probs.get("match_result_draw"),
            "away": normalized_probs.get("match_result_away"),
        },
        "over_under_2_5": {
            "over": normalized_probs.get("goals_over_2_5"),
            "under": normalized_probs.get("goals_under_2_5"),
        },
        "btts": {
            "yes": normalized_probs.get("btts_yes"),
            "no": normalized_probs.get("btts_no"),
        },
    }
    optional: dict[str, float | None] = {}
    for key, val in normalized_probs.items():
        if key in ECSE_REQUIRED_KEYS or val is None:
            continue
        if any(key.startswith(p) if p.endswith("_") else key == p for p in OPTIONAL_MARKET_PREFIXES):
            optional[key] = val
    if optional:
        markets["optional"] = optional
    return markets


def build_snapshot_payload(
    *,
    fixture_id: int,
    competition_key: str | None,
    snapshot_time: str,
    policy_version: str,
    normalized_probs: dict[str, float | None],
    matrix_fixture: dict[str, Any],
    preview_entry: dict[str, Any],
    crosswalk_confidence: str,
    probability_band_coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    markets = matrix_fixture.get("markets") or []
    all_methods = sorted({m.get("selected_method") for m in markets if m.get("selected_method")})
    all_bookmakers = sorted({bm for m in markets for bm in (m.get("source_bookmakers") or [])})
    row_hashes = sorted({h for m in markets for h in (m.get("source_row_hashes") or [])})
    source_files = sorted({f for m in markets for f in (m.get("source_files") or [])})

    ecse_keys = sorted(k for k in normalized_probs if k in ECSE_REQUIRED_KEYS)
    missing_ecse = sorted(ECSE_REQUIRED_KEYS - set(ecse_keys))

    return {
        "fixture_id": fixture_id,
        "competition_key": competition_key,
        "snapshot_time": snapshot_time,
        "source_provider": SOURCE_PROVIDER,
        "source_detail": SOURCE_DETAIL,
        "policy_version": policy_version,
        "markets": _build_markets_block(normalized_probs),
        "normalized_probabilities": {k: v for k, v in normalized_probs.items() if v is not None},
        "metadata": {
            "bookmaker_count_avg": preview_entry.get("bookmaker_count_avg"),
            "selected_methods": all_methods or preview_entry.get("selected_methods") or [],
            "source_bookmakers": all_bookmakers,
            "source_row_hashes": row_hashes,
            "source_files": source_files,
            "probability_band_coverage": probability_band_coverage or {},
            "normalization_warnings": (matrix_fixture.get("ecse_readiness") or {}).get("consistency_warnings") or preview_entry.get("warnings") or [],
            "market_completeness": {
                "ecse_required_complete": not missing_ecse,
                "ecse_keys_present": ecse_keys,
                "ecse_keys_missing": missing_ecse,
                "total_markets": len(normalized_probs),
            },
            "crosswalk_confidence": crosswalk_confidence,
        },
        "payload_json_preview": {
            "snapshot_at": snapshot_time,
            "source_provider": SOURCE_PROVIDER,
            "source_detail": SOURCE_DETAIL,
            "policy_version": policy_version,
            "oddalerts_csv_policy": {
                "probabilities_pct": {k: v for k, v in normalized_probs.items() if v is not None},
                "metadata": {
                    "bookmaker_count_avg": preview_entry.get("bookmaker_count_avg"),
                    "selected_methods": all_methods,
                    "source_row_hash_count": len(row_hashes),
                    "source_file_count": len(source_files),
                },
            },
        },
    }


def _load_crosswalk_confidence(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, str]:
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" * len(fixture_ids))
    sql = f"""
        SELECT internal_fixture_id, fixture_match_status, COUNT(*) c
        FROM oddalerts_probability_market_rows
        WHERE internal_fixture_id IN ({placeholders})
        GROUP BY internal_fixture_id, fixture_match_status
    """
    by_fx: dict[int, dict[str, int]] = {}
    for row in conn.execute(sql, fixture_ids).fetchall():
        fid = int(row["internal_fixture_id"])
        by_fx.setdefault(fid, {})[str(row["fixture_match_status"])] = int(row["c"])

    out: dict[int, str] = {}
    for fid, statuses in by_fx.items():
        if statuses.get("MATCHED_HIGH_CONFIDENCE"):
            out[fid] = "MATCHED_HIGH_CONFIDENCE"
        elif statuses.get("MATCHED"):
            out[fid] = "MATCHED"
        else:
            out[fid] = next(iter(statuses.keys()), "UNKNOWN")
    return out


def _fetch_existing_snapshots(conn: sqlite3.Connection, fixture_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT snapshot_at, payload_json, competition_key
        FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY snapshot_at ASC
        """,
        (int(fixture_id),),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
        result.append(
            {
                "fixture_id": fixture_id,
                "snapshot_at": row["snapshot_at"],
                "competition_key": row["competition_key"],
                "payload": payload,
            }
        )
    return result


def run_promotion_dryrun(
    conn: sqlite3.Connection,
    *,
    matrix: dict[str, Any] | None = None,
    ecse_readiness: dict[str, Any] | None = None,
    policy_preview: dict[str, Any] | None = None,
    dual_band_coverage: dict[str, Any] | None = None,
    process_date: str | None = None,
    sample_limit: int = 10,
) -> dict[str, Any]:
    paths = artifact_paths(process_date)
    matrix = matrix or json.loads(paths["matrix"].read_text(encoding="utf-8"))
    ecse_readiness = ecse_readiness or json.loads(paths["ecse_readiness"].read_text(encoding="utf-8"))
    policy_preview = policy_preview or json.loads(paths["policy_preview"].read_text(encoding="utf-8"))
    if dual_band_coverage is None and paths["dual_band_coverage"].exists():
        dual_band_coverage = json.loads(paths["dual_band_coverage"].read_text(encoding="utf-8"))

    cfg = load_policy_config()
    policy_version = matrix.get("policy_version") or cfg.get("version") or PROCESS_DATE
    snapshot_time = _utc_now()
    ref_time = _parse_snapshot_time(matrix.get("generated_at_utc")) or datetime.now(timezone.utc)

    ready_full_ids = {
        int(fx["fixture_id"])
        for fx in matrix.get("fixtures") or []
        if (fx.get("ecse_readiness") or {}).get("status") == "READY_FULL"
    }
    ready_full_fixture_count = int(ecse_readiness.get("ready_full_count", len(ready_full_ids)))

    preview_by_id = {
        int(p["fixture_id"]): p
        for p in (policy_preview.get("previews") or [])
        if p.get("fixture_id") is not None
    }
    matrix_by_id = {
        int(fx["fixture_id"]): fx for fx in (matrix.get("fixtures") or []) if fx.get("fixture_id") is not None
    }

    crosswalk = _load_crosswalk_confidence(conn, sorted(ready_full_ids))

    counts = {
        "candidate_count": 0,
        "would_insert_count": 0,
        "would_enrich_count": 0,
        "skipped_existing_fresh_count": 0,
        "conflict_review_count": 0,
        "skipped_not_ready_count": 0,
    }
    candidates: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for fx in matrix.get("fixtures") or []:
        fixture_id = int(fx["fixture_id"])
        ecse = fx.get("ecse_readiness") or {}
        status = ecse.get("status")
        preview = preview_by_id.get(fixture_id)

        if status != "READY_FULL":
            counts["skipped_not_ready_count"] += 1
            if preview and preview.get("blocker_reason"):
                blockers.append(
                    {
                        "fixture_id": fixture_id,
                        "match": fx.get("match"),
                        "reason": preview.get("blocker_reason") or status,
                    }
                )
            continue

        counts["candidate_count"] += 1
        if not preview:
            blockers.append({"fixture_id": fixture_id, "match": fx.get("match"), "reason": "PREVIEW_MISSING"})
            continue

        normalized_probs = {
            k: float(v) for k, v in (preview.get("normalized_probabilities") or {}).items() if v is not None
        }
        missing = sorted(ECSE_REQUIRED_KEYS - set(normalized_probs))
        if missing:
            blockers.append(
                {"fixture_id": fixture_id, "match": fx.get("match"), "reason": "ECSE_MARKETS_INCOMPLETE", "missing": missing}
            )
            continue

        if crosswalk.get(fixture_id) != "MATCHED_HIGH_CONFIDENCE":
            blockers.append(
                {
                    "fixture_id": fixture_id,
                    "match": fx.get("match"),
                    "reason": "CROSSWALK_NOT_HIGH_CONFIDENCE",
                    "crosswalk_confidence": crosswalk.get(fixture_id),
                }
            )
            continue

        existing = _fetch_existing_snapshots(conn, fixture_id)
        action, action_detail = classify_promotion_action(
            existing_snapshots=existing,
            oddalerts_reference_time=ref_time,
        )

        if action == "WOULD_INSERT":
            counts["would_insert_count"] += 1
        elif action == "WOULD_ENRICH":
            counts["would_enrich_count"] += 1
        elif action == "SKIP_EXISTING_FRESH":
            counts["skipped_existing_fresh_count"] += 1
        elif action == "CONFLICT_REVIEW":
            counts["conflict_review_count"] += 1

        payload = build_snapshot_payload(
            fixture_id=fixture_id,
            competition_key=fx.get("competition_key"),
            snapshot_time=snapshot_time,
            policy_version=policy_version,
            normalized_probs=normalized_probs,
            matrix_fixture=fx,
            preview_entry=preview,
            crosswalk_confidence=crosswalk.get(fixture_id, "MATCHED_HIGH_CONFIDENCE"),
            probability_band_coverage={
                "phase": (dual_band_coverage or {}).get("phase"),
                "all_complete": (dual_band_coverage or {}).get("all_complete"),
            },
        )

        entry = {
            "fixture_id": fixture_id,
            "match": fx.get("match"),
            "competition_key": fx.get("competition_key"),
            "kickoff": fx.get("kickoff"),
            "promotion_action": action,
            "action_detail": action_detail,
            "ecse_readiness_status": status,
            "existing_snapshot_count": len(existing),
            "snapshot_payload_preview": payload,
        }
        candidates.append(entry)
        if len(samples) < sample_limit and action in ("WOULD_INSERT", "WOULD_ENRICH"):
            samples.append(entry)

    result = {
        "phase": PHASE,
        "generated_at_utc": snapshot_time,
        "date_processed": process_date or PROCESS_DATE,
        "policy_version": policy_version,
        "source_provider": SOURCE_PROVIDER,
        "source_detail": SOURCE_DETAIL,
        "ready_full_fixture_count": ready_full_fixture_count,
        "dry_run_only": True,
        "writes_odds_snapshots": False,
        **counts,
        "sample_payloads": samples,
        "blockers": blockers[:100],
        "candidates": candidates,
    }
    return result


def promotion_final_recommendation(result: dict[str, Any]) -> str:
    candidates = result.get("candidate_count", 0)
    if candidates == 0:
        return "NO_PROMOTION_CANDIDATES"

    conflicts = int(result.get("conflict_review_count", 0))
    if conflicts > max(candidates * 0.1, 5):
        return "CONFLICT_REVIEW_REQUIRED"

    promotable = int(result.get("would_insert_count", 0)) + int(result.get("would_enrich_count", 0))
    if promotable == 0:
        if int(result.get("skipped_existing_fresh_count", 0)) > 0:
            return "DO_NOT_PROMOTE_YET"
        return "NO_PROMOTION_CANDIDATES"

    if conflicts > 0:
        return "CONFLICT_REVIEW_REQUIRED"

    if promotable >= int(result.get("ready_full_fixture_count", 0)) * 0.8:
        return "READY_FOR_ODDS_SNAPSHOT_WRITE"

    if promotable > 0:
        return "ODDALERTS_ODDS_PROMOTION_DRYRUN_READY"

    return "DO_NOT_PROMOTE_YET"


def build_report_markdown(result: dict[str, Any], validation: dict[str, Any] | None = None) -> str:
    validation = validation or {}
    rec = result.get("final_recommendation") or promotion_final_recommendation(result)
    samples = result.get("sample_payloads") or []

    sample_lines = []
    for s in samples[:8]:
        payload = s.get("snapshot_payload_preview") or {}
        mkts = payload.get("markets") or {}
        sample_lines.append(
            f"| {s.get('fixture_id')} | {s.get('match', '')[:40]} | {s.get('promotion_action')} | "
            f"{len(mkts.get('optional') or {})} optional |"
        )

    action_summary = (
        f"- **Would insert:** {result.get('would_insert_count', 0)}\n"
        f"- **Would enrich:** {result.get('would_enrich_count', 0)}\n"
        f"- **Skipped (existing fresh):** {result.get('skipped_existing_fresh_count', 0)}\n"
        f"- **Conflict review:** {result.get('conflict_review_count', 0)}\n"
        f"- **Skipped (not READY_FULL):** {result.get('skipped_not_ready_count', 0)}"
    )

    val_lines = []
    for c in (validation.get("checks") or []):
        mark = "pass" if c.get("passed") else "FAIL"
        val_lines.append(f"- [{mark}] {c.get('check')}: {c.get('detail', '')}")

    return f"""# OddAlerts CSV Promotion Dry-Run Report

**Phase:** {PHASE}  
**Date:** {result.get('date_processed', PROCESS_DATE)}  
**Generated:** {result.get('generated_at_utc', _utc_now())}  
**Mode:** Owner/internal dry-run — no odds_snapshots writes, no ECSE/WDE generation

---

## Summary

Strict dry-run preview of promoting OddAlerts CSV policy-selected probabilities into `odds_snapshots` for **READY_FULL** fixtures only.

**Final recommendation:** `{rec}`

---

## Part A — Candidate counts

| Metric | Value |
|--------|-------|
| READY_FULL fixtures | {result.get('ready_full_fixture_count', 0)} |
| Candidates previewed | {result.get('candidate_count', 0)} |
| Would insert | {result.get('would_insert_count', 0)} |
| Would enrich | {result.get('would_enrich_count', 0)} |
| Skipped (existing fresh) | {result.get('skipped_existing_fresh_count', 0)} |
| Conflict review | {result.get('conflict_review_count', 0)} |
| Skipped (not READY_FULL) | {result.get('skipped_not_ready_count', 0)} |

{action_summary}

**Artifact:** `artifacts/oddalerts_csv_odds_snapshot_promotion_dryrun_{_date_tag(result.get('date_processed'))}.json`

---

## Part B — Sample fixtures

| Fixture ID | Match | Action | Optional markets |
|------------|-------|--------|------------------|
{chr(10).join(sample_lines) if sample_lines else '| — | — | — | — |'}

---

## Part C — Market completeness

All READY_FULL candidates require complete ECSE markets:

- match_result_home / draw / away
- goals_over_2_5 / goals_under_2_5
- btts_yes / btts_no

Dual-band coverage artifact referenced: `artifacts/oddalerts_lower_band_ecse_market_coverage_{_date_tag(result.get('date_processed'))}.json`

Blockers logged: **{len(result.get('blockers') or [])}**

---

## Part D — Validation

{chr(10).join(val_lines) if val_lines else '- Validation artifact not loaded'}

Checks passed: **{validation.get('passed', '?')}/{validation.get('passed', 0) + validation.get('failed', 0)}**

---

## Part E — Write phase

This run did **not** write to `odds_snapshots`. A separate explicit `--write` phase is required for promotion.

Policy version: `{result.get('policy_version')}`  
Source: `{SOURCE_PROVIDER}` / `{SOURCE_DETAIL}`
"""
