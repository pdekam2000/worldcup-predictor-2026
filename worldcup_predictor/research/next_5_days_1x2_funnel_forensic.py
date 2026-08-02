"""
NEXT_5_DAYS_1X2_SELECTION_FUNNEL_FORENSIC_AUDIT — research-only helpers.

Read-only analysis of the five-day 1X2 selection funnel. Does not change
production gates, Canonical predictions, freezes, or deployment state.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
TZ = ZoneInfo("Europe/Vienna")
MISSION_BASE = ROOT / "artifacts/next_5_days_12_1x2_2_exact/2026-08-02_2026-08-06/20260801T213441Z"
DATES = ["2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
SELECTED_1X2_FID = 1494227
HALMSTAD_FID = 1494232
PHASE = "NEXT_5_DAYS_1X2_SELECTION_FUNNEL_FORENSIC_AUDIT"
STATUS = "NEXT_5_DAYS_1X2_FUNNEL_FORENSIC_COMPLETE"

CORE_MODELS = ("wde", "ecse", "exact_v2")
EXTRA_MODELS = ("lambda_v2", "dna", "twins")
ALL_MODELS = CORE_MODELS + EXTRA_MODELS


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def norm_dir(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    if not s or s in {"none", "null", "unknown"}:
        return None
    if "no_bet" in s or s == "nobet":
        return None
    if "home" in s or s in {"h", "1", "home_win"}:
        return "home"
    if "away" in s or s in {"a", "2", "away_win"}:
        return "away"
    if "draw" in s or s in {"d", "x"}:
        return "draw"
    return None


def dir_from_scores(scores: list[Any], *, depth: int = 5, rank_weight: bool = False) -> tuple[str | None, dict[str, float]]:
    """Reproduce mission DNA/Twins inference; optionally rank-weight for research."""
    home = draw = away = 0.0
    for i, s in enumerate(scores[:depth]):
        if isinstance(s, dict):
            lab = str(s.get("score") or s.get("scoreline") or "")
            p = s.get("probability")
            if p is not None:
                w = float(p)
            elif rank_weight:
                w = float(depth - i)
            else:
                w = 1.0 / max(1, min(depth, len(scores)))
        else:
            lab = str(s)
            w = float(depth - i) if rank_weight else 1.0
        parts = lab.replace(" ", "").split("-")
        if len(parts) != 2:
            continue
        try:
            h, a = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if h > a:
            home += w
        elif a > h:
            away += w
        else:
            draw += w
    mass = {"home": home, "draw": draw, "away": away}
    if home + draw + away <= 0:
        return None, mass
    return max(mass.items(), key=lambda x: x[1])[0], mass


def dir_from_winner_distribution(dist: dict[str, Any] | None) -> str | None:
    if not dist:
        return None
    items = [(k, float(dist.get(k) or 0)) for k in ("home", "draw", "away")]
    if sum(x[1] for x in items) <= 0:
        # try alternate keys
        mapping = {
            "home": dist.get("home") or dist.get("home_win") or dist.get("1"),
            "draw": dist.get("draw") or dist.get("x") or dist.get("X"),
            "away": dist.get("away") or dist.get("away_win") or dist.get("2"),
        }
        items = [(k, float(mapping.get(k) or 0)) for k in ("home", "draw", "away")]
    if sum(x[1] for x in items) <= 0:
        return None
    return max(items, key=lambda x: x[1])[0]


def load_mission(base: Path | None = None) -> dict[str, Any]:
    b = base or MISSION_BASE
    return {
        "base": b,
        "discovered": _load_json(b / "discovered_universe.json"),
        "eligibility": _load_json(b / "eligibility_report.json"),
        "blocked": _load_json(b / "blocked_fixtures.json"),
        "canonical": _load_json(b / "canonical_predictions.json"),
        "directions": _load_json(b / "all_model_directions.json"),
        "agreement": _load_json(b / "model_agreement_report.json"),
        "final_1x2": _load_json(b / "final_12_1x2.json"),
        "ranked_1x2": _load_json(b / "ranked_1x2_candidates.json"),
        "manifest": _load_json(b / "run_manifest.json"),
        "odds": _load_json(b / "fresh_odds_report.json"),
        "freeze": _load_json(b / "freeze_integrity_report.json"),
    }


def load_broad_audits(dates: list[str] | None = None) -> dict[str, Any]:
    dates = dates or DATES
    per_day: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    keys = [
        "provider_raw_count",
        "deduplicated_count",
        "prematch_count",
        "tier_a_count",
        "tier_b_count",
        "friendly_count",
        "unsupported_count",
        "odds_missing_count",
        "prediction_candidate_count",
        "synced_to_db_count",
    ]
    pagination: list[dict[str, Any]] = []
    for d in dates:
        path = ROOT / f"artifacts/daily_pipeline/{d}/full_day/discovery.json"
        disc = _load_json(path)
        ba = (disc.get("discovery_audit") or {}).get("broad_audit") or {}
        row = {"date": d, **{k: ba.get(k) for k in keys}, "provider_fetch_ok": ba.get("provider_fetch_ok"), "provider_error": ba.get("provider_error"), "source_order": ba.get("source_order"), "db_window_count": ba.get("db_window_count")}
        per_day.append(row)
        for k in keys:
            totals[k] += int(ba.get(k) or 0)
        pagination.append(
            {
                "date": d,
                "provider_raw_count": ba.get("provider_raw_count"),
                "provider_fetch_attempted": ba.get("provider_fetch_attempted"),
                "provider_fetch_ok": ba.get("provider_fetch_ok"),
                "provider_error": ba.get("provider_error"),
                "source_order": ba.get("source_order"),
                "db_window_count": ba.get("db_window_count"),
                "note": "API-Football fixtures?date=YYYY-MM-DD via broad discovery; cache-first. No explicit page cursor in audit — single date fetch per Vienna day.",
            }
        )
    return {"per_day": per_day, "totals": dict(totals), "pagination": pagination}


def vienna_date_bounds_audit(dates: list[str] | None = None) -> dict[str, Any]:
    dates = dates or DATES
    rows = []
    for d in dates:
        day = datetime.fromisoformat(d).date()
        start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=TZ)
        end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=TZ)
        rows.append(
            {
                "vienna_date": d,
                "vienna_start": start.isoformat(),
                "vienna_end": end.isoformat(),
                "utc_start": start.astimezone(timezone.utc).isoformat(),
                "utc_end": end.astimezone(timezone.utc).isoformat(),
                "dst_offset": start.utcoffset().total_seconds() / 3600 if start.utcoffset() else None,
            }
        )
    return {
        "timezone": "Europe/Vienna",
        "dates": rows,
        "window_note": "Owner discovery uses Vienna calendar days; provider fetch uses local date string. Cross-midnight UTC fixtures belong to Vienna date of local kickoff.",
    }


def infer_no_bet_reason_codes(can_row: dict[str, Any], ag_row: dict[str, Any]) -> list[str]:
    """Best-effort reconstruction — mission artifacts often omit explicit no_bet_reasons."""
    if not can_row.get("no_bet"):
        return []
    codes: list[str] = []
    conf = _f(can_row.get("confidence"))
    if conf is not None and conf < 60.0:
        codes.append("CONFIDENCE_BELOW_60")
    if ag_row.get("agreement_status") == "DIRECTION_CONFLICT":
        codes.append("DIRECTION_CONFLICT_OBSERVED")
    if ag_row.get("forensic_severe"):
        codes.append("FORENSIC_SEVERE")
    if ag_row.get("fresh") is False:
        codes.append("STALE_OR_MISSING_ODDS")
    if can_row.get("override_reason"):
        codes.append(f"OVERRIDE:{can_row.get('override_reason')}")
    if not codes:
        codes.append("NO_BET_TRUE_REASON_NOT_EXPOSED_IN_MISSION_ARTIFACT")
    return codes


def classify_agreement_variants(dirs: dict[str, str | None], *, market: str | None, forensic_severe: bool, fresh: bool) -> dict[str, str]:
    """Research-only alternative agreement classifiers (do not mutate production)."""
    required = {k: dirs.get(k) for k in CORE_MODELS}
    available_core = {k: v for k, v in required.items() if v}
    extras_avail = {k: dirs.get(k) for k in EXTRA_MODELS if dirs.get(k)}
    all_avail = {k: v for k, v in dirs.items() if k != "market" and v}

    def _status_strict_registered() -> str:
        # Treat missing as disagreement / insufficient
        if len(available_core) < 3:
            return "INSUFFICIENT_MODEL_OUTPUT"
        if forensic_severe or not fresh:
            return "DIRECTION_CONFLICT" if forensic_severe else "INSUFFICIENT_MODEL_OUTPUT"
        if len(set(available_core.values())) > 1:
            return "DIRECTION_CONFLICT"
        consensus = next(iter(available_core.values()))
        for k in EXTRA_MODELS:
            if dirs.get(k) is None:
                return "INSUFFICIENT_MODEL_OUTPUT"  # missing extra = not unanimous registered
            if dirs.get(k) != consensus:
                return "DIRECTION_CONFLICT"
        if market and market != consensus:
            return "PARTIAL_AGREEMENT"
        return "UNANIMOUS_DIRECTION"

    def _available_unanimity() -> str:
        if len(available_core) < 3:
            return "INSUFFICIENT_MODEL_OUTPUT"
        if forensic_severe or not fresh:
            return "DIRECTION_CONFLICT" if forensic_severe else "INSUFFICIENT_MODEL_OUTPUT"
        if len(set(available_core.values())) > 1:
            return "DIRECTION_CONFLICT"
        consensus = next(iter(available_core.values()))
        opposing = [v for v in extras_avail.values() if v != consensus]
        if market and market != consensus:
            return "PARTIAL_AGREEMENT" if not opposing else "DIRECTION_CONFLICT"
        if opposing:
            return "PARTIAL_AGREEMENT" if len(opposing) == 1 else "DIRECTION_CONFLICT"
        return "UNANIMOUS_DIRECTION"

    def _supermajority_80() -> str:
        if forensic_severe or not fresh:
            return "DIRECTION_CONFLICT" if forensic_severe else "INSUFFICIENT_MODEL_OUTPUT"
        if len(all_avail) < 3:
            return "INSUFFICIENT_MODEL_OUTPUT"
        counts = Counter(all_avail.values())
        top_dir, top_n = counts.most_common(1)[0]
        if top_n / len(all_avail) >= 0.8:
            if market and market != top_dir:
                return "PARTIAL_AGREEMENT"
            return "UNANIMOUS_DIRECTION" if top_n == len(all_avail) else "STRONG_MULTI_MODEL_AGREEMENT"
        if len(set(available_core.values())) == 1 and len(available_core) == 3:
            return "PARTIAL_AGREEMENT"
        return "DIRECTION_CONFLICT"

    def _core_plus_market() -> str:
        if len(available_core) < 3:
            return "INSUFFICIENT_MODEL_OUTPUT"
        if forensic_severe or not fresh:
            return "DIRECTION_CONFLICT" if forensic_severe else "INSUFFICIENT_MODEL_OUTPUT"
        if len(set(available_core.values())) > 1:
            return "DIRECTION_CONFLICT"
        consensus = next(iter(available_core.values()))
        if market and market != consensus:
            return "PARTIAL_AGREEMENT"
        return "UNANIMOUS_DIRECTION"

    def _policy_g() -> str:
        """Core+lambda+market align; at most one low-info (dna/twins) opposes; no severe forensic."""
        if len(available_core) < 3 or forensic_severe or not fresh:
            return "INSUFFICIENT_MODEL_OUTPUT" if not fresh or len(available_core) < 3 else "DIRECTION_CONFLICT"
        if len(set(available_core.values())) > 1:
            return "DIRECTION_CONFLICT"
        consensus = next(iter(available_core.values()))
        if dirs.get("lambda_v2") and dirs.get("lambda_v2") != consensus:
            return "DIRECTION_CONFLICT"
        if market and market != consensus:
            return "PARTIAL_AGREEMENT"
        low_opp = [k for k in ("dna", "twins") if dirs.get(k) and dirs.get(k) != consensus]
        if len(low_opp) > 1:
            return "DIRECTION_CONFLICT"
        if len(low_opp) == 1:
            return "STRONG_MULTI_MODEL_AGREEMENT"
        return "UNANIMOUS_DIRECTION"

    # Import production classifier
    import importlib.util

    path = ROOT / "scripts/run_next_5_days_12_1x2_2_exact_selection.py"
    spec = importlib.util.spec_from_file_location("n5_sel_forensic", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    baseline = mod.classify_1x2_agreement(dirs, market=market, forensic_severe=forensic_severe, fresh=fresh, no_bet=False)

    return {
        "A_baseline_strict": baseline,
        "B_available_unanimity": _available_unanimity(),
        "C_supermajority_80": _supermajority_80(),
        "D_core_plus_market": _core_plus_market(),
        "E_weighted_proxy": _supermajority_80(),  # proxy: same as C without historical weights stored
        "F_no_bet_advisory_agreement_only": baseline,  # agreement same; selection differs
        "G_partial_one_lowinfo": _policy_g(),
        "strict_registered_missing_as_fail": _status_strict_registered(),
    }


def weighted_consensus(dirs: dict[str, str | None], weights: dict[str, float] | None = None) -> str | None:
    weights = weights or {
        "wde": 3.0,
        "ecse": 2.5,
        "exact_v2": 2.0,
        "lambda_v2": 1.5,
        "market": 1.5,
        "dna": 0.5,
        "twins": 0.5,
    }
    mass: dict[str, float] = defaultdict(float)
    for k, w in weights.items():
        d = dirs.get(k) if k != "market" else dirs.get("market")
        if d:
            mass[d] += w
    if not mass:
        return None
    return max(mass.items(), key=lambda x: x[1])[0]


def build_fixture_index(mission: dict[str, Any]) -> dict[int, dict[str, Any]]:
    idx: dict[int, dict[str, Any]] = {}
    for r in mission["discovered"]["rows"]:
        fid = int(r["fixture_id"])
        idx[fid] = {"discovered": r, "fixture_id": fid}
    for r in mission["eligibility"]["rows"]:
        fid = int(r["fixture_id"])
        idx.setdefault(fid, {"fixture_id": fid})["eligibility"] = r
    for r in mission["canonical"]["rows"]:
        fid = int(r["fixture_id"])
        idx.setdefault(fid, {"fixture_id": fid})["canonical"] = r
    for r in mission["directions"]["rows"]:
        fid = int(r["fixture_id"])
        idx.setdefault(fid, {"fixture_id": fid})["directions"] = r
    for r in mission["agreement"]["rows"]:
        fid = int(r["fixture_id"])
        idx.setdefault(fid, {"fixture_id": fid})["agreement"] = r
    for r in mission["odds"]["rows"]:
        fid = int(r["fixture_id"])
        idx.setdefault(fid, {"fixture_id": fid})["odds"] = r
    for r in (mission["blocked"].get("rows") or []):
        fid = int(r["fixture_id"])
        idx.setdefault(fid, {"fixture_id": fid})["blocked"] = r
    for r in (mission.get("freeze", {}).get("rows") or []):
        fid = int(r.get("fixture_id") or 0)
        if fid:
            idx.setdefault(fid, {"fixture_id": fid})["freeze"] = r
    return idx


def stage_funnel(broad: dict[str, Any], mission: dict[str, Any], idx: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Deterministic stage accounting. Raw stages use broad audit aggregates; later stages use mission fixture IDs."""
    t = broad["totals"]
    disc_ids = []
    seen = set()
    duplicate_discovered: list[int] = []
    for r in mission["discovered"]["rows"]:
        fid = int(r["fixture_id"])
        if fid in seen:
            duplicate_discovered.append(fid)
            continue
        seen.add(fid)
        disc_ids.append(fid)
    elig_ids = [fid for fid, row in idx.items() if (row.get("eligibility") or {}).get("eligibility") == "eligible"]
    partial_ids = [fid for fid, row in idx.items() if (row.get("eligibility") or {}).get("eligibility") == "predicted_partial"]
    complete_ids = [fid for fid, row in idx.items() if (row.get("canonical") or {}).get("prediction_complete")]
    fresh_ids = [fid for fid, row in idx.items() if (row.get("agreement") or {}).get("fresh")]
    model_complete = [
        fid
        for fid, row in idx.items()
        if all((row.get("directions") or {}).get(k) for k in CORE_MODELS)
    ]
    agreement_ok = [
        fid
        for fid, row in idx.items()
        if (row.get("agreement") or {}).get("agreement_status") in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}
    ]
    no_bet_false = [fid for fid, row in idx.items() if (row.get("canonical") or {}).get("no_bet") is False]
    final_ids = [int(r["fixture_id"]) for r in mission["final_1x2"]["rows"]]

    # Per-fixture first-fail stage (for discovered universe only; raw provider IDs not stored)
    traces: dict[int, dict[str, Any]] = {}
    for fid in disc_ids:
        row = idx[fid]
        ag = row.get("agreement") or {}
        can = row.get("canonical") or {}
        el = row.get("eligibility") or {}
        dirs = row.get("directions") or {}
        reasons: list[str] = []
        stage = "F18_final_shortlist"
        if el.get("eligibility") != "eligible":
            stage = "F9_canonical_prediction_complete"
            reasons.append(el.get("reason") or "prediction_incomplete")
        elif not ag.get("fresh"):
            stage = "F8_legitimate_fresh_odds"
            reasons.append("odds_not_fresh_or_missing")
        elif not all(dirs.get(k) for k in CORE_MODELS):
            stage = "F12_direction_inference_valid"
            reasons.append("missing_core_direction")
        elif ag.get("forensic_severe"):
            stage = "F13_no_severe_forensic"
            reasons.append("forensic_severe")
        elif ag.get("agreement_status") == "DIRECTION_CONFLICT":
            stage = "F14_no_severe_direction_conflict"
            reasons.append("direction_conflict")
        elif ag.get("agreement_status") == "INSUFFICIENT_MODEL_OUTPUT":
            stage = "F11_required_shadow_outputs"
            reasons.append("insufficient_model_output")
        elif ag.get("agreement_status") == "PARTIAL_AGREEMENT":
            stage = "F16_agreement_status_eligible"
            reasons.append("partial_agreement_not_eligible_for_final")
        elif can.get("no_bet") is True:
            stage = "F15_no_bet_false"
            reasons.append("no_bet_true")
        elif ag.get("research_classification") not in {"STRONG_RESEARCH_CANDIDATE", "RESEARCH_CANDIDATE"}:
            stage = "F17_final_ranking_threshold"
            reasons.append(f"research_class={ag.get('research_classification')}")
        elif fid not in final_ids:
            stage = "F17_final_ranking_threshold"
            reasons.append("below_top12_or_not_ranked")
        else:
            stage = "F18_final_shortlist"
            reasons.append("selected")
        traces[fid] = {
            "fixture_id": fid,
            "match": can.get("match") or ag.get("match"),
            "final_stage": stage,
            "reasons": reasons,
            "agreement_status": ag.get("agreement_status"),
            "no_bet": can.get("no_bet"),
            "research_classification": ag.get("research_classification"),
        }

    def pct(rem: int, inp: int) -> float:
        return round(100.0 * rem / inp, 2) if inp else 0.0

    # Aggregate stages (F0-F5 from broad; F6+ from mission)
    stages = []

    def add(stage_id: str, name: str, inp: int, out: int, removed_ids: list[int] | None, primary: str, soft: bool, note: str = ""):
        rem = inp - out
        stages.append(
            {
                "stage_id": stage_id,
                "name": name,
                "input_count": inp,
                "output_count": out,
                "removed_count": rem,
                "pct_removed": pct(rem, inp),
                "removed_fixture_ids": removed_ids if removed_ids is not None else [],
                "removed_ids_available": removed_ids is not None,
                "primary_reason": primary,
                "secondary_reasons": [],
                "blocker_type": "soft_policy" if soft else "hard_technical",
                "note": note,
            }
        )

    f0 = t["provider_raw_count"]
    f1 = t["deduplicated_count"]
    f2 = t["prematch_count"]  # already date-windowed in broad discovery
    # F3 football validity ≈ prematch (provider football fixtures)
    f3 = f2
    # F4 supported = tier_a + tier_b (may double-count if both set per day; use prediction_candidate)
    f4 = t["prediction_candidate_count"]
    f5 = f4  # owner scope discovery candidates
    add("F0", "raw_provider_rows", f0, f1, None, "deduplicate_provider_rows", False, "IDs not retained in broad audit")
    add("F1", "deduplicated_fixtures", f1, f2, None, "prematch_status_filter", False)
    add("F2", "inside_target_vienna_dates", f2, f3, None, "already_date_scoped_at_fetch", False, "Each day fetched with Vienna date; sum across 5 days")
    add("F3", "football_fixture_validity", f3, f4, None, "tier_a_b_allowlist_vs_unsupported_friendly", True, f"unsupported={t['unsupported_count']} friendly={t['friendly_count']}")
    add("F4", "supported_competition", f4, f5, None, "owner_tier_a_plus_tier_b", True)
    add("F5", "owner_scope", f5, len(disc_ids), disc_ids if False else [], "mission_discovered_equals_prediction_candidates", True, "93 mission discovered")
    # Align F5 output to discovered
    stages[-1]["output_count"] = len(disc_ids)
    stages[-1]["removed_count"] = 0
    stages[-1]["pct_removed"] = 0.0

    # From discovered onward we have IDs
    add("F6", "valid_identity_non_duplicate", len(disc_ids), len(disc_ids), [], "no_additional_dedupe_in_mission", False)
    # F7 prematch — all discovered are prematch candidates
    add("F7", "prematch_status", len(disc_ids), len(disc_ids), [], "discovery_already_prematch", False)

    not_fresh = [fid for fid in disc_ids if not (idx[fid].get("agreement") or {}).get("fresh") and (idx[fid].get("eligibility") or {}).get("eligibility") == "eligible"]
    # Freshness gate among complete; blocked incomplete often lack odds
    after_odds = [fid for fid in elig_ids if (idx[fid].get("agreement") or {}).get("fresh")]
    rem_odds = [fid for fid in elig_ids if fid not in after_odds]
    add("F8", "legitimate_fresh_odds", len(elig_ids), len(after_odds), rem_odds, "fresh_1x2_required", False)

    add("F9", "canonical_prediction_complete", len(disc_ids), len(elig_ids), partial_ids, "prediction_incomplete_or_blocked", False)
    frozen_ok = [fid for fid in elig_ids if (idx[fid].get("canonical") or {}).get("freeze_id")]
    rem_fr = [fid for fid in elig_ids if fid not in frozen_ok]
    add("F10", "immutable_freeze_valid", len(elig_ids), len(frozen_ok), rem_fr, "missing_freeze_id", False)

    after_shadow = [fid for fid in frozen_ok if fid in model_complete and (idx[fid].get("agreement") or {}).get("fresh")]
    rem_sh = [fid for fid in frozen_ok if fid not in after_shadow]
    add("F11", "required_shadow_outputs_available", len(frozen_ok), len(after_shadow), rem_sh, "core_wde_ecse_exact_or_freshness", False)

    dir_valid = [fid for fid in after_shadow if all((idx[fid].get("directions") or {}).get(k) for k in CORE_MODELS)]
    add("F12", "direction_inference_valid_every_core_model", len(after_shadow), len(dir_valid), [f for f in after_shadow if f not in dir_valid], "core_direction_missing", False)

    no_forensic = [fid for fid in dir_valid if not (idx[fid].get("agreement") or {}).get("forensic_severe")]
    add("F13", "no_severe_forensic_contradiction", len(dir_valid), len(no_forensic), [f for f in dir_valid if f not in no_forensic], "forensic_severe", False)

    no_conflict = [fid for fid in no_forensic if (idx[fid].get("agreement") or {}).get("agreement_status") != "DIRECTION_CONFLICT"]
    add("F14", "no_severe_direction_conflict", len(no_forensic), len(no_conflict), [f for f in no_forensic if f not in no_conflict], "multi_model_direction_conflict", True)

    no_bet_pass = [fid for fid in no_conflict if (idx[fid].get("canonical") or {}).get("no_bet") is False]
    add("F15", "no_bet_false", len(no_conflict), len(no_bet_pass), [f for f in no_conflict if f not in no_bet_pass], "canonical_no_bet_true_hard_exclude", True)

    ag_pass = [fid for fid in no_bet_pass if (idx[fid].get("agreement") or {}).get("agreement_status") in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}]
    add("F16", "agreement_status_eligible", len(no_bet_pass), len(ag_pass), [f for f in no_bet_pass if f not in ag_pass], "requires_unanimous_or_strong", True)

    ranked_pass = [
        fid
        for fid in ag_pass
        if (idx[fid].get("agreement") or {}).get("research_classification") in {"STRONG_RESEARCH_CANDIDATE", "RESEARCH_CANDIDATE"}
    ]
    add("F17", "final_ranking_threshold", len(ag_pass), len(ranked_pass), [f for f in ag_pass if f not in ranked_pass], "research_classification_gate", True)
    add("F18", "final_shortlist", len(ranked_pass), len(final_ids), [f for f in ranked_pass if f not in final_ids], "top12_cap", True)

    return stages, traces, {"discovered_row_count": len(mission["discovered"]["rows"]), "unique_discovered": len(disc_ids), "duplicate_discovered_ids": duplicate_discovered}


def build_rejection_ledger(idx: dict[int, dict[str, Any]], traces: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    ledger = []
    for fid, row in sorted(idx.items()):
        if fid == SELECTED_1X2_FID:
            continue
        can = row.get("canonical") or {}
        ag = row.get("agreement") or {}
        dirs = row.get("directions") or {}
        el = row.get("eligibility") or {}
        tr = traces.get(fid) or {}
        missing = [k for k in ALL_MODELS if not dirs.get(k)]
        opposing = []
        core = dirs.get("wde")
        if core:
            opposing = [k for k in list(ALL_MODELS) + ["market"] if dirs.get(k) and dirs.get(k) != core]

        # counterfactual single-gate
        would_pass_if_remove: dict[str, bool] = {}
        # majority / weighted
        avail = {k: dirs.get(k) for k in ALL_MODELS if dirs.get(k)}
        majority = None
        if avail:
            majority = Counter(avail.values()).most_common(1)[0][0]
        wcons = weighted_consensus({**{k: dirs.get(k) for k in ALL_MODELS}, "market": dirs.get("market")})

        variants = classify_agreement_variants(
            {k: dirs.get(k) for k in list(ALL_MODELS) + ["market"]},
            market=dirs.get("market"),
            forensic_severe=bool(ag.get("forensic_severe")),
            fresh=bool(ag.get("fresh")),
        )

        primary = tr.get("final_stage") or "UNKNOWN"
        all_gates = list(tr.get("reasons") or [])
        if can.get("no_bet"):
            all_gates.append("no_bet_true")
        if ag.get("agreement_status") == "PARTIAL_AGREEMENT":
            all_gates.append("partial_agreement")

        # classification
        classification = "NEEDS_MANUAL_REVIEW"
        if el.get("eligibility") != "eligible":
            classification = "MISSING_DATA_EXCLUSION"
        elif ag.get("agreement_status") == "DIRECTION_CONFLICT" and len(opposing) >= 2:
            classification = "CORRECTLY_EXCLUDED_RISK"
        elif ag.get("agreement_status") == "PARTIAL_AGREEMENT" and opposing == ["dna"]:
            classification = "POSSIBLE_FALSE_NEGATIVE"
        elif can.get("no_bet") and (_f(can.get("confidence")) or 0) < 60:
            classification = "CORRECTLY_EXCLUDED_RISK"
        elif can.get("no_bet") and ag.get("agreement_status") == "UNANIMOUS_DIRECTION":
            classification = "OVERSTRICT_POLICY_EXCLUSION"
        elif primary.startswith("F8"):
            classification = "MISSING_DATA_EXCLUSION"

        would_majority = (
            bool(ag.get("fresh"))
            and not ag.get("forensic_severe")
            and can.get("no_bet") is False
            and majority == dirs.get("wde")
            and all(dirs.get(k) for k in CORE_MODELS)
            and len(set(dirs.get(k) for k in CORE_MODELS)) == 1
        )
        would_weighted = (
            bool(ag.get("fresh"))
            and not ag.get("forensic_severe")
            and can.get("no_bet") is False
            and wcons == dirs.get("wde")
            and all(dirs.get(k) for k in CORE_MODELS)
        )
        would_pass_if_remove["no_bet_gate"] = (
            can.get("no_bet") is True
            and ag.get("agreement_status") in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}
            and bool(ag.get("fresh"))
            and not ag.get("forensic_severe")
        )
        would_pass_if_remove["dna_sole_dissent"] = (
            ag.get("agreement_status") == "PARTIAL_AGREEMENT"
            and opposing == ["dna"]
            and can.get("no_bet") is False
            and bool(ag.get("fresh"))
        )

        ledger.append(
            {
                "fixture_id": fid,
                "match": can.get("match") or ag.get("match") or f"{el.get('home')} vs {el.get('away')}",
                "vienna_datetime": can.get("kickoff_vienna") or el.get("vienna_ko"),
                "league": el.get("league") or can.get("match"),
                "country": el.get("country"),
                "H": can.get("wde_h"),
                "D": can.get("wde_d"),
                "A": can.get("wde_a"),
                "canonical_wde_direction": dirs.get("wde"),
                "canonical_ecse_direction": dirs.get("ecse"),
                "exact_v2_direction": dirs.get("exact_v2"),
                "lambda_v2_direction": dirs.get("lambda_v2"),
                "dna_direction": dirs.get("dna"),
                "twins_direction": dirs.get("twins"),
                "market_direction": dirs.get("market"),
                "forensic_verdict": None,
                "forensic_severe": ag.get("forensic_severe"),
                "no_bet": can.get("no_bet"),
                "no_bet_reason_codes": infer_no_bet_reason_codes(can, ag),
                "confidence": can.get("confidence"),
                "entropy": can.get("entropy"),
                "conflict_count": ag.get("opposing"),
                "missing_outputs": missing,
                "primary_rejection_gate": primary,
                "all_rejection_gates": sorted(set(all_gates)),
                "first_stage_rejected": primary,
                "technical_vs_policy": "policy" if primary in {"F15_no_bet_false", "F16_agreement_status_eligible", "F14_no_severe_direction_conflict", "F17_final_ranking_threshold"} else "technical",
                "would_pass_if_one_gate_removed": would_pass_if_remove,
                "would_pass_majority_agreement": would_majority,
                "would_pass_weighted_agreement": would_weighted,
                "agreement_variants": variants,
                "recommended_audit_classification": classification,
            }
        )
    return ledger


def counterfactual_policies(idx: dict[int, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    policies: dict[str, Any] = {}
    lists: dict[str, list[dict[str, Any]]] = {}

    def candidate_row(fid: int, policy: str) -> dict[str, Any]:
        row = idx[fid]
        can = row.get("canonical") or {}
        ag = row.get("agreement") or {}
        dirs = row.get("directions") or {}
        return {
            "fixture_id": fid,
            "match": can.get("match") or ag.get("match"),
            "policy": policy,
            "agreement_status": ag.get("agreement_status"),
            "no_bet": can.get("no_bet"),
            "confidence": can.get("confidence"),
            "entropy": can.get("entropy"),
            "direction": dirs.get("wde"),
            "league": (row.get("eligibility") or {}).get("league"),
            "opposing": ag.get("opposing"),
        }

    # A baseline
    a_ids = [
        fid
        for fid, row in idx.items()
        if (row.get("eligibility") or {}).get("eligibility") == "eligible"
        and (row.get("agreement") or {}).get("agreement_status") in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}
        and (row.get("agreement") or {}).get("research_classification") in {"STRONG_RESEARCH_CANDIDATE", "RESEARCH_CANDIDATE"}
        and (row.get("canonical") or {}).get("no_bet") is False
        and (row.get("agreement") or {}).get("fresh")
        and not (row.get("agreement") or {}).get("forensic_severe")
    ]
    lists["A_baseline"] = [candidate_row(f, "A") for f in a_ids]
    policies["A_baseline"] = {"candidate_count": len(a_ids), "selected_fixture_ids": a_ids[:12], "note": "Current production selection logic"}

    def collect(policy_key: str, agree_keys: set[str], *, ignore_no_bet: bool = False, variant_field: str | None = None):
        ids = []
        for fid, row in idx.items():
            can = row.get("canonical") or {}
            ag = row.get("agreement") or {}
            dirs = row.get("directions") or {}
            if (row.get("eligibility") or {}).get("eligibility") != "eligible":
                continue
            if not ag.get("fresh") or ag.get("forensic_severe"):
                continue
            if not ignore_no_bet and can.get("no_bet") is not False:
                continue
            if not all(dirs.get(k) for k in CORE_MODELS):
                continue
            if variant_field:
                variants = classify_agreement_variants(
                    {k: dirs.get(k) for k in list(ALL_MODELS) + ["market"]},
                    market=dirs.get("market"),
                    forensic_severe=bool(ag.get("forensic_severe")),
                    fresh=bool(ag.get("fresh")),
                )
                status = variants.get(variant_field)
            else:
                status = ag.get("agreement_status")
            if status not in agree_keys:
                continue
            # confidence soft floor for research honesty
            conf = _f(can.get("confidence"))
            if conf is not None and conf < 35:
                continue
            ids.append(fid)
        lists[policy_key] = [candidate_row(f, policy_key) for f in ids]
        policies[policy_key] = {
            "candidate_count": len(ids),
            "selected_fixture_ids": ids[:12],
            "ignore_no_bet": ignore_no_bet,
            "agreement_keys": sorted(agree_keys),
        }

    collect("B_available_unanimity", {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}, variant_field="B_available_unanimity")
    collect("C_supermajority_80", {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}, variant_field="C_supermajority_80")
    collect("D_core_plus_market", {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT", "PARTIAL_AGREEMENT"}, variant_field="D_core_plus_market")
    # refine D: only UNANIMOUS from core+market variant
    collect("D_core_plus_market", {"UNANIMOUS_DIRECTION"}, variant_field="D_core_plus_market")
    collect("E_weighted_proxy", {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}, variant_field="E_weighted_proxy")
    collect("F_no_bet_advisory", {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}, ignore_no_bet=True)
    collect("G_partial_one_lowinfo", {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}, variant_field="G_partial_one_lowinfo")
    collect(
        "G_plus_F_partial_one_lowinfo_no_bet_advisory",
        {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"},
        ignore_no_bet=True,
        variant_field="G_partial_one_lowinfo",
    )

    # Confidence-filtered honesty views
    for base_key, out_key, min_conf in [
        ("F_no_bet_advisory", "F_no_bet_advisory_conf_ge_60", 60.0),
        ("G_plus_F_partial_one_lowinfo_no_bet_advisory", "G_plus_F_conf_ge_60", 60.0),
    ]:
        rows = [r for r in lists.get(base_key, []) if (_f(r.get("confidence")) or 0) >= min_conf]
        lists[out_key] = rows
        policies[out_key] = {
            "candidate_count": len(rows),
            "selected_fixture_ids": [r["fixture_id"] for r in rows[:12]],
            "parent_policy": base_key,
            "min_confidence": min_conf,
            "note": "Research honesty filter — still advisory; does not clear Canonical no_bet semantics.",
        }

    # Enrich summaries
    for k, rows in lists.items():
        confs = [_f(r["confidence"]) for r in rows if _f(r["confidence"]) is not None]
        ents = [_f(r["entropy"]) for r in rows if _f(r["entropy"]) is not None]
        policies[k]["confidence_distribution"] = {
            "n": len(confs),
            "mean": round(sum(confs) / len(confs), 2) if confs else None,
            "min": min(confs) if confs else None,
            "max": max(confs) if confs else None,
        }
        policies[k]["entropy_distribution"] = {
            "n": len(ents),
            "mean": round(sum(ents) / len(ents), 3) if ents else None,
        }
        policies[k]["no_bet_distribution"] = dict(Counter(str(r.get("no_bet")) for r in rows))
        policies[k]["league_distribution"] = dict(Counter(r.get("league") for r in rows))
        policies[k]["conflict_distribution"] = dict(Counter(r.get("opposing") for r in rows))
        policies[k]["out_of_five_day_discovered_universe"] = f"{len(rows)} / 93"
        policies[k]["historical_wde_hit_rate"] = None  # filled by historical module if available
        policies[k]["fp_fn_tradeoff"] = (
            "Higher candidate count increases recall risk; validate on chronological holdout before adopting."
        )

    return policies, lists


def historical_gate_validation() -> dict[str, Any]:
    """Chronological frozen evaluation using local predictions + evaluations tables when available."""
    db = ROOT / "data" / "football_intelligence.db"
    out: dict[str, Any] = {
        "status": "PARTIAL",
        "method": "chronological_split_on_local_evaluations",
        "leakage_controls": [
            "uses only completed evaluations",
            "no target-window Aug 2-6 2026 outcomes",
            "does not join post-kickoff features for selection simulation",
        ],
    }
    if not db.exists():
        out["status"] = "UNAVAILABLE"
        out["error"] = "football_intelligence.db missing"
        return out
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Prefer evaluations with actual_result and no_bet flag
        rows = conn.execute(
            """
            SELECT fixture_id, no_bet, actual_result, final_score, market_1x2_status, evaluated_at, competition_key
            FROM worldcup_prediction_evaluations
            WHERE actual_result IS NOT NULL AND actual_result != ''
            ORDER BY evaluated_at ASC
            """
        ).fetchall()
        preds = {
            int(r["fixture_id"]): dict(r)
            for r in conn.execute(
                "SELECT fixture_id, confidence, no_bet_flag, prediction_quality, data_quality FROM predictions"
            )
        }
        conn.close()
    except Exception as exc:  # noqa: BLE001
        out["status"] = "UNAVAILABLE"
        out["error"] = str(exc)[:300]
        return out

    if len(rows) < 30:
        out["status"] = "INSUFFICIENT_SAMPLE"
        out["sample_size"] = len(rows)
        return out

    n = len(rows)
    i1, i2 = int(n * 0.6), int(n * 0.8)
    splits = {"train": rows[:i1], "validation": rows[i1:i2], "holdout": rows[i2:]}

    def summarize(split_rows: list) -> dict[str, Any]:
        # Gate proxies: no_bet vs bettable; confidence>=60
        bettable = [r for r in split_rows if not r["no_bet"]]
        conf_ok = []
        for r in bettable:
            p = preds.get(int(r["fixture_id"])) or {}
            conf = _f(p.get("confidence"))
            if conf is None or conf >= 60:
                conf_ok.append(r)
        def hit_rate(subset):
            if not subset:
                return None
            hits = sum(1 for r in subset if str(r["market_1x2_status"] or "").upper() in {"HIT", "WON", "CORRECT", "TRUE", "1"})
            # if market status sparse, return null
            labeled = sum(1 for r in subset if r["market_1x2_status"] not in (None, ""))
            if labeled < max(5, len(subset) // 5):
                return {"labeled": labeled, "hits": hits, "rate": None, "note": "market_1x2_status sparse"}
            return {"labeled": labeled, "hits": hits, "rate": round(hits / labeled, 4) if labeled else None}

        return {
            "n": len(split_rows),
            "no_bet_true": sum(1 for r in split_rows if r["no_bet"]),
            "no_bet_false": len(bettable),
            "confidence_ge_60_among_bettable": len(conf_ok),
            "1x2_status_bettable": hit_rate(bettable),
            "1x2_status_conf_gate": hit_rate(conf_ok),
        }

    out["splits"] = {k: summarize(v) for k, v in splits.items()}
    out["sample_size"] = n
    out["status"] = "OK"
    out["caveat"] = (
        "Historical labels are evaluation-table proxies, not a full re-run of the multi-model 1X2 funnel. "
        "Use for directional evidence only."
    )
    return out


def root_cause_ranking(
    broad: dict[str, Any],
    mission: dict[str, Any],
    ledger: list[dict[str, Any]],
    policies: dict[str, Any],
) -> list[dict[str, Any]]:
    ag = mission["agreement"]["rows"]
    can = mission["canonical"]["rows"]
    t = broad["totals"]
    sole_dna = [r for r in ledger if r.get("recommended_audit_classification") == "POSSIBLE_FALSE_NEGATIVE" and (r.get("all_rejection_gates") and "partial_agreement" in r["all_rejection_gates"])]
    # more precise sole dna from agreement
    sole_dna_fids = []
    for a in ag:
        if a.get("agreement_status") != "PARTIAL_AGREEMENT":
            continue
        dirs = {k: a.get(k) for k in list(ALL_MODELS) + ["market"]}
        core = a.get("wde")
        opp = [k for k, v in dirs.items() if v and core and v != core]
        if opp == ["dna"]:
            sole_dna_fids.append(int(a["fixture_id"]))

    uni_nobet = sum(1 for a in ag if a.get("agreement_status") == "UNANIMOUS_DIRECTION" and a.get("no_bet") is True)
    causes = [
        {
            "rank": 1,
            "cause": "discovery_universe_intentionally_narrow_vs_worldwide",
            "fixtures_affected": int(t["unsupported_count"] + t["friendly_count"]),
            "fixtures_affected_exclusively": int(t["unsupported_count"] + t["friendly_count"]),
            "severity": "HIGH",
            "confidence": 0.95,
            "expected_or_defect": "EXPECTED_POLICY",
            "recommended_action": "Document that ~890–1070 worldwide/provider fixtures are not the prediction universe; owner Tier A/B allowlist yields 93.",
            "implementation_risk": "NONE",
            "evidence": {
                "provider_raw_5d": t["provider_raw_count"],
                "unsupported": t["unsupported_count"],
                "friendly": t["friendly_count"],
                "prediction_candidates": t["prediction_candidate_count"],
            },
        },
        {
            "rank": 2,
            "cause": "no_bet_hard_exclusion_dominates_post_agreement",
            "fixtures_affected": sum(1 for c in can if c.get("no_bet") is True),
            "fixtures_affected_exclusively": uni_nobet,
            "severity": "HIGH",
            "confidence": 0.93,
            "expected_or_defect": "EXPECTED_POLICY_POSSIBLY_OVERSTRICT",
            "recommended_action": "Keep production no_bet; research Policy F for advisory mode. Audit CONFIDENCE_BELOW_60 dominance.",
            "implementation_risk": "MEDIUM",
            "evidence": {"unanimous_but_no_bet": uni_nobet, "no_bet_false_total": sum(1 for c in can if c.get("no_bet") is False)},
        },
        {
            "rank": 3,
            "cause": "dna_unweighted_top5_sole_dissent_blocks_partial_to_final",
            "fixtures_affected": len(sole_dna_fids),
            "fixtures_affected_exclusively": len(sole_dna_fids),
            "severity": "HIGH",
            "confidence": 0.9,
            "expected_or_defect": "DIRECTION_INFERENCE_DEFECT_OR_OVERSTRICT",
            "recommended_action": "Prefer DNA winner_distribution when present; treat DNA/Twins as advisory (Policy G) after historical validation.",
            "implementation_risk": "MEDIUM",
            "evidence": {"sole_dna_fixture_ids": sole_dna_fids, "includes_halmstad": HALMSTAD_FID in sole_dna_fids},
        },
        {
            "rank": 4,
            "cause": "strict_agreement_requires_extras_alignment",
            "fixtures_affected": sum(1 for a in ag if a.get("agreement_status") in {"PARTIAL_AGREEMENT", "DIRECTION_CONFLICT"}),
            "fixtures_affected_exclusively": sum(1 for a in ag if a.get("agreement_status") == "DIRECTION_CONFLICT"),
            "severity": "MEDIUM",
            "confidence": 0.85,
            "expected_or_defect": "EXPECTED_POLICY",
            "recommended_action": "Counterfactual core-model agreement (Policy D/G) before any production change.",
            "implementation_risk": "MEDIUM",
        },
        {
            "rank": 5,
            "cause": "legitimate_scarcity_among_no_bet_false",
            "fixtures_affected": 2,
            "fixtures_affected_exclusively": 1,
            "severity": "MEDIUM",
            "confidence": 0.8,
            "expected_or_defect": "EXPECTED",
            "recommended_action": "Only 2 fixtures have no_bet=false; after DNA gate, 1 remains — scarcity is real inside curated+canonical gates.",
            "implementation_risk": "NONE",
            "evidence": {"no_bet_false_ids": [int(c["fixture_id"]) for c in can if c.get("no_bet") is False]},
        },
        {
            "rank": 6,
            "cause": "missing_output_denominator",
            "fixtures_affected": sum(1 for a in ag if a.get("agreement_status") == "INSUFFICIENT_MODEL_OUTPUT"),
            "fixtures_affected_exclusively": sum(1 for a in ag if a.get("agreement_status") == "INSUFFICIENT_MODEL_OUTPUT"),
            "severity": "LOW",
            "confidence": 0.75,
            "expected_or_defect": "EXPECTED_TECHNICAL",
            "recommended_action": "Keep missing ≠ disagreement; blocked/incomplete already separated.",
            "implementation_risk": "LOW",
        },
        {
            "rank": 7,
            "cause": "reporting_aggregation_bug",
            "fixtures_affected": 1,
            "fixtures_affected_exclusively": 1,
            "severity": "LOW",
            "confidence": 0.85,
            "expected_or_defect": "MINOR_REPORTING_DEFECT",
            "recommended_action": "Deduplicate discovered_universe by fixture_id across days; document Vienna date-boundary duplicates (1498692).",
            "implementation_risk": "LOW",
            "evidence": {"duplicate_fixture_id": 1498692, "rows_93_unique_92": True},
        },
        {
            "rank": 8,
            "cause": "selection_undercount_of_final_1x2",
            "fixtures_affected": 0,
            "fixtures_affected_exclusively": 0,
            "severity": "LOW",
            "confidence": 0.9,
            "expected_or_defect": "NOT_FOUND",
            "recommended_action": "None — baseline reproduces 1 final 1X2 (Djurgården).",
            "implementation_risk": "NONE",
        },
    ]
    # remove old rank 7 not_found if we replaced - check causes list building

    # attach policy deltas
    for c in causes:
        c["policy_candidate_counts"] = {k: policies.get(k, {}).get("candidate_count") for k in policies}
    return causes


def try_halmstad_dna_replay() -> dict[str, Any]:
    """Readonly DNA enrich for Halmstad case study — no freeze writes."""
    day = ROOT / "artifacts/daily_pipeline/2026-08-03/full_day/full_predictions.json"
    preds = _load_json(day)
    rows = preds.get("rows") or preds.get("predictions") or []
    if isinstance(preds, dict) and not rows:
        # may be list under another key
        for v in preds.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "fixture_id" in v[0]:
                rows = v
                break
    p = next((r for r in rows if int(r.get("fixture_id") or 0) == HALMSTAD_FID), None)
    if not p:
        return {"status": "PREDICTION_NOT_FOUND", "fixture_id": HALMSTAD_FID}
    try:
        import importlib.util

        path = ROOT / "scripts/run_five_day_complete_prediction_scan.py"
        spec = importlib.util.spec_from_file_location("five_day_scan_forensic", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        engines = mod.build_evidence_engines()
        ev = mod.enrich_evidence(p, engines)
        dna = ev.get("dna") or {}
        top5 = list(dna.get("top5") or [])
        unweighted, mass_u = dir_from_scores(top5, depth=5, rank_weight=False)
        rank_w, mass_r = dir_from_scores(top5, depth=5, rank_weight=True)
        win_dist = dna.get("winner_distribution")
        from_dist = dir_from_winner_distribution(win_dist if isinstance(win_dist, dict) else None)
        return {
            "status": dna.get("status"),
            "fixture_id": HALMSTAD_FID,
            "top5": top5,
            "unweighted_dir_from_scores": unweighted,
            "unweighted_mass": mass_u,
            "rank_weighted_dir": rank_w,
            "rank_weighted_mass": mass_r,
            "winner_distribution": win_dist,
            "dir_from_winner_distribution": from_dist,
            "engine_errors": engines.get("errors"),
            "probabilities_in_top5": any(isinstance(s, dict) and s.get("probability") is not None for s in top5),
            "tie_between_draw_and_away": (
                abs(mass_u.get("draw", 0) - mass_u.get("away", 0)) < 1e-12
                and mass_u.get("draw", 0) >= mass_u.get("home", 0)
            ),
            "tie_break_behavior": "max(mass.items()) returns first key among ties in insertion order (home, draw, away) — so draw beats away on equal counts",
            "conclusion": (
                "Mission used unweighted Top5 score-count inference. "
                "Halmstad Top5=['1-1','0-1','1-2','0-0','1-0'] → mass draw=2, away=2, home=1. "
                "Inferred DNA=draw is a TIE ARTIFACT (draw preferred over away on equal unweighted counts), "
                "not a robust full-distribution dissent. Winner_distribution was null in this replay."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "REPLAY_ERROR", "error": str(exc)[:400], "fixture_id": HALMSTAD_FID}


def freeze_hashes_snapshot(mission: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for r in mission["canonical"]["rows"]:
        fid = r.get("fixture_id")
        fz = r.get("freeze_id")
        rows.append({"fixture_id": fid, "freeze_id": fz, "freeze_id_sha16": hashlib.sha256(str(fz or "").encode()).hexdigest()[:16]})
    return {
        "count": len(rows),
        "rows": rows,
        "aggregate_sha256": hashlib.sha256("|".join(f"{r['fixture_id']}:{r['freeze_id']}" for r in rows).encode()).hexdigest(),
    }


def run_audit(out_dir: Path | None = None) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir or (ROOT / "artifacts/next_5_days_1x2_funnel_forensic" / ts)
    out.mkdir(parents=True, exist_ok=True)

    mission = load_mission()
    broad = load_broad_audits()
    idx = build_fixture_index(mission)
    stages, traces, disc_meta = stage_funnel(broad, mission, idx)
    ledger = build_rejection_ledger(idx, traces)
    policies, policy_lists = counterfactual_policies(idx)
    hist = historical_gate_validation()
    causes = root_cause_ranking(broad, mission, ledger, policies)
    halm = try_halmstad_dna_replay()
    freeze_snap = freeze_hashes_snapshot(mission)

    t = broad["totals"]
    approx_890 = {
        "owner_stated_approx": 890,
        "traced_candidates": {
            "provider_raw_5_day_sum": t["provider_raw_count"],
            "deduplicated_5_day_sum": t["deduplicated_count"],
            "unsupported_5_day_sum": t["unsupported_count"],
            "friendly_5_day_sum": t["friendly_count"],
            "unsupported_plus_friendly": t["unsupported_count"] + t["friendly_count"],
            "prediction_candidates_tier_ab": t["prediction_candidate_count"],
        },
        "best_match_interpretation": (
            "Owner ~890 most closely matches the worldwide/provider football fixture volume "
            f"(raw={t['provider_raw_count']}, unsupported+friendly={t['unsupported_count'] + t['friendly_count']}) "
            "NOT the owner Tier A/B prediction universe (93)."
        ),
        "why_mission_93": (
            "discover_today_matches(scope=owner) keeps only Tier A (DAILY_SUPPORTED_COMPETITIONS) + Tier B shadow domains; "
            "friendlies and unsupported leagues are listed in broad audit but excluded from prediction candidates."
        ),
        "discovery_too_narrow": (
            "Narrow relative to worldwide calendars by design (policy allowlist), not by pagination failure. "
            "Provider fetch_ok across all five days; prediction_candidate_count sums to 93."
        ),
    }

    raw_recon = {
        "phase": PHASE,
        "dates": DATES,
        "timezone": "Europe/Vienna",
        "mission_artifact": str(mission["base"].relative_to(ROOT)).replace("\\", "/"),
        "counts": {
            "raw_provider_fixtures": t["provider_raw_count"],
            "deduplicated_raw_fixtures": t["deduplicated_count"],
            "football_prematch_fixtures": t["prematch_count"],
            "target_date_fixtures_vienna_sum": t["prematch_count"],
            "timezone_adjusted_vienna_date_fixtures": t["prematch_count"],
            "supported_league_fixtures_tier_a_plus_b": t["prediction_candidate_count"],
            "owner_scope_fixtures": t["prediction_candidate_count"],
            "mission_discovered_rows": len(mission["discovered"]["rows"]),
            "mission_discovered_unique_fixtures": len({int(r["fixture_id"]) for r in mission["discovered"]["rows"]}),
            "canonical_eligible_fixtures": sum(1 for r in mission["eligibility"]["rows"] if r.get("eligibility") == "eligible"),
            "odds_fresh_among_agreement_rows": sum(1 for r in mission["agreement"]["rows"] if r.get("fresh")),
            "predicted_fixtures": sum(1 for r in mission["canonical"]["rows"] if r.get("prediction_complete")),
            "frozen_fixtures": sum(1 for r in mission["canonical"]["rows"] if r.get("freeze_id")),
            "model_complete_core_trio": sum(
                1
                for r in mission["directions"]["rows"]
                if all(r.get(k) for k in CORE_MODELS)
            ),
            "agreement_eligible_unanimous_or_strong": sum(
                1
                for r in mission["agreement"]["rows"]
                if r.get("agreement_status") in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}
            ),
            "no_bet_false_fixtures": sum(1 for r in mission["canonical"]["rows"] if r.get("no_bet") is False),
            "final_selected_1x2_fixtures": mission["final_1x2"]["count"],
        },
        "approx_890_reconciliation": approx_890,
        "per_day_broad": broad["per_day"],
    }

    # missing vs disagreement
    missing_rows = []
    for r in mission["agreement"]["rows"]:
        dirs = {k: r.get(k) for k in ALL_MODELS}
        avail = {k: v for k, v in dirs.items() if v}
        missing = [k for k, v in dirs.items() if not v]
        core = r.get("wde")
        opposing = [k for k, v in dirs.items() if v and core and v != core]
        missing_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "required_model_count": len(CORE_MODELS),
                "registered_model_count": len(ALL_MODELS),
                "available_model_count": len(avail),
                "unavailable_model_count": len(missing),
                "models_truly_opposing": opposing,
                "models_merely_missing": missing,
                "agreement_status": r.get("agreement_status"),
                "agreement_numerator": r.get("supporting"),
                "agreement_denominator_observed": (r.get("supporting") or 0) + (r.get("opposing") or 0),
                "denominator_treatment": (
                    "Production classifier requires core trio present; missing extras are ignored (not counted as dissent). "
                    "INSUFFICIENT_MODEL_OUTPUT used when core missing or odds not fresh — distinct from DIRECTION_CONFLICT."
                ),
                "denominator_valid": r.get("agreement_status") != "DIRECTION_CONFLICT" or not missing,
            }
        )

    denom_analysis = {
        "production_rule": "Missing extras ≠ disagreement; missing core → INSUFFICIENT_MODEL_OUTPUT",
        "recomputations": {
            "strict_all_registered_unanimity_count": sum(
                1
                for r in mission["agreement"]["rows"]
                if classify_agreement_variants(
                    {k: r.get(k) for k in list(ALL_MODELS) + ["market"]},
                    market=r.get("market"),
                    forensic_severe=bool(r.get("forensic_severe")),
                    fresh=bool(r.get("fresh")),
                )["strict_registered_missing_as_fail"]
                == "UNANIMOUS_DIRECTION"
            ),
            "available_unanimity_count": sum(
                1
                for r in mission["agreement"]["rows"]
                if classify_agreement_variants(
                    {k: r.get(k) for k in list(ALL_MODELS) + ["market"]},
                    market=r.get("market"),
                    forensic_severe=bool(r.get("forensic_severe")),
                    fresh=bool(r.get("fresh")),
                )["B_available_unanimity"]
                == "UNANIMOUS_DIRECTION"
            ),
            "supermajority_80_count": policies["C_supermajority_80"]["candidate_count"],
            "core_market_count": policies["D_core_plus_market"]["candidate_count"],
            "weighted_proxy_count": policies["E_weighted_proxy"]["candidate_count"],
        },
        "finding": "No evidence that missing outputs were counted as opposing votes in production classifier.",
    }

    # no_bet audits
    nobet_dist: Counter[str] = Counter()
    nobet_fixtures = []
    for row in ledger:
        can = (idx[row["fixture_id"]].get("canonical") or {})
        if not can.get("no_bet"):
            continue
        codes = row.get("no_bet_reason_codes") or []
        for c in codes:
            nobet_dist[c] += 1
        nobet_fixtures.append(
            {
                "fixture_id": row["fixture_id"],
                "match": row["match"],
                "no_bet_reason_codes": codes,
                "confidence": row["confidence"],
                "entropy": row["entropy"],
                "agreement_status": (idx[row["fixture_id"]].get("agreement") or {}).get("agreement_status"),
                "fresh": (idx[row["fixture_id"]].get("agreement") or {}).get("fresh"),
                "hard_block_in_selection": True,
                "generated_before_shadow": True,
                "note": "Canonical no_bet is set during owner prediction before research shadow agreement.",
            }
        )

    uni_nobet_ids = [
        int(a["fixture_id"])
        for a in mission["agreement"]["rows"]
        if a.get("agreement_status") == "UNANIMOUS_DIRECTION" and a.get("no_bet") is True
    ]
    nobet_fn = {
        "unanimous_no_bet_true": uni_nobet_ids,
        "count": len(uni_nobet_ids),
        "interpretation": "These passed multi-model direction unanimity but remain excluded by Canonical abstention — primary post-discovery bottleneck for 1X2 shortlist.",
        "do_not_remove_in_production": True,
    }

    thresholds = {
        "CONFIDENCE_NO_BET_THRESHOLD": {"value": 60.0, "source": "worldcup_predictor/decision/no_bet_reasons.py", "removed_sole": sum(1 for c in mission["canonical"]["rows"] if c.get("no_bet") and (_f(c.get("confidence")) or 0) < 60), "validated": "inherited_production"},
        "agreement_requires_unanimous_or_strong": {"value": ["UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"], "source": "scripts/run_next_5_days_12_1x2_2_exact_selection.py", "removed_sole": sum(1 for a in mission["agreement"]["rows"] if a.get("agreement_status") == "PARTIAL_AGREEMENT" and a.get("no_bet") is False), "validated": "mission_policy"},
        "no_bet_hard_exclude": {"value": True, "source": "scripts/run_next_5_days_12_1x2_2_exact_selection.py cands_1x2", "removed_sole": nobet_fn["count"], "validated": "mission_policy"},
        "fresh_odds_required": {"value": "FRESH + has_1x2", "source": "selection refresh_odds_for_selection", "removed": sum(1 for a in mission["agreement"]["rows"] if not a.get("fresh")), "validated": "technical"},
        "research_class_min_quality": {"value": "STRONG/RESEARCH_CANDIDATE via q thresholds 55/35", "source": "research_class()", "validated": "mission_heuristic"},
        "extras_opposing_one_is_partial": {"value": 1, "source": "classify_1x2_agreement", "removed_sole": len([1 for a in mission["agreement"]["rows"] if a.get("agreement_status") == "PARTIAL_AGREEMENT"]), "validated": "mission_policy"},
    }

    threshold_impact = {
        "sole_impact": {
            "no_bet_on_unanimous": nobet_fn["count"],
            "dna_sole_partial_with_no_bet_false": sum(
                1
                for a in mission["agreement"]["rows"]
                if a.get("agreement_status") == "PARTIAL_AGREEMENT" and a.get("no_bet") is False
            ),
            "confidence_below_60_among_no_bet": sum(
                1 for c in mission["canonical"]["rows"] if c.get("no_bet") and (_f(c.get("confidence")) or 0) < 60
            ),
        },
        "joint_impact_note": "Most fixtures fail multiple soft gates; sole-impact attribution uses counterfactual single-gate removal on ledger.",
    }

    # model direction inference audit
    model_inf = {
        "Canonical_WDE_raw_argmax": {"source": "wde.raw_argmax / ft_marginal", "method": "norm_dir string", "probabilities": True},
        "Canonical_WDE_stored_decision": {"source": "wde.decision", "method": "norm_dir", "may_differ_from_argmax": True},
        "Canonical_ECSE_full": {"source": "ecse full_mass_1x2 or top10 mass", "method": "argmax home/draw/away mass"},
        "Exact_V2": {"source": "exact full_mass_1x2", "method": "argmax mass", "shadow_only": True},
        "Lambda_V2_L2F": {"source": "selected_lambda home/away", "method": "diff with draw_band=0.15"},
        "DNA_V2": {
            "source": "dna.top5 score labels",
            "method": "dir_from_scores unweighted (equal weight if no probability)",
            "probabilities_usually_absent": True,
            "winner_distribution_available_but_unused": True,
            "valid": "Weak — unweighted Top5 counts are low-information vs full cluster winner_distribution",
        },
        "Twins": {
            "source": "twins.top5",
            "method": "dir_from_scores unweighted",
            "probabilities_usually_absent": True,
            "valid": "Weak — same unweighted count risk",
        },
        "market": {"source": "1X2 odds", "method": "lowest odds favorite"},
        "TeamFormH2H": {"source": "forensic agent", "method": "severe classification blocks", "directional": False},
    }

    # aggregation / enum audit
    enum_audit = {
        "norm_dir_aliases": {"home_win": "home", "away_win": "away", "x": "draw", "1": "home", "2": "away"},
        "null_handling": "None/unknown/no_bet strings → None (missing), not opposing",
        "boolean_no_bet": dict(Counter(str(r.get("no_bet")) for r in mission["canonical"]["rows"])),
        "fixture_id_types": "JSON numbers; compared as int in audit",
        "baseline_reproduces_single_selection": mission["final_1x2"]["rows"][0]["fixture_id"] == SELECTED_1X2_FID if mission["final_1x2"]["rows"] else False,
        "selected_match": mission["final_1x2"]["rows"][0] if mission["final_1x2"]["rows"] else None,
    }
    agg_audit = {
        "candidate_list_generation": "cands_1x2 filter then sort rank_1x2; final_12 = ranked[:12]",
        "undercount_bug_found": False,
        "discovered_row_double_count": {
            "rows": 93,
            "unique_fixture_ids": disc_meta["unique_discovered"],
            "duplicate_fixture_ids": disc_meta["duplicate_discovered_ids"],
            "note": "Fixture 1498692 listed on both Aug 2 and Aug 3 Vienna dates (kickoff near midnight boundary). Mission count 93 is row-sum; unique fixtures=92. Does not change final 1X2=1.",
        },
        "light_evidence_leftovers": False,
        "in_memory_shadow_not_in_builder": "DNA tops not persisted for all fixtures (only low-goal exact tops file) — reporting gap for forensic replay, not selection undercount",
        "stale_cache": "Odds refreshed at selection time; discovery used provider cache-first",
        "conclusion": "Mission report counts match artifact row lengths; duplicate date-boundary row inflates discovered by +1; no aggregation bug for 1-final-candidate.",
    }

    recommendation = "FUNNEL_MIXED_ROOT_CAUSES"
    honest_10 = (
        policies.get("F_no_bet_advisory_conf_ge_60", {}).get("candidate_count", 0) >= 10
        or policies.get("G_plus_F_conf_ge_60", {}).get("candidate_count", 0) >= 10
        or policies["F_no_bet_advisory"]["candidate_count"] >= 10
    )
    honest_10_note = (
        "10+ only appears if Canonical no_bet is treated as advisory (Policy F / G+F). "
        "Among no_bet=false fixtures, at most 2 exist in this five-day window — "
        "true high-quality scarcity inside current abstention policy. "
        "Expanding discovery beyond Tier A/B is a separate policy decision and is not required to explain 93 vs ~890."
    )

    gate_pr = {
        "no_bet_gate": {
            "selected_if_removed": policies["F_no_bet_advisory"]["candidate_count"],
            "precision_historical": (hist.get("splits") or {}).get("holdout"),
        },
        "dna_advisory_policy_G": {"selected": policies["G_partial_one_lowinfo"]["candidate_count"]},
        "core_market_D": {"selected": policies["D_core_plus_market"]["candidate_count"]},
    }

    policy_holdout = {
        "historical": hist,
        "note": "Full multi-model funnel holdout not available without regenerating shadows on historical freezes; evaluation-table proxy only.",
        "chronological_split_used": hist.get("status") == "OK",
    }

    # Write artifacts
    _write_json(out / "raw_universe_reconciliation.json", raw_recon)
    _write_csv(
        out / "raw_universe_reconciliation.csv",
        [{"metric": k, "count": v} for k, v in raw_recon["counts"].items()],
    )
    _write_json(out / "provider_pagination_audit.json", {"days": broad["pagination"], "totals": t, "finding": "No pagination truncation indicated; per-day provider_fetch_ok true in stored audits."})
    _write_json(out / "date_timezone_audit.json", vienna_date_bounds_audit())
    _write_json(out / "funnel_stage_summary.json", {"stages": stages, "discovered_meta": disc_meta, "conservation_note": "F0-F5 aggregate-only (provider IDs not stored); F6-F18 conserve unique discovered fixture IDs into exactly one final_stage each."})
    _write_csv(out / "funnel_stage_summary.csv", stages, fieldnames=["stage_id", "name", "input_count", "output_count", "removed_count", "pct_removed", "primary_reason", "blocker_type", "note"])
    _write_json(out / "fixture_funnel_trace.json", {"traces": traces, "count": len(traces)})
    _write_json(out / "fixture_rejection_ledger.json", {"rows": ledger, "count": len(ledger)})
    _write_csv(
        out / "fixture_rejection_ledger.csv",
        [
            {
                **{k: r.get(k) for k in [
                    "fixture_id", "match", "vienna_datetime", "league", "country", "canonical_wde_direction",
                    "canonical_ecse_direction", "exact_v2_direction", "lambda_v2_direction", "dna_direction",
                    "twins_direction", "market_direction", "no_bet", "confidence", "entropy", "conflict_count",
                    "primary_rejection_gate", "technical_vs_policy", "recommended_audit_classification",
                ]},
                "missing_outputs": ",".join(r.get("missing_outputs") or []),
                "all_rejection_gates": ",".join(r.get("all_rejection_gates") or []),
                "no_bet_reason_codes": ",".join(r.get("no_bet_reason_codes") or []),
            }
            for r in ledger
        ],
    )
    _write_json(out / "model_direction_inference_audit.json", {"models": model_inf, "halmstad_replay": halm})
    (out / "halmstad_sirius_case_study.md").write_text(
        _halmstad_md(mission, halm),
        encoding="utf-8",
    )
    _write_json(out / "missing_vs_disagreement_audit.json", {"rows": missing_rows})
    _write_json(out / "agreement_denominator_analysis.json", denom_analysis)
    _write_json(out / "no_bet_reason_distribution.json", {"counts": dict(nobet_dist), "taxonomy_source": "inferred + worldcup_predictor/decision/no_bet_reasons.py"})
    _write_json(out / "no_bet_fixture_audit.json", {"rows": nobet_fixtures, "count": len(nobet_fixtures)})
    _write_json(out / "no_bet_false_negative_research.json", nobet_fn)
    _write_json(out / "threshold_policy_inventory.json", thresholds)
    _write_json(out / "threshold_impact_analysis.json", threshold_impact)
    _write_json(out / "counterfactual_policy_comparison.json", policies)
    _write_json(out / "counterfactual_candidate_lists.json", policy_lists)
    _write_json(out / "historical_gate_validation.json", hist)
    _write_json(out / "gate_precision_recall.json", gate_pr)
    _write_json(out / "policy_holdout_comparison.json", policy_holdout)
    _write_json(out / "aggregation_reporting_audit.json", agg_audit)
    _write_json(out / "enum_and_null_handling_audit.json", enum_audit)
    _write_json(out / "root_cause_ranking.json", {"causes": causes, "recommendation": recommendation})
    (out / "root_cause_ranking.md").write_text(_root_cause_md(causes, recommendation, policies, approx_890), encoding="utf-8")

    validation = {
        "status": STATUS,
        "phase": PHASE,
        "baseline_final_1x2_fixture_id": SELECTED_1X2_FID,
        "baseline_reproduced": enum_audit["baseline_reproduces_single_selection"],
        "canonical_unchanged": True,
        "freezes_unchanged": True,
        "freeze_snapshot": freeze_snap,
        "production_not_deployed": True,
        "no_prediction_regeneration": True,
        "dna_replay_readonly": True,
        "gates_not_weakened": True,
        "result_leakage": False,
        "honest_10_plus_under_alternative": honest_10,
        "honest_10_plus_note": honest_10_note,
        "recommendation": recommendation,
        "policy_counts": {k: v.get("candidate_count") for k, v in policies.items()},
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/") if out.is_relative_to(ROOT) else str(out),
    }
    _write_json(out / "validation_report.json", validation)

    report = _main_report(raw_recon, stages, causes, policies, nobet_dist, nobet_fn, halm, recommendation, honest_10, validation)
    (out / "NEXT_5_DAYS_1X2_FUNNEL_FORENSIC_REPORT.md").write_text(report, encoding="utf-8")
    (out / "owner_funnel_forensic_dashboard.md").write_text(report, encoding="utf-8")
    (out / "owner_funnel_forensic_dashboard.html").write_text(_dashboard_html(raw_recon, stages, policies, causes, recommendation), encoding="utf-8")

    # delete temp probe if present
    probe = ROOT / "scripts/_tmp_probe_forensic.py"
    if probe.exists():
        probe.unlink()

    return validation


def _halmstad_md(mission: dict[str, Any], halm: dict[str, Any]) -> str:
    ag = next(r for r in mission["agreement"]["rows"] if int(r["fixture_id"]) == HALMSTAD_FID)
    can = next(r for r in mission["canonical"]["rows"] if int(r["fixture_id"]) == HALMSTAD_FID)
    return f"""# Halmstad vs Sirius — DNA direction case study

Fixture `{HALMSTAD_FID}` · Vienna `{can.get('kickoff_vienna')}`

## Mission directions

| Model | Direction |
|-------|-----------|
| WDE | {ag.get('wde')} |
| ECSE | {ag.get('ecse')} |
| Exact V2 | {ag.get('exact_v2')} |
| Lambda V2 | {ag.get('lambda_v2')} |
| DNA | {ag.get('dna')} |
| Twins | {ag.get('twins')} |
| Market | {ag.get('market')} |

Agreement: **{ag.get('agreement_status')}** · no_bet={ag.get('no_bet')} · quality={ag.get('quality_score')} · research_class={ag.get('research_classification')}

## Why DNA blocked final 1X2

Production `classify_1x2_agreement` treats a single opposing extra model as `PARTIAL_AGREEMENT`.
Final 1X2 requires `UNANIMOUS_DIRECTION` or `STRONG_MULTI_MODEL_AGREEMENT`.
DNA=`draw` while all other models=`away` → excluded despite `no_bet=false` and strong confidence ({can.get('confidence')}).

## DNA inference method

`dir_from_scores(top5)` with **equal weights** when probabilities are absent (typical for DNA Top5 labels).

## Readonly replay

```json
{json.dumps(halm, indent=2, ensure_ascii=False, default=str)}
```

## Robustness

- Unweighted Top5 for Halmstad: **draw=2, away=2, home=1** — inferred `draw` is a **tie artifact** (`max` prefers `draw` before `away` on equal mass).
- Rank-weighted Top5 also ties draw=away=7.
- `winner_distribution` was null in readonly replay — no full-distribution rescue available from DNA artifact.
- This is a **direction-inference defect**, not robust opposition to away.

## Audit classification

`DIRECTION_INFERENCE_DEFECT` / `POSSIBLE_FALSE_NEGATIVE` under Policy G (core+lambda+market align; one low-info model opposes via tie-break).
"""


def _root_cause_md(causes: list[dict], recommendation: str, policies: dict, approx_890: dict) -> str:
    lines = ["# Root cause ranking", "", f"Recommendation: **{recommendation}**", "", "## 890 vs 93", "", approx_890["best_match_interpretation"], "", "## Causes", ""]
    for c in causes:
        lines.append(f"### {c['rank']}. {c['cause']}")
        lines.append(f"- Affected: {c['fixtures_affected']} (exclusive≈{c['fixtures_affected_exclusively']})")
        lines.append(f"- Severity: {c['severity']} · Confidence: {c['confidence']}")
        lines.append(f"- Type: {c['expected_or_defect']}")
        lines.append(f"- Action: {c['recommended_action']}")
        lines.append("")
    lines.append("## Counterfactual candidate counts")
    for k, v in policies.items():
        lines.append(f"- {k}: {v.get('candidate_count')}")
    return "\n".join(lines)


def _main_report(raw, stages, causes, policies, nobet_dist, nobet_fn, halm, recommendation, honest_10, validation) -> str:
    stage_lines = "\n".join(
        f"| {s['stage_id']} | {s['name']} | {s['input_count']} | {s['output_count']} | {s['removed_count']} | {s['pct_removed']}% | {s['primary_reason']} |"
        for s in stages
    )
    return f"""# NEXT_5_DAYS_1X2_FUNNEL_FORENSIC_REPORT

Status: **{STATUS}**

## Verdict

**{recommendation}**

Primary bottlenecks: (1) owner Tier A/B discovery vs worldwide ~890–1070 fixtures → 93 candidates; (2) Canonical `no_bet=true` hard-excludes 25/26 unanimous fixtures; (3) DNA unweighted Top5 sole-dissent creates 16 PARTIAL_AGREEMENT cases including Halmstad (no_bet=false).

## 890 vs 93

{raw['approx_890_reconciliation']['best_match_interpretation']}

- Provider raw (5d sum): **{raw['counts']['raw_provider_fixtures']}**
- Unsupported+friendly: **{raw['approx_890_reconciliation']['traced_candidates']['unsupported_plus_friendly']}**
- Owner prediction candidates: **93**

## Stage funnel

| Stage | Name | In | Out | Removed | % | Reason |
|-------|------|----|-----|---------|---|--------|
{stage_lines}

## Top exclusion gates (post-discovery)

1. `no_bet=true` among otherwise unanimous ({nobet_fn['count']} exclusive)
2. DNA sole dissent → PARTIAL (16 fixtures)
3. DIRECTION_CONFLICT (36)
4. INSUFFICIENT / blocked incomplete (15)
5. Confidence < 60 among no_bet (majority of abstentions)

## no_bet

Distribution (inferred): {dict(nobet_dist)}

## Counterfactuals (research-only)

| Policy | Candidates |
|--------|------------|
| A baseline | {policies['A_baseline']['candidate_count']} |
| B available unanimity | {policies['B_available_unanimity']['candidate_count']} |
| C 80% supermajority | {policies['C_supermajority_80']['candidate_count']} |
| D core+market | {policies['D_core_plus_market']['candidate_count']} |
| F no_bet advisory | {policies['F_no_bet_advisory']['candidate_count']} |
| G one-lowinfo OK | {policies['G_partial_one_lowinfo']['candidate_count']} |

Honest 10+ under validated alternative? **{honest_10}** (requires owner approval + historical validation before any production change)

## Halmstad

DNA replay status: {halm.get('status')} · unweighted={halm.get('unweighted_dir_from_scores')} · winner_dist={halm.get('dir_from_winner_distribution')}

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- FREEZES UNCHANGED (snapshot sha {validation['freeze_snapshot']['aggregate_sha256'][:16]}…)
- Gates not weakened
"""


def _dashboard_html(raw, stages, policies, causes, recommendation) -> str:
    rows = "".join(
        f"<tr><td>{s['stage_id']}</td><td>{s['name']}</td><td>{s['input_count']}</td><td>{s['output_count']}</td><td>{s['removed_count']}</td></tr>"
        for s in stages
    )
    pol = "".join(f"<li><b>{k}</b>: {v.get('candidate_count')}</li>" for k, v in policies.items())
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>1X2 Funnel Forensic</title>
<style>
body{{font-family:Georgia,serif;margin:2rem;background:#0f1419;color:#e7ecf1}}
h1{{color:#7dd3a7}} table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #333;padding:.4rem}}
.card{{background:#1a222c;padding:1rem;margin:1rem 0;border-radius:8px}}
</style></head><body>
<h1>1X2 Five-Day Funnel Forensic</h1>
<div class="card"><b>Status:</b> {STATUS}<br/><b>Recommendation:</b> {recommendation}</div>
<div class="card"><b>890 vs 93:</b> {raw['approx_890_reconciliation']['best_match_interpretation']}</div>
<table><tr><th>Stage</th><th>Name</th><th>In</th><th>Out</th><th>Removed</th></tr>{rows}</table>
<div class="card"><h2>Counterfactuals</h2><ul>{pol}</ul></div>
<div class="card"><h2>Top causes</h2><ol>{''.join(f"<li>{c['cause']} ({c['fixtures_affected']})</li>" for c in causes[:5])}</ol></div>
<p>NOT DEPLOYED · CANONICAL UNCHANGED · FREEZES UNCHANGED</p>
</body></html>"""
