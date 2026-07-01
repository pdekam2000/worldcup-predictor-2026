"""OddAlerts bookmaker selection + consensus policy engine (dry-run)."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE = "ODDALERTS-BOOKMAKER-POLICY-1"
POLICY_CONFIG_PATH = Path("config/oddalerts_bookmaker_policy.json")
PROCESS_DATE = "2026-06-30"

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


def load_policy_config(path: Path | None = None) -> dict[str, Any]:
    p = path or POLICY_CONFIG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _valid_probability(value: Any) -> float | None:
    if value is None:
        return None
    try:
        p = float(value)
    except (TypeError, ValueError):
        return None
    if p <= 0 or p > 100:
        return None
    return round(p, 6)


@dataclass
class BookmakerRow:
    row_hash: str
    source_file: str
    bookmaker: str
    model_probability: float
    opening_odds: float | None = None
    closing_odds: float | None = None
    peak_odds: float | None = None


@dataclass
class PolicySelectionResult:
    fixture_id: int | None
    fixture_name: str
    kickoff_time: str | None
    normalized_market_key: str
    bookmaker_count: int = 0
    available_bookmakers: list[str] = field(default_factory=list)
    priority_bookmaker_available: str | None = None
    average_probability: float | None = None
    median_probability: float | None = None
    min_probability: float | None = None
    max_probability: float | None = None
    probability_spread: float | None = None
    selected_probability: float | None = None
    selected_method: str | None = None
    selected_bookmaker: str | None = None
    disagreement_flag: bool = False
    blocked: bool = False
    block_reason: str | None = None
    source_row_hashes: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    probability_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "fixture_name": self.fixture_name,
            "kickoff_time": self.kickoff_time,
            "normalized_market_key": self.normalized_market_key,
            "bookmaker_count": self.bookmaker_count,
            "available_bookmakers": self.available_bookmakers,
            "priority_bookmaker_available": self.priority_bookmaker_available,
            "average_probability": self.average_probability,
            "median_probability": self.median_probability,
            "min_probability": self.min_probability,
            "max_probability": self.max_probability,
            "probability_spread": self.probability_spread,
            "selected_probability": self.selected_probability,
            "selected_method": self.selected_method,
            "selected_bookmaker": self.selected_bookmaker,
            "disagreement_flag": self.disagreement_flag,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "source_row_hashes": self.source_row_hashes,
            "source_files": sorted(set(self.source_files)),
            "probability_valid": self.probability_valid,
        }


def _priority_bookmaker(rows: list[BookmakerRow], priority: list[str]) -> BookmakerRow | None:
    by_name = {r.bookmaker: r for r in rows}
    for name in priority:
        if name in by_name:
            return by_name[name]
    return rows[0] if rows else None


def apply_bookmaker_policy(
    *,
    fixture_id: int | None,
    fixture_name: str,
    kickoff_time: str | None,
    normalized_market_key: str,
    rows: list[BookmakerRow],
    config: dict[str, Any] | None = None,
    allow_high_disagreement: bool = False,
) -> PolicySelectionResult:
    cfg = config or load_policy_config()
    ecse_cfg = cfg.get("ecse_policy") or {}
    priority = cfg.get("bookmaker_priority") or []
    threshold = float(ecse_cfg.get("disagreement_threshold_pct", cfg.get("default_disagreement_threshold_pct", 8.0)))
    min_median = int(ecse_cfg.get("min_bookmakers_for_median", 3))

    result = PolicySelectionResult(
        fixture_id=fixture_id,
        fixture_name=fixture_name,
        kickoff_time=kickoff_time,
        normalized_market_key=normalized_market_key,
    )

    valid_rows = [r for r in rows if _valid_probability(r.model_probability) is not None]
    if not valid_rows:
        result.probability_valid = False
        result.blocked = True
        result.block_reason = "PROBABILITY_INVALID"
        return result

    valid_rows.sort(key=lambda r: (priority.index(r.bookmaker) if r.bookmaker in priority else 999, r.bookmaker, r.row_hash))

    probs = [float(r.model_probability) for r in valid_rows]
    result.bookmaker_count = len(valid_rows)
    result.available_bookmakers = sorted({r.bookmaker for r in valid_rows})
    result.source_row_hashes = [r.row_hash for r in valid_rows]
    result.source_files = [r.source_file for r in valid_rows]
    result.average_probability = round(statistics.mean(probs), 6)
    result.median_probability = round(statistics.median(probs), 6)
    result.min_probability = round(min(probs), 6)
    result.max_probability = round(max(probs), 6)
    result.probability_spread = round(max(probs) - min(probs), 6)
    result.disagreement_flag = result.probability_spread > threshold

    prio_row = _priority_bookmaker(valid_rows, priority)
    result.priority_bookmaker_available = prio_row.bookmaker if prio_row else None

    if result.disagreement_flag and ecse_cfg.get("reject_high_disagreement", True) and not allow_high_disagreement:
        result.blocked = True
        result.block_reason = "HIGH_DISAGREEMENT_BLOCKED"
        return result

    if len(valid_rows) >= min_median:
        result.selected_probability = result.median_probability
        result.selected_method = "median_probability"
    elif prio_row:
        result.selected_probability = round(float(prio_row.model_probability), 6)
        result.selected_method = "priority_bookmaker"
        result.selected_bookmaker = prio_row.bookmaker
    else:
        result.blocked = True
        result.block_reason = "POLICY_ERROR"
        result.probability_valid = False

    return result


def load_grouped_rows(conn, *, high_confidence_only: bool = True) -> dict[tuple[int, str], list[BookmakerRow]]:
    where = "WHERE normalized_market_key IS NOT NULL"
    if high_confidence_only:
        where += " AND internal_fixture_id IS NOT NULL AND fixture_match_status = 'MATCHED_HIGH_CONFIDENCE'"

    sql = f"""
        SELECT internal_fixture_id, fixture_name, kickoff_time, normalized_market_key,
               bookmaker, model_probability, opening_odds, closing_odds, peak_odds,
               row_hash, source_file
        FROM oddalerts_probability_market_rows
        {where}
    """
    groups: dict[tuple[int, str], list[BookmakerRow]] = {}
    for row in conn.execute(sql).fetchall():
        fid = int(row["internal_fixture_id"])
        gkey = (fid, str(row["normalized_market_key"]))
        groups.setdefault(gkey, []).append(
            BookmakerRow(
                row_hash=row["row_hash"],
                source_file=row["source_file"],
                bookmaker=row["bookmaker"] or "unknown",
                model_probability=float(row["model_probability"]),
                opening_odds=row["opening_odds"],
                closing_odds=row["closing_odds"],
                peak_odds=row["peak_odds"],
            )
        )
    return groups


def check_probability_consistency(
    selections: dict[str, PolicySelectionResult],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_policy_config()
    norm_cfg = cfg.get("normalization") or {}
    groups_cfg = cfg.get("consistency_groups") or {
        "match_result_1x2": list(ECSE_REQUIRED_KEYS & {"match_result_home", "match_result_draw", "match_result_away"}),
        "goals_over_under_2_5": ["goals_over_2_5", "goals_under_2_5"],
        "btts": ["btts_yes", "btts_no"],
    }
    warnings: list[str] = []
    group_results: dict[str, Any] = {}

    for group_name, keys in groups_cfg.items():
        raw: dict[str, float | None] = {}
        for k in keys:
            sel = selections.get(k)
            raw[k] = sel.selected_probability if sel and not sel.blocked else None

        present = {k: v for k, v in raw.items() if v is not None}
        if len(present) < 2:
            group_results[group_name] = {
                "raw_selected": raw,
                "normalized": raw,
                "normalization_method": None,
                "model_sum": None,
                "overround_pct": None,
                "warnings": ["incomplete_group"],
            }
            continue

        model_sum = round(sum(present.values()), 6)
        overround = round(model_sum - 100.0, 6)
        normalized = dict(raw)
        norm_method = None
        group_warnings: list[str] = []

        if norm_cfg.get("enabled", True):
            lo = float(norm_cfg.get("min_raw_sum_pct", 85.0))
            hi = float(norm_cfg.get("max_raw_sum_pct", 115.0))
            if lo <= model_sum <= hi and model_sum > 0:
                scale = 100.0 / model_sum
                for k in keys:
                    if raw.get(k) is not None:
                        normalized[k] = round(raw[k] * scale, 6)
                norm_method = norm_cfg.get("method", "proportional_scale")
            else:
                group_warnings.append(f"{group_name}: sum {model_sum}% outside safe band [{lo}, {hi}]")
                warnings.append(group_warnings[-1])

        if abs(overround) > 5:
            group_warnings.append(f"{group_name}: overround {overround}%")
            warnings.append(group_warnings[-1])

        group_results[group_name] = {
            "raw_selected": raw,
            "normalized": normalized,
            "normalization_method": norm_method,
            "model_sum": model_sum,
            "overround_pct": overround,
            "warnings": group_warnings,
        }

    return {"groups": group_results, "warnings": warnings}


def assess_ecse_readiness(
    selections: dict[str, PolicySelectionResult],
    consistency: dict[str, Any],
    *,
    fixture_id: int | None,
    has_fixture_mapping: bool,
) -> dict[str, Any]:
    if not has_fixture_mapping or fixture_id is None:
        return {"status": "FIXTURE_MAPPING_MISSING", "missing_keys": sorted(ECSE_REQUIRED_KEYS), "blocked_keys": []}

    missing: list[str] = []
    blocked: list[str] = []
    invalid: list[str] = []

    for key in sorted(ECSE_REQUIRED_KEYS):
        sel = selections.get(key)
        if not sel:
            missing.append(key)
        elif not sel.probability_valid:
            invalid.append(key)
        elif sel.blocked:
            blocked.append(key)
        elif sel.selected_probability is None:
            missing.append(key)

    if invalid:
        status = "PROBABILITY_INVALID"
    elif blocked:
        status = "HIGH_DISAGREEMENT_BLOCKED"
    elif missing:
        status = "MARKET_MISSING" if len(missing) == len(ECSE_REQUIRED_KEYS) else "READY_PARTIAL"
    else:
        bad_norm = any("outside safe band" in w for w in (consistency.get("warnings") or []))
        status = "NEED_PROBABILITY_NORMALIZATION_FIX" if bad_norm else "READY_FULL"

    return {
        "status": status,
        "missing_keys": missing,
        "blocked_keys": blocked,
        "invalid_keys": invalid,
        "consistency_warnings": consistency.get("warnings") or [],
    }


def process_all_groups(
    conn,
    *,
    config: dict[str, Any] | None = None,
    allow_high_disagreement: bool = False,
    high_confidence_only: bool = True,
) -> dict[str, Any]:
    cfg = config or load_policy_config()
    grouped = load_grouped_rows(conn, high_confidence_only=high_confidence_only)

    fixture_meta: dict[int, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key FROM fixtures"
    ).fetchall():
        fixture_meta[int(row["fixture_id"])] = dict(row)

    fx_names: dict[int, tuple[str, str | None]] = {}
    for row in conn.execute(
        """
        SELECT DISTINCT internal_fixture_id, fixture_name, kickoff_time
        FROM oddalerts_probability_market_rows
        WHERE internal_fixture_id IS NOT NULL
        """
    ).fetchall():
        fx_names[int(row["internal_fixture_id"])] = (row["fixture_name"], row["kickoff_time"])

    selections_by_fixture: dict[int, dict[str, PolicySelectionResult]] = {}
    all_selections: list[PolicySelectionResult] = []
    stats = {
        "groups_processed": 0,
        "median_selected": 0,
        "priority_selected": 0,
        "blocked_disagreement": 0,
        "blocked_invalid": 0,
    }

    for (fixture_id, market_key), rows in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
        fname, kickoff = fx_names.get(fixture_id, ("", None))
        sel = apply_bookmaker_policy(
            fixture_id=fixture_id,
            fixture_name=fname,
            kickoff_time=kickoff,
            normalized_market_key=market_key,
            rows=rows,
            config=cfg,
            allow_high_disagreement=allow_high_disagreement,
        )
        stats["groups_processed"] += 1
        if sel.blocked and sel.block_reason == "HIGH_DISAGREEMENT_BLOCKED":
            stats["blocked_disagreement"] += 1
        elif sel.blocked and sel.block_reason == "PROBABILITY_INVALID":
            stats["blocked_invalid"] += 1
        elif sel.selected_method == "median_probability":
            stats["median_selected"] += 1
        elif sel.selected_method == "priority_bookmaker":
            stats["priority_selected"] += 1

        selections_by_fixture.setdefault(fixture_id, {})[market_key] = sel
        all_selections.append(sel)

    return {
        "config_version": cfg.get("version"),
        "selections_by_fixture": selections_by_fixture,
        "all_selections": all_selections,
        "stats": stats,
        "fixture_meta": fixture_meta,
        "fx_names": fx_names,
    }


def build_policy_market_matrix(
    conn,
    *,
    config: dict[str, Any] | None = None,
    allow_high_disagreement: bool = False,
) -> dict[str, Any]:
    cfg = config or load_policy_config()
    processed = process_all_groups(
        conn,
        config=cfg,
        allow_high_disagreement=allow_high_disagreement,
        high_confidence_only=True,
    )
    fixture_meta = processed["fixture_meta"]
    fixtures_out: list[dict[str, Any]] = []

    for fixture_id in sorted(processed["selections_by_fixture"].keys()):
        sels = processed["selections_by_fixture"][fixture_id]
        meta = fixture_meta.get(fixture_id, {})
        consistency = check_probability_consistency(sels, config=cfg)
        ecse = assess_ecse_readiness(sels, consistency, fixture_id=fixture_id, has_fixture_mapping=True)

        markets = []
        for mk in sorted(sels.keys()):
            s = sels[mk]
            markets.append(
                {
                    "normalized_market_key": mk,
                    "selected_probability": s.selected_probability,
                    "selected_method": s.selected_method,
                    "selected_bookmaker": s.selected_bookmaker,
                    "bookmaker_count": s.bookmaker_count,
                    "source_bookmakers": s.available_bookmakers,
                    "spread": s.probability_spread,
                    "disagreement_flag": s.disagreement_flag,
                    "blocked": s.blocked,
                    "source_row_hashes": s.source_row_hashes,
                    "source_files": s.source_files,
                }
            )

        fixtures_out.append(
            {
                "fixture_id": fixture_id,
                "match": f"{meta.get('home_team', '?')} vs {meta.get('away_team', '?')}",
                "competition_key": meta.get("competition_key"),
                "kickoff": meta.get("kickoff_utc"),
                "fixture_name": processed["fx_names"].get(fixture_id, ("", ""))[0],
                "markets": markets,
                "market_keys_available": sorted(sels.keys()),
                "ecse_readiness": ecse,
                "consistency": consistency,
            }
        )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "date_processed": PROCESS_DATE,
        "policy_version": cfg.get("version"),
        "policy_config_path": str(POLICY_CONFIG_PATH),
        "fixture_count": len(fixtures_out),
        "stats": processed["stats"],
        "fixtures": fixtures_out,
    }


def build_ecse_readiness_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    ready_full: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []

    for fx in matrix.get("fixtures") or []:
        ecse = fx.get("ecse_readiness") or {}
        status = ecse.get("status", "POLICY_ERROR")
        status_counts[status] = status_counts.get(status, 0) + 1
        entry = {
            "fixture_id": fx.get("fixture_id"),
            "match": fx.get("match"),
            "competition_key": fx.get("competition_key"),
            "status": status,
        }
        if status == "READY_FULL":
            ready_full.append(entry)
        elif status == "READY_PARTIAL":
            partial.append(entry)

    wc = [f for f in ready_full if (f.get("competition_key") or "").startswith("world_cup")]
    uefa = [
        f
        for f in ready_full
        if any(x in (f.get("competition_key") or "") for x in ("uefa", "euro", "champions", "europa", "conference"))
    ]

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "status_counts": status_counts,
        "ready_full_count": len(ready_full),
        "ready_partial_count": len(partial),
        "ready_full_fixtures": ready_full[:100],
        "ready_partial_fixtures": partial[:50],
        "world_cup_ready_full": wc,
        "uefa_ready_full": uefa,
    }


def preview_odds_snapshot_payloads(matrix: dict[str, Any], *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_policy_config()
    previews: list[dict[str, Any]] = []

    for fx in matrix.get("fixtures") or []:
        ecse = fx.get("ecse_readiness") or {}
        status = ecse.get("status")
        consistency = fx.get("consistency") or {}
        normalized_probs: dict[str, float | None] = {}

        for gdata in (consistency.get("groups") or {}).values():
            for k, v in (gdata.get("normalized") or {}).items():
                if v is not None:
                    normalized_probs[k] = v

        for m in fx.get("markets") or []:
            mk = m.get("normalized_market_key")
            if mk and mk not in normalized_probs and m.get("selected_probability") is not None and not m.get("blocked"):
                normalized_probs[mk] = m.get("selected_probability")

        would_insert = status == "READY_FULL"
        previews.append(
            {
                "fixture_id": fx.get("fixture_id"),
                "match": fx.get("match"),
                "competition_key": fx.get("competition_key"),
                "source_provider": "oddalerts_csv_policy",
                "selected_policy_version": cfg.get("version"),
                "markets_included": sorted(normalized_probs.keys()),
                "ecse_markets_included": sorted(k for k in normalized_probs if k in ECSE_REQUIRED_KEYS),
                "normalized_probabilities": normalized_probs,
                "bookmaker_count_avg": round(
                    statistics.mean([m.get("bookmaker_count") or 0 for m in fx.get("markets") or []]) if fx.get("markets") else 0,
                    2,
                ),
                "selected_methods": sorted({m.get("selected_method") for m in fx.get("markets") or [] if m.get("selected_method")}),
                "source_refs": {
                    "row_hash_count": sum(len(m.get("source_row_hashes") or []) for m in fx.get("markets") or []),
                    "file_count": len({f for m in fx.get("markets") or [] for f in (m.get("source_files") or [])}),
                },
                "warnings": ecse.get("consistency_warnings") or [],
                "would_insert": would_insert,
                "blocker_reason": None if would_insert else status,
            }
        )

    would_count = sum(1 for p in previews if p.get("would_insert"))
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "policy_version": cfg.get("version"),
        "preview_count": len(previews),
        "would_insert_count": would_count,
        "would_not_insert_count": len(previews) - would_count,
        "previews": previews,
    }


def final_policy_recommendation(
    matrix: dict[str, Any],
    ecse_summary: dict[str, Any],
    preview: dict[str, Any],
) -> str:
    ready = ecse_summary.get("ready_full_count", 0)
    if ready == 0:
        if ecse_summary.get("status_counts", {}).get("HIGH_DISAGREEMENT_BLOCKED", 0) > 0:
            return "HIGH_DISAGREEMENT_REVIEW_REQUIRED"
        return "NO_ECSE_READY_FIXTURES"

    norm_issues = ecse_summary.get("status_counts", {}).get("NEED_PROBABILITY_NORMALIZATION_FIX", 0)
    if norm_issues > max(ready * 0.2, 1):
        return "NEED_PROBABILITY_NORMALIZATION_FIX"

    blocked = matrix.get("stats", {}).get("blocked_disagreement", 0)
    processed = matrix.get("stats", {}).get("groups_processed", 1)
    if blocked / max(processed, 1) > 0.05:
        return "HIGH_DISAGREEMENT_REVIEW_REQUIRED"

    if preview.get("would_insert_count", 0) >= max(ready * 0.5, 1):
        return "BOOKMAKER_POLICY_READY_FOR_PROMOTION"

    partial = ecse_summary.get("ready_partial_count", 0)
    if partial > ready:
        return "NEED_POLICY_TUNING"

    return "DO_NOT_PROMOTE_YET"
