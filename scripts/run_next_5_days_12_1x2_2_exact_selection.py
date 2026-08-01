#!/usr/bin/env python3
"""
NEXT_5_DAYS_12_1X2_PLUS_2_LOW_GOAL_EXACT_SELECTION
==================================================

Controlled five-day (Vienna) multi-model selection mission.
Reuses owner full-day discovery/odds/canonical/freeze; enriches with
read-only research shadows. Exact V2 remains shadow-only. No promotion /
no routing / no Portfolio-Similarity-OOD selection layers.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TZ = ZoneInfo("Europe/Vienna")
FI = ROOT / "data" / "football_intelligence.db"
DEFAULT_DATES = ["2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
PHASE = "NEXT_5_DAYS_12_1X2_PLUS_2_LOW_GOAL_EXACT_SELECTION"
STATUS_READY = "NEXT_5_DAYS_12_1X2_PLUS_2_LOW_GOAL_EXACT_READY"
STATUS_PARTIAL = "NEXT_5_DAYS_12_1X2_PLUS_2_LOW_GOAL_EXACT_PARTIAL"
STATUS_NONE = "NEXT_5_DAYS_NO_VALID_SELECTIONS"
LOW6 = {"0-0", "1-0", "0-1", "1-1", "2-0", "0-2"}


def _safe_print(s: object) -> None:
    print(str(s).encode("ascii", "replace").decode("ascii"), flush=True)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


five = _load(ROOT / "scripts" / "run_five_day_complete_prediction_scan.py", "five_day_scan")
enrich = _load(ROOT / "scripts" / "enrich_next_4_days_existing_mission.py", "enrich_n4")
mission4 = _load(ROOT / "scripts" / "run_next_4_days_complete_prediction_scan.py", "mission_n4")


def _f(v: Any) -> float | None:
    return five._f(v)


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def disk_gb() -> dict[str, float]:
    u = shutil.disk_usage(str(ROOT))
    return {"total_gb": round(u.total / (1 << 30), 2), "used_gb": round(u.used / (1 << 30), 2), "free_gb": round(u.free / (1 << 30), 2)}


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


def dir_from_mass(mass: dict[str, Any] | None) -> str | None:
    if not mass:
        return None
    items = [(k, float(mass.get(k) or 0)) for k in ("home", "draw", "away")]
    if sum(x[1] for x in items) <= 0:
        return None
    return max(items, key=lambda x: x[1])[0]


def dir_from_scores(scores: list[Any]) -> str | None:
    home = draw = away = 0.0
    for i, s in enumerate(scores[:10]):
        if isinstance(s, dict):
            lab = str(s.get("score") or s.get("scoreline") or "")
            w = float(s.get("probability") or (1.0 / max(1, min(5, len(scores)))))
        else:
            lab = str(s)
            w = 1.0
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
    if home + draw + away <= 0:
        return None
    return max((("home", home), ("draw", draw), ("away", away)), key=lambda x: x[1])[0]


def dir_from_lambdas(lh: float | None, la: float | None, *, draw_band: float = 0.15) -> str | None:
    if lh is None or la is None:
        return None
    diff = float(lh) - float(la)
    if abs(diff) < draw_band:
        return "draw"
    return "home" if diff > 0 else "away"


def market_dir(odds: dict[str, Any]) -> str | None:
    h, d, a = _f(odds.get("home")), _f(odds.get("draw")), _f(odds.get("away"))
    if not h or not d or not a:
        return None
    # lowest odds = favorite
    return min((("home", h), ("draw", d), ("away", a)), key=lambda x: x[1])[0]


def _to_daily_fixture(p: dict[str, Any]):
    from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

    fid = int(p.get("fixture_id") or 0)
    return DailyFixture(
        fixture_id=fid,
        provider_fixture_id=int(p.get("provider_fixture_id") or fid),
        competition_key=str(p.get("competition") or p.get("league") or p.get("competition_key") or ""),
        home_team=str(p.get("home_team") or ""),
        away_team=str(p.get("away_team") or ""),
        kickoff_utc=str(p.get("kickoff_utc") or ""),
        status=str(p.get("fixture_status") or p.get("status") or "NS"),
        season=p.get("season"),
    )


def refresh_odds_for_selection(p: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Prematch odds refresh for selection freshness — does not regenerate freezes/Canonical."""
    ko = None
    try:
        ko = datetime.fromisoformat(str(p.get("kickoff_utc")).replace("Z", "+00:00"))
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    if ko is not None and ko <= now:
        base = assess_odds_freshness(p, now=now, refresh_meta={"refresh_attempted": False, "refresh_success": None, "block_reason": "post_kickoff"})
        return base

    refresh_meta: dict[str, Any] = {"refresh_attempted": False, "refresh_success": None}
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.connection import connect
        from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
        from worldcup_predictor.odds.refresh_gate import refresh_live_odds

        settings = get_settings()
        daily = _to_daily_fixture(p)
        refresh_meta = refresh_live_odds(daily, settings=settings)
        refresh_meta["refresh_attempted"] = True
        conn = connect(settings.sqlite_path)
        try:
            snap = get_latest_valid_1x2_odds_snapshot(conn, int(p["fixture_id"]), kickoff_utc=p.get("kickoff_utc"))
        finally:
            conn.close()
        if snap is not None:
            p = dict(p)
            odds = dict(p.get("odds") or {})
            fclass = getattr(snap, "freshness_class", None)
            fclass_s = str(getattr(fclass, "value", fclass) or "")
            odds.update(
                {
                    "home": snap.home_odds if snap.home_odds is not None else odds.get("home"),
                    "draw": snap.draw_odds if snap.draw_odds is not None else odds.get("draw"),
                    "away": snap.away_odds if snap.away_odds is not None else odds.get("away"),
                    "captured_at": snap.fetched_at_utc or odds.get("captured_at"),
                    "provider": snap.provider or odds.get("provider"),
                    "bookmaker_count": snap.bookmaker_count or odds.get("bookmaker_count"),
                    "freshness_status": fclass_s or odds.get("freshness_status"),
                    "allowed_ttl_seconds": snap.allowed_ttl_seconds or odds.get("allowed_ttl_seconds") or 21600,
                    "odds_age_minutes": snap.odds_age_minutes,
                }
            )
            p["odds"] = odds
            refresh_meta["snapshot_freshness_class"] = fclass_s
    except Exception as exc:  # noqa: BLE001
        refresh_meta = {"refresh_attempted": True, "refresh_success": False, "error": str(exc)[:200]}
    return assess_odds_freshness(p, now=now, refresh_meta=refresh_meta)


def assess_odds_freshness(p: dict, *, now: datetime, refresh_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    odds = dict(p.get("odds") or {})
    refresh_meta = refresh_meta or {}
    ts = odds.get("captured_at") or odds.get("timestamp") or odds.get("odds_timestamp")
    ttl = _f(odds.get("allowed_ttl_seconds")) or _f(p.get("odds_allowed_ttl_seconds")) or 21600.0
    age = _f(odds.get("odds_age_minutes"))
    status = str(odds.get("freshness_status") or p.get("odds_freshness") or "")
    parsed = None
    if ts:
        try:
            parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except Exception:
            parsed = None
    if parsed is not None:
        age_sec = max(0.0, (now - parsed).total_seconds())
        age = age_sec / 60.0
        live_status = "FRESH" if age_sec <= float(ttl) else "STALE"
    else:
        live_status = status or "UNKNOWN"
        if "FRESH" in live_status.upper() and age is None:
            live_status = "UNKNOWN"
        if age is not None and age * 60 > float(ttl):
            live_status = "STALE"
    has_1x2 = all(_f(odds.get(k)) for k in ("home", "draw", "away"))
    block = None
    if refresh_meta.get("block_reason"):
        block = refresh_meta.get("block_reason")
    elif not has_1x2:
        block = "missing_1x2"
    elif "FRESH" not in live_status.upper():
        block = "stale_or_unknown_odds"
    return {
        "home": odds.get("home"),
        "draw": odds.get("draw"),
        "away": odds.get("away"),
        "provider": odds.get("provider"),
        "bookmaker_count": odds.get("bookmaker_count"),
        "odds_timestamp": ts,
        "odds_age_minutes": None if age is None else round(float(age), 2),
        "allowed_ttl_seconds": ttl,
        "freshness_status": live_status,
        "stored_freshness_status": status,
        "has_1x2": has_1x2,
        "refresh_attempted": bool(refresh_meta.get("refresh_attempted")),
        "refresh_success": refresh_meta.get("refresh_success"),
        "refresh_provider": refresh_meta.get("provider"),
        "block_reason": block,
        "_odds_overlay": odds,
    }


def low_score_six_mass(scores: list[dict[str, Any]]) -> float:
    m = 0.0
    for s in scores:
        if str(s.get("score") or "") in LOW6:
            m += float(s.get("probability") or 0)
    return round(m, 8)


def tail4_mass(scores: list[dict[str, Any]]) -> float:
    m = 0.0
    for s in scores:
        parts = str(s.get("score") or "").split("-")
        if len(parts) != 2:
            continue
        try:
            if int(parts[0]) + int(parts[1]) >= 4:
                m += float(s.get("probability") or 0)
        except ValueError:
            continue
    return round(m, 8)


def classify_1x2_agreement(dirs: dict[str, str | None], *, market: str | None, forensic_severe: bool, fresh: bool, no_bet: bool) -> str:
    required = ["wde", "ecse", "exact_v2"]
    have = {k: dirs.get(k) for k in required if dirs.get(k)}
    if len(have) < 3:
        return "INSUFFICIENT_MODEL_OUTPUT"
    if forensic_severe or not fresh:
        return "DIRECTION_CONFLICT" if forensic_severe else "INSUFFICIENT_MODEL_OUTPUT"
    vals = list(have.values())
    if len(set(vals)) > 1:
        return "DIRECTION_CONFLICT"
    consensus = vals[0]
    extras = [dirs.get(k) for k in ("lambda_v2", "dna", "twins") if dirs.get(k)]
    opposing = [d for d in extras if d and d != consensus]
    if market and market != consensus:
        # market contradiction blocks unanimous; may still be strong if soft
        if opposing:
            return "DIRECTION_CONFLICT"
        return "PARTIAL_AGREEMENT"
    if opposing:
        return "PARTIAL_AGREEMENT" if len(opposing) == 1 else "DIRECTION_CONFLICT"
    supporting_extra = [d for d in extras if d == consensus]
    if no_bet:
        # still classify, but final list excludes
        pass
    if len(supporting_extra) >= 2 and market in {None, consensus}:
        return "UNANIMOUS_DIRECTION"
    if len(supporting_extra) >= 1 or market in {None, consensus}:
        return "STRONG_MULTI_MODEL_AGREEMENT"
    return "PARTIAL_AGREEMENT"


def research_class(ag: str, q: float, no_bet: bool, fresh: bool) -> str:
    if not fresh:
        return "BLOCKED"
    if no_bet:
        return "NO_BET"
    if ag in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"} and q >= 55:
        return "STRONG_RESEARCH_CANDIDATE"
    if ag in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"} and q >= 35:
        return "RESEARCH_CANDIDATE"
    if ag in {"DIRECTION_CONFLICT", "INSUFFICIENT_MODEL_OUTPUT"}:
        return "NO_BET" if no_bet else "WATCHLIST"
    return "WATCHLIST"


def build_consensus_top5(
    can: list[dict[str, Any]],
    exact: list[dict[str, Any]],
    dna: list[Any],
    twins: list[Any],
) -> list[dict[str, Any]]:
    """Transparent consensus: appearance + weighted p + ranks."""
    scores: dict[str, dict[str, Any]] = {}

    def bump(score: str, *, model: str, rank: int | None, p: float | None):
        if not score:
            return
        row = scores.setdefault(
            score,
            {"score": score, "models": set(), "canon_rank": None, "canon_p": None, "exact_rank": None, "exact_p": None, "dna_rank": None, "twins_rank": None, "weight": 0.0},
        )
        row["models"].add(model)
        if model == "canonical":
            row["canon_rank"] = rank
            row["canon_p"] = p
            row["weight"] += 3.0 * (p or 0) + max(0, 6 - (rank or 6)) * 0.15
        elif model == "exact_v2":
            row["exact_rank"] = rank
            row["exact_p"] = p
            row["weight"] += 2.5 * (p or 0) + max(0, 6 - (rank or 6)) * 0.12
        elif model == "dna":
            row["dna_rank"] = rank
            row["weight"] += 0.8 + max(0, 6 - (rank or 6)) * 0.08
        elif model == "twins":
            row["twins_rank"] = rank
            row["weight"] += 0.8 + max(0, 6 - (rank or 6)) * 0.08

    for i, s in enumerate(can[:10], 1):
        bump(str(s.get("score") or ""), model="canonical", rank=i, p=_f(s.get("probability")))
    for i, s in enumerate(exact[:10], 1):
        bump(str(s.get("score") or ""), model="exact_v2", rank=i, p=_f(s.get("probability")))
    for i, s in enumerate(dna[:5], 1):
        lab = s.get("score") if isinstance(s, dict) else s
        bump(str(lab or ""), model="dna", rank=i, p=_f(s.get("probability")) if isinstance(s, dict) else None)
    for i, s in enumerate(twins[:5], 1):
        lab = s.get("score") if isinstance(s, dict) else s
        bump(str(lab or ""), model="twins", rank=i, p=_f(s.get("probability")) if isinstance(s, dict) else None)

    ranked = sorted(
        scores.values(),
        key=lambda r: (-len(r["models"]), -float(r["weight"]), r["canon_rank"] or 99, r["exact_rank"] or 99, r["score"]),
    )
    out = []
    for i, r in enumerate(ranked[:5], 1):
        models = sorted(r["models"])
        reason = f"models={','.join(models)}; weight={r['weight']:.3f}"
        out.append(
            {
                "rank": i,
                "consensus_score": r["score"],
                "models_containing": models,
                "model_count": len(models),
                "canonical_rank": r["canon_rank"],
                "canonical_p": r["canon_p"],
                "exact_v2_rank": r["exact_rank"],
                "exact_v2_p": r["exact_p"],
                "dna_rank": r["dna_rank"],
                "twins_rank": r["twins_rank"],
                "consensus_reason": reason,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=PHASE)
    ap.add_argument("--dates", nargs="+", default=DEFAULT_DATES)
    ap.add_argument("--skip-owner", action="store_true")
    ap.add_argument("--output-dir", type=str, default="")
    args = ap.parse_args(argv)
    dates = list(args.dates)
    if len(dates) != 5:
        _safe_print(f"WARNING: expected 5 dates, got {len(dates)}")

    disk_before = disk_gb()
    _safe_print(f"Disk before: {disk_before}")
    if float(disk_before.get("free_gb") or 0) < 8:
        _safe_print("STOP: free disk < 8GB")
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rng = f"{dates[0]}_{dates[-1]}"
    out = Path(args.output_dir) if args.output_dir else ROOT / "artifacts" / "next_5_days_12_1x2_2_exact" / rng / ts
    out.mkdir(parents=True, exist_ok=True)

    commit = "unknown"
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        pass

    owner_runs = []
    if not args.skip_owner:
        for d in dates:
            owner_runs.append(five.ensure_owner_day(d, force=False))
    else:
        owner_runs = [{"date": d, "ran": False, "ok": True, "skipped": True} for d in dates]

    _safe_print("Building DNA/Twins engines (read-only)...")
    engines = five.build_evidence_engines()
    strength_engine = None
    try:
        from worldcup_predictor.research.football_strength_foundation.historical_match_service import HistoricalMatchService
        from worldcup_predictor.research.football_strength_foundation.team_strength_engine import TeamStrengthEngine

        strength_engine = TeamStrengthEngine(HistoricalMatchService(fi_path=str(FI)))
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"Strength engine unavailable: {exc}")

    forensic_agent = None
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.research.team_form_h2h_forensic.agent import TeamFormH2HForensicAgent

        forensic_agent = TeamFormH2HForensicAgent(settings=get_settings(), root=ROOT)
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"Forensic unavailable: {exc}")

    fi_conn = None
    if FI.exists():
        fi_conn = sqlite3.connect(f"file:{FI.as_posix()}?mode=ro", uri=True, timeout=60)
        fi_conn.row_factory = sqlite3.Row

    now = datetime.now(timezone.utc)
    shadow_success = Counter()
    discovered_rows: list[dict] = []
    eligibility_rows: list[dict] = []
    odds_rows: list[dict] = []
    blocked_rows: list[dict] = []
    canonical_rows: list[dict] = []
    direction_rows: list[dict] = []
    agreement_rows: list[dict] = []
    freeze_rows: list[dict] = []
    records: list[dict] = []
    already_frozen = newly_frozen = 0

    for d in dates:
        day = five.load_day(d)
        disc = day.get("discovery") or {}
        preds = list((day.get("predictions") or {}).get("predictions") or [])
        freezes = list((day.get("freezes") or {}).get("freezes") or [])
        _safe_print(f"[{d}] preds={len(preds)} freezes={len(freezes)}")

        for r in list(disc.get("all_discovered") or []):
            discovered_rows.append(
                {
                    "date": d,
                    "fixture_id": r.get("fixture_id"),
                    "vienna_ko": r.get("kickoff_vienna"),
                    "country": r.get("league_country") or r.get("country"),
                    "league": r.get("league") or r.get("competition"),
                    "home": r.get("home_team"),
                    "away": r.get("away_team"),
                    "eligibility": "discovered",
                }
            )
        for e in list(disc.get("exclusions") or []):
            blocked_rows.append(
                {
                    "date": d,
                    "fixture_id": e.get("fixture_id"),
                    "match": f"{e.get('home_team')} vs {e.get('away_team')}",
                    "reason": e.get("exclusion_reason") or e.get("reason") or "excluded",
                    "stage": "discovery",
                }
            )
            eligibility_rows.append(
                {
                    "date": d,
                    "fixture_id": e.get("fixture_id"),
                    "home": e.get("home_team"),
                    "away": e.get("away_team"),
                    "eligibility": "excluded",
                    "reason": e.get("exclusion_reason") or e.get("reason"),
                }
            )
        for f in freezes:
            st = str(f.get("capture_status") or f.get("status") or "")
            if "reus" in st.lower() or f.get("reused"):
                already_frozen += 1
            elif f.get("created") or "creat" in st.lower() or "captured" in st.lower():
                newly_frozen += 1
            else:
                already_frozen += 1

        for p in preds:
            p = dict(p)
            p["date"] = d
            fid = int(p.get("fixture_id") or 0)
            complete = bool(p.get("prediction_complete"))
            eligibility_rows.append(
                {
                    "date": d,
                    "fixture_id": fid,
                    "vienna_ko": p.get("kickoff_vienna"),
                    "country": p.get("league_country"),
                    "league": p.get("league") or p.get("competition"),
                    "home": p.get("home_team"),
                    "away": p.get("away_team"),
                    "eligibility": "eligible" if complete else "predicted_partial",
                    "reason": "" if complete else (p.get("block_reason") or "incomplete"),
                    "no_bet": p.get("no_bet"),
                }
            )
            if not complete:
                blocked_rows.append(
                    {
                        "date": d,
                        "fixture_id": fid,
                        "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                        "reason": p.get("block_reason") or "prediction_incomplete",
                        "stage": "prediction",
                    }
                )

            _safe_print(f"odds-refresh {d} {fid}...")
            odds_info = refresh_odds_for_selection(p, now=now)
            if odds_info.get("_odds_overlay"):
                p["odds"] = {**(p.get("odds") or {}), **odds_info["_odds_overlay"]}
            odds_rows.append(
                {
                    "fixture_id": fid,
                    "date": d,
                    "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                    **{k: v for k, v in odds_info.items() if k != "_odds_overlay"},
                }
            )

            _safe_print(f"enrich {d} {fid}...")
            ev = five.enrich_evidence(p, engines)
            if (ev.get("dna") or {}).get("status") == "OK":
                shadow_success["dna_v2"] += 1
            if (ev.get("twins") or {}).get("status") == "OK":
                shadow_success["twins"] += 1
            if (ev.get("hcee") or {}).get("status") == "OK":
                shadow_success["hcee"] += 1

            exact_meta: dict[str, Any] = {"status": "SKIPPED", "persisted": False, "shadow_only": True}
            if strength_engine is not None:
                exact_meta = enrich.compute_exact_family_readonly(p, conn=fi_conn, engine=strength_engine)
            if exact_meta.get("status") == "OK":
                shadow_success["exact_v2"] += 1
                shadow_success["lambda_v2"] += 1
                shadow_success["l2f"] += 1
                shadow_success["dixon_coles"] += 1
                shadow_success["football_strength"] += 1

            tsbp = enrich.try_tsbp_readonly(p, fi_conn) if fi_conn is not None else {"status": "NO_DB"}
            if tsbp.get("status") == "OK":
                shadow_success["tsbp"] += 1
            else:
                shadow_success["tsbp_skipped_readonly"] += 1

            forensic: dict[str, Any] = {"status": "SKIPPED"}
            forensic_severe = False
            if forensic_agent is not None:
                try:
                    forensic = forensic_agent.analyze_fixture(
                        fixture_id=fid,
                        home_team=p.get("home_team"),
                        away_team=p.get("away_team"),
                        kickoff_utc=p.get("kickoff_utc"),
                        competition_key=p.get("competition") or p.get("league"),
                    )
                    shadow_success["forensic_team_form_h2h"] += 1
                    cls = str(forensic.get("classification") or forensic.get("verdict") or "").upper()
                    forensic_severe = any(x in cls for x in ("SEVERE", "HARD_BLOCK", "CRITICAL", "CONTRADICTION"))
                except Exception as exc:  # noqa: BLE001
                    forensic = {"status": "ERROR", "error": str(exc)[:160]}

            ecse10 = mission4.load_ecse_top10(fid)
            if not ecse10.get("available"):
                scores = []
                for i in range(1, 11):
                    t = (p.get("ecse") or {}).get(f"top{i}") or {}
                    if t.get("score"):
                        scores.append({"rank": i, "score": t.get("score"), "probability": t.get("probability")})
                ecse10["scores"] = scores
                ecse10["available"] = bool(scores)
            if not ecse10.get("full_mass_1x2"):
                ecse10["full_mass_1x2"] = enrich.mass_1x2(ecse10.get("scores") or [])

            exact_tops = list(exact_meta.get("exact_v2_top10") or [])
            dna_top = list((ev.get("dna") or {}).get("top5") or [])
            twin_top = list((ev.get("twins") or {}).get("top5") or [])

            wde = p.get("wde") or {}
            raw_argmax = norm_dir(wde.get("raw_argmax") or wde.get("ft_marginal") or wde.get("decision"))
            stored_decision = norm_dir(wde.get("decision"))
            ecse_dir = dir_from_mass(ecse10.get("full_mass_1x2"))
            exact_dir = dir_from_mass(exact_meta.get("full_mass_1x2") or enrich.mass_1x2(exact_tops))
            lam = exact_meta.get("selected_lambda") or {}
            lambda_dir = dir_from_lambdas(_f(lam.get("lambda_home")), _f(lam.get("lambda_away")))
            dna_dir = dir_from_scores(dna_top)
            twin_dir = dir_from_scores(twin_top)
            mkt_dir = market_dir(p.get("odds") or {})

            dirs = {
                "wde": raw_argmax or stored_decision,
                "ecse": ecse_dir,
                "exact_v2": exact_dir,
                "lambda_v2": lambda_dir,
                "dna": dna_dir,
                "twins": twin_dir,
                "market": mkt_dir,
            }
            fresh = "FRESH" in str(odds_info.get("freshness_status") or "").upper() and bool(odds_info.get("has_1x2"))
            ag_status = classify_1x2_agreement(
                dirs,
                market=mkt_dir,
                forensic_severe=forensic_severe,
                fresh=fresh,
                no_bet=bool(p.get("no_bet")),
            )
            # quality score
            edge = max(_f(wde.get("home_probability")) or 0, _f(wde.get("draw_probability")) or 0, _f(wde.get("away_probability")) or 0)
            if edge > 1.5:
                edge /= 100.0
            conf = _f(wde.get("confidence")) or 0
            if conf > 1.5:
                conf /= 100.0
            q = 40 * edge + 30 * conf + (20 if ag_status == "UNANIMOUS_DIRECTION" else 12 if ag_status == "STRONG_MULTI_MODEL_AGREEMENT" else 0)
            if fresh:
                q += 8
            rclass = research_class(ag_status, q, bool(p.get("no_bet")), fresh)

            support = dirs["wde"]
            supporting = sum(1 for k, v in dirs.items() if k != "market" and v and support and v == support)
            opposing = sum(1 for k, v in dirs.items() if k != "market" and v and support and v != support)

            fi_row = mission4.freeze_integrity(p)
            freeze_rows.append({**fi_row, "date": d, "fixture_id": fid})

            can_lt = _f((p.get("ecse") or {}).get("total_lambda")) or _f(ecse10.get("lambda_total"))
            ex_lt = _f(lam.get("lambda_total"))
            ou = p.get("ou25") or {}
            btts = p.get("btts") or {}
            ou_under = _f(ou.get("under_probability") or ou.get("under_p") or ou.get("p_under"))
            # sometimes preferred_side only
            ou_side = str(ou.get("preferred_side") or ou.get("prediction") or "").lower()
            btts_pred = str(btts.get("prediction") or btts.get("preferred_side") or "").lower()
            top5_mass = _f(ecse10.get("top5_mass")) or _f((p.get("ecse") or {}).get("top5_mass")) or 0
            top10_mass = _f(ecse10.get("top10_mass")) or 0
            ent = _f((p.get("ecse") or {}).get("entropy")) or _f(ecse10.get("entropy_top10_normalized"))
            t4 = tail4_mass(ecse10.get("scores") or [])
            low6 = low_score_six_mass(ecse10.get("scores") or [])

            low_goal_ok = (
                complete
                and fresh
                and can_lt is not None
                and can_lt <= 2.20
                and (ex_lt is None or ex_lt <= 2.45)
                and top5_mass >= 0.55
                and low6 >= 0.60
                and t4 <= 0.18
                and (ou_under is None or ou_under >= 0.58 or "under" in ou_side)
                and ("yes" not in btts_pred or "no" in btts_pred or btts_pred == "")
                and not forensic_severe
                and ag_status not in {"DIRECTION_CONFLICT"}
            )
            # soft under if ou_under missing but side under
            if ou_under is None and "under" not in ou_side and ou_side:
                low_goal_ok = False

            canonical_rows.append(
                {
                    "fixture_id": fid,
                    "date": d,
                    "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                    "wde_h": wde.get("home_probability"),
                    "wde_d": wde.get("draw_probability"),
                    "wde_a": wde.get("away_probability"),
                    "raw_argmax": wde.get("raw_argmax") or wde.get("ft_marginal"),
                    "decision": wde.get("decision"),
                    "override": wde.get("decision_source"),
                    "override_reason": wde.get("decision_override_reason"),
                    "confidence": wde.get("confidence"),
                    "no_bet": p.get("no_bet"),
                    "btts": btts.get("prediction"),
                    "ou25": ou.get("preferred_side") or ou.get("prediction"),
                    "lambda_home": (p.get("ecse") or {}).get("lambda_home"),
                    "lambda_away": (p.get("ecse") or {}).get("lambda_away"),
                    "lambda_total": can_lt,
                    "top3_mass": ecse10.get("top3_mass") or (p.get("ecse") or {}).get("top3_mass"),
                    "top5_mass": top5_mass,
                    "top10_mass": top10_mass,
                    "entropy": ent,
                    "freeze_id": (p.get("freeze") or {}).get("freeze_id"),
                    "kickoff_utc": p.get("kickoff_utc"),
                    "kickoff_vienna": p.get("kickoff_vienna"),
                    "prediction_complete": complete,
                }
            )
            direction_rows.append({"fixture_id": fid, "date": d, "match": f"{p.get('home_team')} vs {p.get('away_team')}", **dirs, "agreement": ag_status})
            agreement_rows.append(
                {
                    "fixture_id": fid,
                    "date": d,
                    "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                    "agreement_status": ag_status,
                    "research_classification": rclass,
                    "supporting": supporting,
                    "opposing": opposing,
                    "fresh": fresh,
                    "no_bet": p.get("no_bet"),
                    "forensic_severe": forensic_severe,
                    "quality_score": round(q, 3),
                    **dirs,
                }
            )

            records.append(
                {
                    "p": p,
                    "fid": fid,
                    "date": d,
                    "odds_info": odds_info,
                    "ev": ev,
                    "exact_meta": exact_meta,
                    "ecse10": ecse10,
                    "exact_tops": exact_tops,
                    "dna_top": dna_top,
                    "twin_top": twin_top,
                    "dirs": dirs,
                    "ag_status": ag_status,
                    "rclass": rclass,
                    "q": q,
                    "supporting": supporting,
                    "opposing": opposing,
                    "forensic": forensic,
                    "forensic_severe": forensic_severe,
                    "fresh": fresh,
                    "fi_row": fi_row,
                    "low_goal_ok": low_goal_ok,
                    "low_goal_metrics": {
                        "canonical_lambda_total": can_lt,
                        "exact_v2_lambda_total": ex_lt,
                        "ou_under": ou_under,
                        "ou_side": ou_side,
                        "btts": btts_pred,
                        "top5_mass": top5_mass,
                        "top10_mass": top10_mass,
                        "entropy": ent,
                        "tail_4plus": t4,
                        "low6_mass": low6,
                    },
                    "complete": complete,
                }
            )

    # ---- PART A: 1X2 selection ----
    def rank_1x2(rec: dict) -> float:
        ag = rec["ag_status"]
        base = 50 if ag == "UNANIMOUS_DIRECTION" else 35 if ag == "STRONG_MULTI_MODEL_AGREEMENT" else 0
        return base + float(rec["q"]) + 5 * rec["supporting"] - 8 * rec["opposing"]

    cands_1x2 = [
        r
        for r in records
        if r["complete"]
        and r["ag_status"] in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}
        and r["rclass"] in {"STRONG_RESEARCH_CANDIDATE", "RESEARCH_CANDIDATE"}
        and not r["p"].get("no_bet")
        and r["fresh"]
        and not r["forensic_severe"]
    ]
    cands_1x2.sort(key=rank_1x2, reverse=True)

    def row_1x2(rec: dict, rank: int) -> dict[str, Any]:
        p = rec["p"]
        wde = p.get("wde") or {}
        return {
            "rank": rank,
            "date": rec["date"],
            "kickoff_vienna": p.get("kickoff_vienna"),
            "country": p.get("league_country"),
            "league": p.get("league") or p.get("competition"),
            "fixture_id": rec["fid"],
            "home": p.get("home_team"),
            "away": p.get("away_team"),
            "odds_h": rec["odds_info"].get("home"),
            "odds_d": rec["odds_info"].get("draw"),
            "odds_a": rec["odds_info"].get("away"),
            "selected_1x2_direction": rec["dirs"].get("wde"),
            "wde_h": wde.get("home_probability"),
            "wde_d": wde.get("draw_probability"),
            "wde_a": wde.get("away_probability"),
            "raw_argmax": wde.get("raw_argmax") or wde.get("ft_marginal"),
            "canonical_decision": wde.get("decision"),
            "confidence": wde.get("confidence"),
            "no_bet": p.get("no_bet"),
            "ecse_direction": rec["dirs"].get("ecse"),
            "exact_v2_direction": rec["dirs"].get("exact_v2"),
            "lambda_v2_direction": rec["dirs"].get("lambda_v2"),
            "dna_direction": rec["dirs"].get("dna"),
            "twins_direction": rec["dirs"].get("twins"),
            "market_direction": rec["dirs"].get("market"),
            "forensic_verdict": (rec["forensic"] or {}).get("classification") or (rec["forensic"] or {}).get("verdict") or (rec["forensic"] or {}).get("status"),
            "agreement_status": rec["ag_status"],
            "models_supporting": rec["supporting"],
            "models_opposing": rec["opposing"],
            "main_risk": "market_soft_dissent" if rec["dirs"].get("market") not in {None, rec["dirs"].get("wde")} else "low",
            "research_classification": rec["rclass"],
            "freeze_id": (p.get("freeze") or {}).get("freeze_id"),
            "score": round(rank_1x2(rec), 3),
        }

    ranked_1x2 = [row_1x2(r, i) for i, r in enumerate(cands_1x2, 1)]
    final_12 = ranked_1x2[:12]

    # ---- PART B: low-goal exact ----
    def rank_low(rec: dict) -> float:
        m = rec["low_goal_metrics"]
        s = 0.0
        s += 40 * float(m.get("low6_mass") or 0)
        s += 25 * float(m.get("top5_mass") or 0)
        s += 20 * max(0.0, (2.20 - float(m.get("canonical_lambda_total") or 2.2)) / 2.2)
        s += 15 * max(0.0, (0.18 - float(m.get("tail_4plus") or 0.18)) / 0.18)
        if rec["p"].get("no_bet"):
            s -= 10
        return s

    low_cands = [r for r in records if r["low_goal_ok"]]
    low_cands.sort(key=rank_low, reverse=True)
    # Prefer no_bet=false
    low_cands.sort(key=lambda r: (0 if not r["p"].get("no_bet") else 1, -rank_low(r)))

    low_ranked = []
    for i, rec in enumerate(low_cands, 1):
        p = rec["p"]
        m = rec["low_goal_metrics"]
        can = (rec["ecse10"].get("scores") or [])[:5]
        ex = (rec["exact_tops"] or [])[:5]
        low_ranked.append(
            {
                "rank": i,
                "fixture_id": rec["fid"],
                "date": rec["date"],
                "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "score": round(rank_low(rec), 3),
                "no_bet": p.get("no_bet"),
                "metrics": m,
                "freeze_id": (p.get("freeze") or {}).get("freeze_id"),
                "agreement_status": rec["ag_status"],
            }
        )
    final_2_recs = low_cands[:2]
    final_2 = []
    exact_top5_all = {}
    exact_consensus = {}
    for rec in final_2_recs:
        p = rec["p"]
        fid = rec["fid"]
        can_scores = list(rec["ecse10"].get("scores") or [])
        ex_scores = list(rec["exact_tops"] or [])
        dna = rec["dna_top"]
        twins = rec["twin_top"]
        cons = build_consensus_top5(can_scores, ex_scores, dna, twins)
        cmp = enrich.compare_models(rec["ecse10"], ex_scores, [{"score": t} if not isinstance(t, dict) else t for t in twins], p, rec["exact_meta"])
        payload = {
            "fixture_id": fid,
            "date": rec["date"],
            "match": f"{p.get('home_team')} vs {p.get('away_team')}",
            "kickoff_vienna": p.get("kickoff_vienna"),
            "freeze_id": (p.get("freeze") or {}).get("freeze_id"),
            "no_bet": p.get("no_bet"),
            "canonical_lambda": {
                "home": (p.get("ecse") or {}).get("lambda_home"),
                "away": (p.get("ecse") or {}).get("lambda_away"),
                "total": rec["low_goal_metrics"].get("canonical_lambda_total"),
            },
            "exact_v2_lambda": rec["exact_meta"].get("selected_lambda"),
            "ou25": p.get("ou25"),
            "btts": p.get("btts"),
            "top5_mass": rec["low_goal_metrics"].get("top5_mass"),
            "top10_mass": rec["low_goal_metrics"].get("top10_mass"),
            "entropy": rec["low_goal_metrics"].get("entropy"),
            "tail_4plus": rec["low_goal_metrics"].get("tail_4plus"),
            "low6_mass": rec["low_goal_metrics"].get("low6_mass"),
            "comparison": cmp,
            "main_low_goal_evidence": {
                "canonical_lambda_total": rec["low_goal_metrics"].get("canonical_lambda_total"),
                "low6_mass": rec["low_goal_metrics"].get("low6_mass"),
                "tail_4plus": rec["low_goal_metrics"].get("tail_4plus"),
                "ou_side": rec["low_goal_metrics"].get("ou_side"),
            },
            "main_risk": "elevated_exact_v2_lambda" if (rec["low_goal_metrics"].get("exact_v2_lambda_total") or 0) > 2.3 else "low",
            "final_verdict": "LOW_GOAL_EXACT_RESEARCH_CANDIDATE",
            "exact_v2_shadow_only": True,
        }
        final_2.append(payload)
        exact_top5_all[str(fid)] = {
            "fixture_id": fid,
            "match": payload["match"],
            "canonical_ecse_top5": can_scores[:5],
            "exact_v2_top5": ex_scores[:5],
            "dna_v2_top5": [{"score": s if not isinstance(s, dict) else s.get("score"), "probability": None if not isinstance(s, dict) else s.get("probability"), "probabilities_stored": isinstance(s, dict) and s.get("probability") is not None} for s in dna[:5]],
            "twins_top5": [{"score": s if not isinstance(s, dict) else s.get("score"), "probability": None if not isinstance(s, dict) else s.get("probability"), "probabilities_stored": False} for s in twins[:5]],
            "best_challenger_top5": [{"score": s if not isinstance(s, dict) else s.get("score"), "probability": None, "source": "historical_twins"} for s in twins[:5]],
            "notes": {
                "dna_probabilities_stored": False,
                "twins_probabilities_stored": False,
                "hcee_has_score_tops": False,
            },
        }
        exact_consensus[str(fid)] = {"fixture_id": fid, "match": payload["match"], "consensus_top5": cons}

    # Avoid list
    avoid = []
    for rec in records:
        if rec["ag_status"] == "DIRECTION_CONFLICT" or rec["forensic_severe"] or (rec["complete"] and not rec["fresh"]):
            avoid.append(
                {
                    "fixture_id": rec["fid"],
                    "date": rec["date"],
                    "match": f"{rec['p'].get('home_team')} vs {rec['p'].get('away_team')}",
                    "agreement_status": rec["ag_status"],
                    "no_bet": rec["p"].get("no_bet"),
                    "fresh": rec["fresh"],
                    "forensic_severe": rec["forensic_severe"],
                    "reason": "direction_conflict" if rec["ag_status"] == "DIRECTION_CONFLICT" else ("forensic_severe" if rec["forensic_severe"] else "stale_or_missing_odds"),
                }
            )
    avoid = avoid[:40]

    n_disc = len({(r.get("date"), r.get("fixture_id")) for r in discovered_rows if r.get("fixture_id")})
    n_elig = sum(1 for r in eligibility_rows if r.get("eligibility") == "eligible")
    n_complete = sum(1 for r in records if r["complete"])
    n_blocked = len(blocked_rows)

    if len(final_12) >= 12 and len(final_2) >= 2:
        status = STATUS_READY
    elif len(final_12) == 0 and len(final_2) == 0:
        status = STATUS_NONE
    else:
        status = STATUS_PARTIAL

    disk_after = disk_gb()
    selected_freeze_ids = [x.get("freeze_id") for x in final_12 if x.get("freeze_id")] + [x.get("freeze_id") for x in final_2 if x.get("freeze_id")]
    selected_fixture_ids = [x.get("fixture_id") for x in final_12] + [x.get("fixture_id") for x in final_2]

    validation = {
        "status": status,
        "phase": PHASE,
        "dates": dates,
        "commit": commit,
        "disk_before": disk_before,
        "disk_after": disk_after,
        "discovered_count": n_disc,
        "eligible_count": n_elig,
        "predicted_frozen_count": n_complete,
        "blocked_count": n_blocked,
        "already_frozen": already_frozen,
        "newly_frozen": newly_frozen,
        "valid_1x2_agreement_candidates": len(ranked_1x2),
        "final_1x2_selected": len(final_12),
        "low_goal_candidates": len(low_ranked),
        "final_low_goal_selected": len(final_2),
        "shadow_success_by_model": dict(shadow_success),
        "owner_runs": owner_runs,
        "no_promotion": True,
        "no_routing_activation": True,
        "exact_v2_shadow_only": True,
        "portfolio_similarity_ood_not_used": True,
        "selected_fixture_ids": selected_fixture_ids,
        "selected_freeze_ids": selected_freeze_ids,
        "cohort_type": "true_forward",
        "artifact_dir": str(out),
        "engine_errors": engines.get("errors"),
    }

    _json_dump(out / "run_manifest.json", validation)
    _json_dump(out / "discovered_universe.json", {"rows": discovered_rows, "count": len(discovered_rows)})
    _json_dump(out / "eligibility_report.json", {"rows": eligibility_rows})
    _json_dump(out / "fresh_odds_report.json", {"rows": odds_rows})
    _json_dump(out / "blocked_fixtures.json", {"rows": blocked_rows, "count": n_blocked})
    _json_dump(out / "canonical_predictions.json", {"rows": canonical_rows})
    _json_dump(out / "all_model_directions.json", {"rows": direction_rows})
    _json_dump(out / "model_agreement_report.json", {"rows": agreement_rows})
    _json_dump(out / "ranked_1x2_candidates.json", {"rows": ranked_1x2, "count": len(ranked_1x2)})
    _json_dump(out / "final_12_1x2.json", {"rows": final_12, "count": len(final_12), "max": 12})
    _json_dump(out / "low_goal_candidate_ranking.json", {"rows": low_ranked, "count": len(low_ranked)})
    _json_dump(out / "final_2_low_goal_exact.json", {"rows": final_2, "count": len(final_2), "max": 2})
    _json_dump(out / "exact_top5_all_models.json", exact_top5_all)
    _json_dump(out / "exact_consensus_top5.json", exact_consensus)
    _json_dump(out / "avoid_list.json", {"rows": avoid})
    _json_dump(out / "freeze_integrity_report.json", {"rows": freeze_rows, "cohort_type": "true_forward"})
    _json_dump(out / "validation_report.json", validation)

    md = _build_md(validation, final_12, final_2, exact_top5_all, exact_consensus, ranked_1x2, low_ranked, avoid, blocked_rows)
    (out / "NEXT_5_DAYS_12_1X2_2_EXACT_REPORT.md").write_text(md, encoding="utf-8")
    (ROOT / "NEXT_5_DAYS_12_1X2_2_EXACT_REPORT.md").write_text(md, encoding="utf-8")
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'/><title>Next 5 Days Selection</title>
<style>body{{font-family:Georgia,serif;background:#101820;color:#e8eef4;margin:2rem}}
h1{{color:#7dd3c0}} code{{color:#f0c674}} .card{{background:#1b2630;padding:1rem;margin:1rem 0;border-left:4px solid #7dd3c0}}
table{{border-collapse:collapse;width:100%;font-size:12px}} td,th{{border:1px solid #333;padding:4px}}</style></head>
<body><h1>Next 5 Days — 12×1X2 + 2 Low-Goal Exact</h1>
<div class='card'><strong>Status:</strong> <code>{status}</code><br/>
<strong>1X2 selected:</strong> <code>{len(final_12)}</code> / candidates <code>{len(ranked_1x2)}</code><br/>
<strong>Low-goal Exact:</strong> <code>{len(final_2)}</code> / candidates <code>{len(low_ranked)}</code><br/>
<strong>Promotion:</strong> NONE — NOT ACTIVATED</div>
<pre>{json.dumps({'final_12': final_12, 'final_2': final_2}, indent=2, default=str)[:14000]}</pre>
</body></html>"""
    (out / "owner_report.html").write_text(html, encoding="utf-8")

    if forensic_agent is not None:
        try:
            forensic_agent.close()
        except Exception:
            pass
    if fi_conn is not None:
        fi_conn.close()

    _safe_print(json.dumps({"status": status, "final_1x2": len(final_12), "final_exact": len(final_2), "artifact_dir": str(out)}, indent=2))
    return 0 if status != STATUS_NONE else 1


def _build_md(validation, final_12, final_2, exact_top5, consensus, ranked_1x2, low_ranked, avoid, blocked):
    lines = [
        "# NEXT_5_DAYS_12_1X2_2_EXACT_REPORT",
        "",
        f"**Status:** `{validation.get('status')}`  ",
        f"**Dates:** `{validation.get('dates')}`  ",
        f"**Commit:** `{validation.get('commit')}`  ",
        "",
        "**No promotion and no routing activation occurred.**",
        "",
        "## Discovery summary",
        "",
        f"- Discovered: `{validation.get('discovered_count')}`",
        f"- Eligible: `{validation.get('eligible_count')}`",
        f"- Predicted/frozen: `{validation.get('predicted_frozen_count')}`",
        f"- Already frozen: `{validation.get('already_frozen')}`",
        f"- Newly frozen: `{validation.get('newly_frozen')}`",
        f"- Blocked: `{validation.get('blocked_count')}`",
        "",
        f"- Valid 1X2 agreement candidates: `{validation.get('valid_1x2_agreement_candidates')}`",
        f"- Final 1X2 selected: `{validation.get('final_1x2_selected')}`",
        f"- Low-goal candidates: `{validation.get('low_goal_candidates')}`",
        f"- Final low-goal Exact: `{validation.get('final_low_goal_selected')}`",
        "",
        "## Final 1X2 shortlist",
        "",
        "| Rank | Date | Match | Dir | Odds H/D/A | Agreement | Class | Freeze |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for r in final_12:
        lines.append(
            f"| {r['rank']} | {r.get('kickoff_vienna')} | {r.get('home')} vs {r.get('away')} | {r.get('selected_1x2_direction')} | "
            f"{r.get('odds_h')}/{r.get('odds_d')}/{r.get('odds_a')} | {r.get('agreement_status')} | {r.get('research_classification')} | `{r.get('freeze_id')}` |"
        )
    if not final_12:
        lines.append("| — | — | *(none passed gates)* | — | — | — | — | — |")
    lines += ["", "## Final low-goal Exact Score selections", ""]
    for r in final_2:
        lines += [
            f"### {r.get('match')} (`{r.get('fixture_id')}`)",
            "",
            f"- Canonical λ total: `{ (r.get('canonical_lambda') or {}).get('total') }`",
            f"- Exact V2 λ total: `{ (r.get('exact_v2_lambda') or {}).get('lambda_total') }`",
            f"- Top5 mass: `{r.get('top5_mass')}` · low6 mass: `{r.get('low6_mass')}` · 4+ tail: `{r.get('tail_4plus')}`",
            f"- Verdict: `{r.get('final_verdict')}`",
            "",
        ]
        fid = str(r.get("fixture_id"))
        tops = exact_top5.get(fid) or {}
        lines.append("Canonical Top1–Top5:")
        for s in tops.get("canonical_ecse_top5") or []:
            lines.append(f"- {s.get('score')} p={s.get('probability')}")
        lines.append("Exact V2 Top1–Top5:")
        for s in tops.get("exact_v2_top5") or []:
            lines.append(f"- {s.get('score')} p={s.get('probability')}")
        lines.append("DNA V2 Top1–Top5 (probabilities not stored):")
        for s in tops.get("dna_v2_top5") or []:
            lines.append(f"- {s.get('score')}")
        lines.append("Twins Top1–Top5 (probabilities not stored):")
        for s in tops.get("twins_top5") or []:
            lines.append(f"- {s.get('score')}")
        lines += ["", "| Rank | Consensus | Models | Canon r/p | Exact r/p | DNA r | Twins r | Reason |", "|---:|---|---|---|---|---|---|---|"]
        for c in (consensus.get(fid) or {}).get("consensus_top5") or []:
            lines.append(
                f"| {c['rank']} | {c['consensus_score']} | {','.join(c['models_containing'])} | "
                f"{c.get('canonical_rank')}/{c.get('canonical_p')} | {c.get('exact_v2_rank')}/{c.get('exact_v2_p')} | "
                f"{c.get('dna_rank')} | {c.get('twins_rank')} | {c.get('consensus_reason')} |"
            )
        lines.append("")
    if not final_2:
        lines.append("*(no low-goal Exact fixtures passed gates)*")
    lines += [
        "",
        "## Avoid (sample)",
        "",
    ]
    for a in avoid[:15]:
        lines.append(f"- `{a.get('date')}` {a.get('match')} — {a.get('reason')} ({a.get('agreement_status')})")
    lines += [
        "",
        f"Shadow success: `{validation.get('shadow_success_by_model')}`",
        f"Disk: `{validation.get('disk_before')}` → `{validation.get('disk_after')}`",
        "",
        "**NOT DEPLOYED / NO ROUTING ACTIVATION / EXACT V2 SHADOW-ONLY**",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
