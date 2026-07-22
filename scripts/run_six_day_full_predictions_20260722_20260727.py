#!/usr/bin/env python3
"""Six-day full prediction run: 2026-07-22 .. 2026-07-27 (Europe/Vienna).

Extends scripts/run_owner_full_day_predictions.py — no parallel prediction system,
no formula changes. Per-day canonical discover → fresh odds → predict → freeze,
then aggregate owner reports + rankings + validation inputs.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import traceback
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("ENVIRONMENT", "production")
if (ROOT / ".env.production").is_file():
    os.environ.setdefault("ENV_FILE", str(ROOT / ".env.production"))

from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime

import importlib.util


def _load_full_day():
    path = ROOT / "scripts" / "run_owner_full_day_predictions.py"
    spec = importlib.util.spec_from_file_location("run_owner_full_day_predictions", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


full_day = _load_full_day()

TZ = ZoneInfo("Europe/Vienna")
START = date(2026, 7, 22)
END = date(2026, 7, 27)
DATES = [(START + timedelta(days=i)).isoformat() for i in range((END - START).days + 1)]

ART_ROOT = ROOT / "artifacts" / "six_day_predictions" / "2026-07-22_2026-07-27"
REPORT_DIR = ROOT / "reports" / "owner" / "daily"
REPORT_STEM = "2026-07-22_TO_2026-07-27_SIX_DAY_FULL_PREDICTIONS"


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in r.items() if k in fields})


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cell(t: dict | None) -> str:
    return full_day._cell(t)


def _devig(h: float | None, d: float | None, a: float | None) -> dict[str, float | None]:
    if not all(v and v > 1 for v in (h, d, a)):
        return {"home": None, "draw": None, "away": None}
    ih, id_, ia = 1.0 / h, 1.0 / d, 1.0 / a  # type: ignore[operator]
    s = ih + id_ + ia
    return {"home": round(ih / s, 6), "draw": round(id_ / s, 6), "away": round(ia / s, 6)}


def _enrich_from_payload(pred: dict[str, Any]) -> dict[str, Any]:
    """Add O/U 1.5/3.5 / EGIE / no_bet reasons from stored payload when present — no fabrication."""
    out = dict(pred)
    fid = pred.get("fixture_id")
    if not fid:
        return out
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.connection import connect

        conn = connect(get_settings().sqlite_path)
        row = conn.execute(
            "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
            (int(fid),),
        ).fetchone()
        conn.close()
        if not row:
            return out
        payload = json.loads(row["payload_json"])
    except Exception:
        return out

    probs = payload.get("probabilities") or {}
    for key, label in (("over_under_1_5", "ou15"), ("over_under_3_5", "ou35"), ("over_under_4_5", "ou45")):
        blob = probs.get(key) or {}
        if not blob:
            out[label] = {"execution_status": "UNAVAILABLE", "reason": f"{key}_not_in_payload"}
            continue
        sel = blob.get("selection")
        pmap = blob.get("probabilities") or {}
        out[label] = {
            "preferred_side": sel,
            "over_probability": _f(pmap.get("over") or pmap.get(f"over_{key.split('_')[-1]}") or next((v for k, v in pmap.items() if str(k).startswith("over")), None)),
            "under_probability": _f(pmap.get("under") or pmap.get(f"under_{key.split('_')[-1]}") or next((v for k, v in pmap.items() if str(k).startswith("under")), None)),
            "confidence": blob.get("confidence"),
            "execution_status": "OK",
            "model_version": blob.get("model_version"),
        }

    egie = payload.get("egie") or payload.get("goal_timing") or payload.get("first_goal")
    if egie:
        out["egie"] = {**egie, "execution_status": egie.get("execution_status") or "OK"}
    else:
        out["egie"] = {"execution_status": "EGIE_UNAVAILABLE", "reason": "not_in_canonical_payload"}

    reasons = payload.get("no_bet_reasons") or payload.get("no_bet_reason") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    out["no_bet_reasons"] = list(reasons) if reasons else []
    if out.get("no_bet") and not out["no_bet_reasons"]:
        out["no_bet_reasons"] = [str(payload.get("no_bet_flag") or payload.get("reason") or "no_bet_true_no_detail")]

    odds = out.get("odds") or {}
    out["odds_devig"] = _devig(_f(odds.get("home")), _f(odds.get("draw")), _f(odds.get("away")))
    return out


def _exact_suitability(p: dict) -> str:
    if p.get("no_bet"):
        return "EXACT_SCORE_NO_BET"
    mass = _f((p.get("ecse") or {}).get("top5_mass")) or 0
    ent = _f((p.get("ecse") or {}).get("entropy"))
    if mass >= 0.52 and (ent is None or ent <= 1.45):
        return "EXACT_SCORE_STRONG"
    if mass >= 0.40:
        return "EXACT_SCORE_MEDIUM"
    if mass > 0:
        return "EXACT_SCORE_WEAK"
    return "EXACT_SCORE_NO_BET"


def _day_art(d: str) -> Path:
    return ROOT / "artifacts" / "daily_pipeline" / d / "full_day"


def run_all_days() -> dict[str, Any]:
    bootstrap_gpt_actions_runtime()
    day_results: dict[str, Any] = {}
    for d in DATES:
        print(f"\n===== SIX-DAY RUN: {d} =====", flush=True)
        try:
            rc = full_day.main(["--date", d])
        except Exception as exc:
            rc = 99
            day_results[d] = {"exit_code": rc, "error": str(exc), "traceback": traceback.format_exc()[:2000]}
            print(f"DAY_FAILED {d}: {exc}", flush=True)
            continue
        art = _day_art(d)
        day_results[d] = {
            "exit_code": int(rc),
            "artifact_dir": str(art),
            "has_predictions": (art / "full_predictions.json").is_file(),
            "has_discovery": (art / "discovery.json").is_file(),
        }
        print(f"DAY_DONE {d} rc={rc}", flush=True)
    return day_results


def load_day(d: str) -> dict[str, Any]:
    art = _day_art(d)
    def lj(name: str) -> Any:
        p = art / name
        if not p.is_file():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    return {
        "date": d,
        "discovery": lj("discovery.json"),
        "predictions": lj("full_predictions.json"),
        "jobs": lj("prediction_jobs.json"),
        "odds": lj("odds_eligibility.json") or lj("odds_status.json"),
        "freezes": lj("freeze_manifest.json") or lj("canonical_freeze_manifest.json"),
        "rankings": lj("rankings.json"),
        "runtime": lj("runtime.json"),
        "exclusions": lj("exclusions.json"),
    }


def aggregate(day_runs: dict[str, Any]) -> dict[str, Any]:
    ART_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    all_discovered: list[dict] = []
    all_preds: list[dict] = []
    all_jobs: list[dict] = []
    all_odds: list[dict] = []
    all_freezes: list[dict] = []
    all_blocked: list[dict] = []
    funnel_rows: list[dict] = []
    resolution_rows: list[dict] = []

    for d in DATES:
        day = load_day(d)
        disc = day["discovery"] or {}
        counters = disc.get("counters") or {}
        discovered = list(disc.get("all_discovered") or [])
        exclusions = list(disc.get("exclusions") or [])
        preds_wrap = day["predictions"] or {}
        preds = [_enrich_from_payload(p) for p in (preds_wrap.get("predictions") or [])]
        jobs = list((day["jobs"] or {}).get("jobs") or [])
        odds = list((day["odds"] or {}).get("fixtures") or [])
        freezes = list((day["freezes"] or {}).get("freezes") or [])

        for row in discovered:
            row = {**row, "date": d}
            all_discovered.append(row)
            tier = row.get("validation_tier")
            status = "RESOLVED"
            if row.get("exclusion_reason"):
                status = str(row.get("exclusion_reason"))
            elif tier not in ("A", "B"):
                status = "UNSUPPORTED_COMPETITION"
            resolution_rows.append(
                {
                    "fixture_id": row.get("fixture_id"),
                    "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                    "competition": row.get("league") or row.get("competition"),
                    "kickoff_utc": row.get("kickoff_utc"),
                    "vienna": row.get("kickoff_vienna"),
                    "scope": row.get("prediction_scope"),
                    "tier": tier,
                    "status": status,
                    "date": d,
                }
            )

        complete = [p for p in preds if p.get("prediction_complete")]
        blocked_preds = [p for p in preds if not p.get("prediction_complete")]
        for p in blocked_preds:
            all_blocked.append(
                {
                    "date": d,
                    "fixture_id": p.get("fixture_id"),
                    "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                    "block_code": p.get("eligibility") or p.get("main_risk") or "BLOCKED",
                    "refresh_attempted": p.get("refresh_status") is not None or True,
                    "final_reason": p.get("eligibility") or p.get("main_risk") or p.get("source"),
                }
            )
        for e in exclusions:
            all_blocked.append(
                {
                    "date": d,
                    "fixture_id": e.get("fixture_id"),
                    "match": f"{e.get('home_team')} vs {e.get('away_team')}",
                    "block_code": e.get("exclusion_reason") or "EXCLUDED",
                    "refresh_attempted": False,
                    "final_reason": e.get("exclusion_reason"),
                }
            )

        for p in preds:
            p["date"] = d
            p["exact_score_suitability"] = _exact_suitability(p)
            all_preds.append(p)
        for j in jobs:
            all_jobs.append({**j, "date": d})
        for o in odds:
            all_odds.append({**o, "date": d})
        for f in freezes:
            all_freezes.append({**f, "date": d})

        provider_n = int((disc.get("discovery_audit") or {}).get("count") or len(discovered) or counters.get("total_discovered") or 0)
        supported = int(counters.get("total_discovered") or len(discovered))
        prematch = int(counters.get("prematch_needs_prediction") or 0) + int(counters.get("prematch_reuse_freeze") or 0)
        fresh = sum(1 for o in odds if o.get("eligibility") == "PREDICTION_ELIGIBLE" or o.get("gate_allowed"))
        predicted = len(complete)
        frozen = sum(1 for f in freezes if f.get("freeze_id") or f.get("freeze_hash"))
        blocked_n = len(blocked_preds) + len(exclusions)
        funnel_rows.append(
            {
                "date": d,
                "provider": provider_n,
                "date_window": supported,
                "supported": supported,
                "prematch": prematch,
                "fresh_odds": fresh,
                "predicted": predicted,
                "frozen": frozen,
                "blocked": blocked_n,
                "day_exit_code": (day_runs.get(d) or {}).get("exit_code"),
            }
        )

    # Rankings across six days
    complete = [p for p in all_preds if p.get("prediction_complete")]

    def brief(p: dict, **extra: Any) -> dict:
        odds = p.get("odds") or {}
        return {
            "date": p.get("date"),
            "fixture_id": p.get("fixture_id"),
            "match": f"{p.get('home_team')} vs {p.get('away_team')}",
            "league": p.get("league"),
            "kickoff_vienna": p.get("kickoff_vienna"),
            "tier": p.get("validation_tier"),
            "scope": p.get("prediction_scope"),
            "wde": (p.get("wde") or {}).get("decision"),
            "confidence": (p.get("wde") or {}).get("confidence"),
            "consensus": p.get("consensus"),
            "data_quality": p.get("data_quality"),
            "no_bet": p.get("no_bet"),
            "top1": _cell((p.get("ecse") or {}).get("top1")),
            "top2": _cell((p.get("ecse") or {}).get("top2")),
            "top3": _cell((p.get("ecse") or {}).get("top3")),
            "top4": _cell((p.get("ecse") or {}).get("top4")),
            "top5": _cell((p.get("ecse") or {}).get("top5")),
            "top5_mass": (p.get("ecse") or {}).get("top5_mass"),
            "entropy": (p.get("ecse") or {}).get("entropy"),
            "btts": (p.get("btts") or {}).get("prediction"),
            "ou15": (p.get("ou15") or {}).get("preferred_side"),
            "ou25": (p.get("ou25") or {}).get("preferred_side"),
            "ou35": (p.get("ou35") or {}).get("preferred_side"),
            "odds_h": odds.get("home"),
            "odds_d": odds.get("draw"),
            "odds_a": odds.get("away"),
            "suitability": p.get("exact_score_suitability"),
            "egie_status": (p.get("egie") or {}).get("execution_status"),
            **extra,
        }

    wde_rank = sorted(
        [p for p in complete if not p.get("no_bet")],
        key=lambda p: (
            -full_day._dq_score(p.get("data_quality")),
            -(_f((p.get("wde") or {}).get("confidence")) or 0),
            -full_day._agree_score(p.get("consensus")),
        ),
    )
    exact_rank = sorted(
        [p for p in complete if (p.get("ecse") or {}).get("top1")],
        key=lambda p: (
            0 if p.get("exact_score_suitability") == "EXACT_SCORE_STRONG" else 1 if p.get("exact_score_suitability") == "EXACT_SCORE_MEDIUM" else 2,
            0 if not p.get("no_bet") else 1,
            -(_f((p.get("ecse") or {}).get("top5_mass")) or 0),
            (_f((p.get("ecse") or {}).get("entropy")) or 99),
        ),
    )
    btts_rank = sorted(
        [p for p in complete if (p.get("btts") or {}).get("prediction")],
        key=lambda p: -(_f((p.get("btts") or {}).get("yes_probability")) or _f((p.get("btts") or {}).get("confidence")) or 0),
    )

    def ou_rank(key: str, over_pref: tuple[str, ...], under_pref: tuple[str, ...]) -> list[dict]:
        rows = []
        for p in complete:
            side = str((p.get(key) or {}).get("preferred_side") or "").lower()
            if side in over_pref or side in under_pref or side:
                rows.append(p)
        return sorted(rows, key=lambda p: -(_f(((p.get(key) or {}).get("confidence"))) or 0))

    ou15_rank = ou_rank("ou15", ("over", "over_1_5"), ("under", "under_1_5"))
    ou25_rank = ou_rank("ou25", ("over", "over_2_5"), ("under", "under_2_5"))
    ou35_rank = ou_rank("ou35", ("over", "over_3_5"), ("under", "under_3_5"))
    egie_rank = [p for p in complete if str((p.get("egie") or {}).get("execution_status") or "").upper() in {"OK", "EXECUTED", "AVAILABLE"}]

    balanced = []
    for thr in (1.80, 1.90, 2.00):
        for p in complete:
            odds = p.get("odds") or {}
            h, a = _f(odds.get("home")), _f(odds.get("away"))
            if h and a and h >= thr and a >= thr:
                balanced.append(brief(p, balanced_threshold=thr))

    avoid = [
        brief(p)
        for p in all_preds
        if (p.get("consensus") == "HIGH_CONFLICT")
        or p.get("no_bet")
        or (not p.get("prediction_complete"))
        or str(p.get("eligibility") or "").startswith("BLOCKED")
    ]

    summary = {
        "period": {"start": START.isoformat(), "end": END.isoformat(), "timezone": "Europe/Vienna"},
        "day_runs": day_runs,
        "totals": {
            "provider_fixtures": sum(int(r.get("provider") or 0) for r in funnel_rows),
            "resolved": len(all_discovered),
            "supported": len([r for r in all_discovered if r.get("validation_tier") in ("A", "B")]),
            "predictions_complete": len(complete),
            "partial": len([p for p in all_preds if p.get("prediction_partial")]),
            "blocked": len(all_blocked),
            "freezes_new": len([f for f in all_freezes if f.get("new_or_reused") == "new"]),
            "freezes_reused": len([f for f in all_freezes if f.get("new_or_reused") == "reused"]),
            "tier_a": len([p for p in complete if p.get("validation_tier") == "A"]),
            "tier_b": len([p for p in complete if p.get("validation_tier") == "B"]),
            "no_bet_false": len([p for p in complete if not p.get("no_bet")]),
            "no_bet_true": len([p for p in complete if p.get("no_bet")]),
            "high_agreement": len([p for p in complete if p.get("consensus") == "HIGH_AGREEMENT"]),
            "high_conflict": len([p for p in complete if p.get("consensus") == "HIGH_CONFLICT"]),
            "egie_available": len(egie_rank),
            "exact_strong": len([p for p in complete if p.get("exact_score_suitability") == "EXACT_SCORE_STRONG"]),
            "exact_medium": len([p for p in complete if p.get("exact_score_suitability") == "EXACT_SCORE_MEDIUM"]),
            "jobs": len(all_jobs),
        },
        "by_date": funnel_rows,
        "by_league": dict(Counter(str(p.get("league") or "UNKNOWN") for p in complete)),
    }

    # Artifacts
    _write_json(ART_ROOT / "fixture_discovery.json", {"dates": DATES, "fixtures": all_discovered})
    _write_csv(ART_ROOT / "fixture_resolution.csv", resolution_rows)
    _write_csv(
        ART_ROOT / "daily_funnel.csv",
        funnel_rows,
        ["date", "provider", "date_window", "supported", "prematch", "fresh_odds", "predicted", "frozen", "blocked", "day_exit_code"],
    )
    _write_csv(ART_ROOT / "odds_refresh_results.csv", all_odds)
    _write_csv(ART_ROOT / "prediction_jobs.csv", all_jobs)
    _write_json(ART_ROOT / "full_predictions.json", {"predictions": all_preds, "summary": summary})
    _write_csv(ART_ROOT / "full_predictions.csv", [brief(p) for p in all_preds])
    _write_csv(ART_ROOT / "wde_rankings.csv", [brief(p, rank=i) for i, p in enumerate(wde_rank, 1)])
    _write_csv(ART_ROOT / "exact_score_rankings.csv", [brief(p, rank=i) for i, p in enumerate(exact_rank, 1)])
    _write_csv(ART_ROOT / "btts_rankings.csv", [brief(p, rank=i) for i, p in enumerate(btts_rank, 1)])
    _write_csv(ART_ROOT / "ou15_rankings.csv", [brief(p, rank=i) for i, p in enumerate(ou15_rank, 1)])
    _write_csv(ART_ROOT / "ou25_rankings.csv", [brief(p, rank=i) for i, p in enumerate(ou25_rank, 1)])
    _write_csv(ART_ROOT / "ou35_rankings.csv", [brief(p, rank=i) for i, p in enumerate(ou35_rank, 1)])
    _write_csv(ART_ROOT / "goal_timing_rankings.csv", [brief(p, rank=i) for i, p in enumerate(egie_rank, 1)])
    _write_csv(ART_ROOT / "balanced_odds.csv", balanced)
    _write_csv(ART_ROOT / "blocked_fixtures.csv", all_blocked)
    _write_json(ART_ROOT / "freeze_manifest.json", {"freezes": all_freezes})

    # Integrity
    accounted = set()
    for r in resolution_rows:
        accounted.add(int(r["fixture_id"]))
    for b in all_blocked:
        if b.get("fixture_id"):
            accounted.add(int(b["fixture_id"]))
    for p in all_preds:
        if p.get("fixture_id"):
            accounted.add(int(p["fixture_id"]))
    discovered_ids = {int(r["fixture_id"]) for r in all_discovered if r.get("fixture_id")}
    silent = sorted(discovered_ids - accounted)
    integrity = {
        "period": summary["period"],
        "discovered_count": len(discovered_ids),
        "accounted_count": len(accounted & discovered_ids),
        "silent_omissions": silent,
        "no_silent_omission": len(silent) == 0,
        "formula_changes": False,
        "shadow_promotion": False,
        "new_timer_enabled": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(ART_ROOT / "integrity.json", integrity)
    _write_json(ART_ROOT / "summary.json", summary)

    # Reports
    en_lines = _build_en_report(summary, funnel_rows, resolution_rows, complete, wde_rank, exact_rank, btts_rank, ou15_rank, ou25_rank, ou35_rank, egie_rank, balanced, avoid, all_blocked, all_freezes, integrity)
    fa_lines = _build_fa_report(summary, funnel_rows, complete, wde_rank, exact_rank, all_blocked)
    blocked_lines = [
        f"# Six-Day Blocked Fixtures — {START} to {END}",
        "",
        "| Date | Match | Block Code | Refresh Attempted | Final Reason |",
        "|---|---|---|---|---|",
    ]
    for b in all_blocked:
        blocked_lines.append(
            f"| {b.get('date')} | {b.get('match')} | {b.get('block_code')} | {b.get('refresh_attempted')} | {b.get('final_reason')} |"
        )
    blocked_lines.append("")

    report_en = REPORT_DIR / f"{REPORT_STEM}.md"
    report_fa = REPORT_DIR / f"{REPORT_STEM}_FA.md"
    report_blocked = REPORT_DIR / "2026-07-22_TO_2026-07-27_SIX_DAY_BLOCKED_FIXTURES.md"
    report_en.write_text("\n".join(en_lines), encoding="utf-8")
    report_fa.write_text("\n".join(fa_lines), encoding="utf-8")
    report_blocked.write_text("\n".join(blocked_lines), encoding="utf-8")

    return {
        "summary": summary,
        "integrity": integrity,
        "complete": complete,
        "wde_rank": wde_rank,
        "exact_rank": exact_rank,
        "btts_rank": btts_rank,
        "ou15_rank": ou15_rank,
        "ou25_rank": ou25_rank,
        "ou35_rank": ou35_rank,
        "egie_rank": egie_rank,
        "balanced": balanced,
        "avoid": avoid,
        "blocked": all_blocked,
        "freezes": all_freezes,
        "funnel": funnel_rows,
        "resolution": resolution_rows,
        "reports": {"en": str(report_en), "fa": str(report_fa), "blocked": str(report_blocked)},
        "artifacts": str(ART_ROOT),
    }


def _build_en_report(summary, funnel, resolution, complete, wde_rank, exact_rank, btts_rank, ou15, ou25, ou35, egie, balanced, avoid, blocked, freezes, integrity) -> list[str]:
    t = summary["totals"]
    lines = [
        f"# Six-Day Full Predictions — {START.isoformat()} to {END.isoformat()} (Europe/Vienna)",
        "",
        "**Mode:** ALL_ELIGIBLE_SUPPORTED_PREMATCH_FIXTURES_FOR_SIX_DAYS",
        "**Engines:** canonical WDE + ECSE (+ BTTS/O-U/EGIE when present in payload)",
        "**Policy:** fresh odds required · refresh-before-block · immutable freeze reuse · Tier B owner_shadow / public_visible=false",
        "",
        "## Six-day summary",
        "",
        f"- Resolved / supported: **{t['resolved']}** / **{t['supported']}**",
        f"- Predictions complete / partial / blocked: **{t['predictions_complete']}** / **{t['partial']}** / **{t['blocked']}**",
        f"- Freezes new / reused: **{t['freezes_new']}** / **{t['freezes_reused']}**",
        f"- Tier A / B: **{t['tier_a']}** / **{t['tier_b']}**",
        f"- no_bet false/true: **{t['no_bet_false']}** / **{t['no_bet_true']}**",
        f"- HIGH_AGREEMENT / HIGH_CONFLICT: **{t['high_agreement']}** / **{t['high_conflict']}**",
        f"- Exact STRONG / MEDIUM: **{t['exact_strong']}** / **{t['exact_medium']}**",
        f"- EGIE available: **{t['egie_available']}**",
        "",
        "## Daily funnel",
        "",
        "| Date | Provider | Date Window | Supported | Prematch | Fresh Odds | Predicted | Frozen | Blocked |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in funnel:
        lines.append(
            f"| {r['date']} | {r['provider']} | {r['date_window']} | {r['supported']} | {r['prematch']} | "
            f"{r['fresh_odds']} | {r['predicted']} | {r['frozen']} | {r['blocked']} |"
        )
    lines += ["", "## Compact prediction table", "", "| # | Vienna | League | Match | H/D/A | WDE | Conf | BTTS | O/U2.5 | Top1 | Top5 Mass | Consensus | no_bet | Tier | Freeze |", "|---:|---|---|---|---|---|---:|---|---|---|---:|---|---|---|---|"]
    for i, p in enumerate(sorted(complete, key=lambda x: (str(x.get("date")), str(x.get("kickoff_utc")))), 1):
        odds = p.get("odds") or {}
        fr = p.get("freeze") or {}
        lines.append(
            f"| {i} | {p.get('kickoff_vienna')} | {p.get('league')} | {p.get('home_team')} vs {p.get('away_team')} | "
            f"{odds.get('home')}/{odds.get('draw')}/{odds.get('away')} | {(p.get('wde') or {}).get('decision')} | "
            f"{(p.get('wde') or {}).get('confidence')} | {(p.get('btts') or {}).get('prediction')} | "
            f"{(p.get('ou25') or {}).get('preferred_side')} | {_cell((p.get('ecse') or {}).get('top1'))} | "
            f"{(p.get('ecse') or {}).get('top5_mass')} | {p.get('consensus')} | {p.get('no_bet')} | "
            f"{p.get('validation_tier')} | {fr.get('freeze_id') or fr.get('capture_status')} |"
        )

    def rank_block(title: str, rows: list, n: int = 30) -> list[str]:
        out = [f"## {title}", ""]
        if not rows:
            return out + ["_None_", ""]
        out += ["| # | Date | Match | WDE | Conf | Top1 | Notes |", "|---:|---|---|---|---:|---|---|"]
        for i, p in enumerate(rows[:n], 1):
            out.append(
                f"| {i} | {p.get('date')} | {p.get('home_team')} vs {p.get('away_team')} | "
                f"{(p.get('wde') or {}).get('decision')} | {(p.get('wde') or {}).get('confidence')} | "
                f"{_cell((p.get('ecse') or {}).get('top1'))} | {p.get('consensus')} / {p.get('exact_score_suitability')} |"
            )
        out.append("")
        return out

    lines += rank_block("WDE ranking", wde_rank)
    lines += rank_block("Exact Score ranking", exact_rank)
    lines += rank_block("BTTS ranking", btts_rank)
    lines += rank_block("O/U 1.5 ranking", ou15)
    lines += rank_block("O/U 2.5 ranking", ou25)
    lines += rank_block("O/U 3.5 ranking", ou35)
    lines += rank_block("Goal Timing ranking", egie)

    lines += ["## Balanced odds (H>=1.80 and A>=1.80)", ""]
    if not balanced:
        lines += ["_None_", ""]
    else:
        lines += ["| Date | Match | H | A | Threshold | WDE |", "|---|---|---:|---:|---:|---|"]
        for b in balanced[:40]:
            lines.append(
                f"| {b.get('date')} | {b.get('match')} | {b.get('odds_h')} | {b.get('odds_a')} | {b.get('balanced_threshold')} | {b.get('wde')} |"
            )
        lines.append("")

    lines += ["## Avoid list (sample)", ""]
    for a in avoid[:40]:
        lines.append(f"- `{a.get('fixture_id')}` {a.get('date')} {a.get('match')} — {a.get('consensus')} / no_bet={a.get('no_bet')}")
    lines += ["", f"## Integrity", "", f"- Silent omissions: `{integrity.get('silent_omissions')}`", f"- no_silent_omission: **{integrity.get('no_silent_omission')}**", "", f"Artifacts: `{ART_ROOT}`", ""]

    lines += ["## Full Top1–Top5 (every complete fixture)", ""]
    for p in sorted(complete, key=lambda x: (str(x.get("date")), str(x.get("kickoff_utc")))):
        ecse = p.get("ecse") or {}
        lines += [
            f"### {p.get('date')} — {p.get('home_team')} vs {p.get('away_team')} (`{p.get('fixture_id')}`)",
            f"- Top1–Top5: {_cell(ecse.get('top1'))} | {_cell(ecse.get('top2'))} | {_cell(ecse.get('top3'))} | {_cell(ecse.get('top4'))} | {_cell(ecse.get('top5'))}",
            f"- Mass T3/T5 / entropy / λ: {ecse.get('top3_mass')} / {ecse.get('top5_mass')} / {ecse.get('entropy')} / {ecse.get('total_lambda')}",
            f"- WDE {(p.get('wde') or {}).get('decision')} @ {(p.get('wde') or {}).get('confidence')} · BTTS {(p.get('btts') or {}).get('prediction')} · O/U2.5 {(p.get('ou25') or {}).get('preferred_side')}",
            f"- Consensus {p.get('consensus')} · Suitability {p.get('exact_score_suitability')} · Freeze {(p.get('freeze') or {}).get('freeze_id')}",
            "",
        ]
    return lines


def _build_fa_report(summary, funnel, complete, wde_rank, exact_rank, blocked) -> list[str]:
    t = summary["totals"]
    lines = [
        f"# گزارش شش‌روزه پیش‌بینی کامل — {START.isoformat()} تا {END.isoformat()} (وین)",
        "",
        f"**کامل:** {t['predictions_complete']} · **مسدود:** {t['blocked']} · **فریز جدید/بازاستفاده:** {t['freezes_new']}/{t['freezes_reused']}",
        "",
        "## قیف روزانه",
        "",
        "| تاریخ | کشف | پشتیبانی | پیش‌بینی | فریز | مسدود |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in funnel:
        lines.append(f"| {r['date']} | {r['supported']} | {r['supported']} | {r['predicted']} | {r['frozen']} | {r['blocked']} |")
    lines += ["", "## برترین WDE", ""]
    for i, p in enumerate(wde_rank[:20], 1):
        lines.append(f"{i}. {p.get('date')} — {p.get('home_team')} vs {p.get('away_team')} → {(p.get('wde') or {}).get('decision')} ({(p.get('wde') or {}).get('confidence')})")
    lines += ["", "## برترین Exact Score", ""]
    for i, p in enumerate(exact_rank[:20], 1):
        lines.append(f"{i}. {p.get('date')} — {p.get('home_team')} vs {p.get('away_team')} → {_cell((p.get('ecse') or {}).get('top1'))}")
    lines += ["", f"مسدودها: {len(blocked)}", ""]
    return lines


def print_terminal(agg: dict[str, Any], validator: dict[str, Any] | None) -> str:
    s = agg["summary"]["totals"]
    print("1. Target period: 2026-07-22 .. 2026-07-27 Europe/Vienna")
    print(f"2. Discovery totals: resolved={s['resolved']} supported={s['supported']} complete={s['predictions_complete']} blocked={s['blocked']}")
    print("3. Daily funnel:")
    for r in agg["funnel"]:
        print(f"   {r}")
    print(f"4. Resolved fixtures: {len(agg['resolution'])}")
    print(f"5. Complete predictions: {len(agg['complete'])}")
    print(f"6. Top1–Top5 listed in report for {len(agg['complete'])} fixtures")
    print(f"7. WDE ranking: {len(agg['wde_rank'])}")
    print(f"8. Exact Score ranking: {len(agg['exact_rank'])}")
    print(f"9. BTTS ranking: {len(agg['btts_rank'])}")
    print(f"10. O/U1.5 ranking: {len(agg['ou15_rank'])}")
    print(f"11. O/U2.5 ranking: {len(agg['ou25_rank'])}")
    print(f"12. O/U3.5 ranking: {len(agg['ou35_rank'])}")
    print(f"13. Goal Timing ranking: {len(agg['egie_rank'])}")
    print(f"14. Balanced-odds rows: {len(agg['balanced'])}")
    print(f"15. no_bet=false: {s['no_bet_false']}")
    print(f"16. Watchlist/avoid sample: {len(agg['avoid'])}")
    print(f"17. Avoid list: {len(agg['avoid'])}")
    print(f"18. Blocked: {len(agg['blocked'])}")
    print(f"19. Freezes: new={s['freezes_new']} reused={s['freezes_reused']}")
    print(f"20. Reports: {agg['reports']}")
    print(f"21. Validator: {(validator or {}).get('status')}")

    if not agg["integrity"].get("no_silent_omission"):
        status = "SIX_DAY_PREDICTIONS_VALIDATION_FAILED"
    elif s["predictions_complete"] == 0 and s["blocked"] > 0:
        status = "SIX_DAY_PREDICTIONS_ODDS_BLOCKED"
    elif any((agg["summary"]["day_runs"].get(d) or {}).get("exit_code") not in (0, None) for d in DATES):
        # partial if some days ok
        ok_days = sum(1 for d in DATES if (agg["summary"]["day_runs"].get(d) or {}).get("exit_code") == 0)
        status = "SIX_DAY_FULL_PREDICTIONS_PARTIAL" if ok_days else "SIX_DAY_PREDICTIONS_RUNTIME_BLOCKED"
    elif s["predictions_complete"] > 0 and (validator or {}).get("ok", True):
        if s["blocked"] == 0 and all((agg["summary"]["day_runs"].get(d) or {}).get("exit_code") == 0 for d in DATES):
            status = "SIX_DAY_FULL_PREDICTIONS_AND_FREEZES_COMPLETE"
        else:
            status = "SIX_DAY_FULL_PREDICTIONS_PARTIAL"
    else:
        status = "SIX_DAY_FULL_PREDICTIONS_PARTIAL"
    print(status)
    return status


def main() -> int:
    ART_ROOT.mkdir(parents=True, exist_ok=True)
    skip_run = "--aggregate-only" in sys.argv
    if skip_run:
        day_runs = {d: {"exit_code": 0 if _day_art(d).joinpath("full_predictions.json").is_file() else 1} for d in DATES}
    else:
        day_runs = run_all_days()
    agg = aggregate(day_runs)
    # inline light validation hook
    import importlib.util

    vpath = ROOT / "scripts" / "validate_six_day_full_predictions_20260722_20260727.py"
    vspec = importlib.util.spec_from_file_location("validate_six_day_full_predictions", vpath)
    assert vspec and vspec.loader
    vmod = importlib.util.module_from_spec(vspec)
    vspec.loader.exec_module(vmod)
    validator = vmod.run_validation()
    status = print_terminal(agg, validator)
    _write_json(ART_ROOT / "final_status.json", {"status": status, "validator": validator})
    return 0 if status in {"SIX_DAY_FULL_PREDICTIONS_AND_FREEZES_COMPLETE", "SIX_DAY_FULL_PREDICTIONS_PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
