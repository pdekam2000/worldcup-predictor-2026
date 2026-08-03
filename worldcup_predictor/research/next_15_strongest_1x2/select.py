"""Select next 15 strongest 1X2 candidates using canonical + research priority."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.research.next_15_strongest_1x2 import (
    PROGRAM,
    STATUS_EMPTY,
    STATUS_PARTIAL,
    STATUS_READY,
)

ROOT = Path(__file__).resolve().parents[3]
VIENNA = ZoneInfo("Europe/Vienna")
EVAL_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _norm_dir(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower().replace(" ", "_")
    if s in {"home", "home_win", "1", "h"}:
        return "home"
    if s in {"away", "away_win", "2", "a"}:
        return "away"
    if s in {"draw", "x", "d"}:
        return "draw"
    return None


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_unit(value: Any) -> float | None:
    x = _f(value)
    if x is None:
        return None
    if x > 1.5:
        x = x / 100.0
    return max(0.0, min(1.0, x))


def latest_next5_artifact() -> Path | None:
    root = ROOT / "artifacts" / "next_5_days_complete_predictions"
    if not root.exists():
        return None
    runs = sorted(root.glob("*/*"), key=lambda p: p.stat().st_mtime if p.is_dir() else 0)
    for p in reversed(runs):
        if (p / "canonical_predictions.json").is_file():
            return p
    return None


def load_predictions(art: Path) -> list[dict[str, Any]]:
    obj = json.loads((art / "canonical_predictions.json").read_text(encoding="utf-8"))
    return list(obj.get("predictions") or [])


def ecse_direction(p: dict[str, Any]) -> str | None:
    ecse = p.get("ecse") or {}
    d = _norm_dir(ecse.get("direction") or ecse.get("top1_side") or ecse.get("ft_marginal_direction"))
    if d:
        return d
    top1 = ecse.get("top1") or {}
    score = None
    if isinstance(top1, dict):
        score = top1.get("score") or top1.get("exact_score")
    elif isinstance(top1, str):
        score = top1.split()[0]
    if score and "-" in str(score):
        try:
            h, a = str(score).split("-", 1)
            hi, ai = int(h), int(a)
            if hi > ai:
                return "home"
            if hi < ai:
                return "away"
            return "draw"
        except ValueError:
            return None
    return None


def market_dir(odds: dict[str, Any]) -> str | None:
    h, d, a = _f(odds.get("home")), _f(odds.get("draw")), _f(odds.get("away"))
    if not (h and d and a and h > 1 and d > 1 and a > 1):
        return None
    return min([("home", h), ("draw", d), ("away", a)], key=lambda x: x[1])[0]


def _iter_score_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # shapes: {"1": {...}, "2": {...}} or {"scores": [...]}
        if "scores" in value and isinstance(value["scores"], list):
            return value["scores"]
        keys = sorted(value.keys(), key=lambda k: int(k) if str(k).isdigit() else 999)
        return [value[k] for k in keys]
    return []


def top_scores(ecse: dict[str, Any], n: int = 5) -> list[str]:
    out: list[str] = []
    for item in _iter_score_items(ecse.get("top5") or ecse.get("top_5")):
        if len(out) >= n:
            break
        if isinstance(item, dict):
            sc = item.get("score") or item.get("exact_score")
            pr = item.get("probability") or item.get("p")
            if sc is None:
                continue
            if isinstance(pr, (int, float)):
                pct = pr * 100 if pr <= 1 else pr
                out.append(f"{sc} ({pct:.1f}%)")
            else:
                out.append(str(sc))
        elif isinstance(item, str):
            out.append(item)
    if len(out) < n:
        for item in _iter_score_items(ecse.get("top10")):
            if len(out) >= n:
                break
            if isinstance(item, dict):
                sc = item.get("score")
                if sc and all(str(sc) not in x for x in out):
                    out.append(str(sc))
            elif isinstance(item, str) and item not in out:
                out.append(item)
    return out[:n]


def research_opinions(p: dict[str, Any]) -> dict[str, str]:
    """Best-effort opinions; UNAVAILABLE when not in freeze/artifact."""
    out = {
        "dna": "UNAVAILABLE",
        "twins": "UNAVAILABLE",
        "exact_v2": "UNAVAILABLE",
        "hcee": "UNAVAILABLE",
        "lambda_v2": "UNAVAILABLE",
    }
    l2f = p.get("l2f_forward_shadow") or {}
    if isinstance(l2f, dict) and l2f:
        if l2f.get("direction") or l2f.get("exact_top1"):
            out["lambda_v2"] = str(l2f.get("direction") or l2f.get("status") or "PRESENT")
        elif l2f.get("status"):
            out["lambda_v2"] = str(l2f.get("status"))
    # shadow flags from optional enrichment
    for key, label in (
        ("dna_opinion", "dna"),
        ("twins_opinion", "twins"),
        ("exact_v2_opinion", "exact_v2"),
        ("hcee_opinion", "hcee"),
    ):
        if p.get(key):
            out[label] = str(p[key])
    return out


def score_candidate(p: dict[str, Any]) -> dict[str, Any]:
    wde = p.get("wde") or {}
    ecse = p.get("ecse") or {}
    odds = p.get("odds") or {}
    wde_dir = _norm_dir(wde.get("decision") or wde.get("effective_1x2"))
    ecse_dir = ecse_direction(p)
    mkt = market_dir(odds)
    conf = _pct_unit(wde.get("confidence") or p.get("model_confidence_pct"))
    t5 = _f(ecse.get("top5_mass"))
    ent = _f(ecse.get("entropy"))
    lh = _f(ecse.get("lambda_home"))
    la = _f(ecse.get("lambda_away"))
    total_l = _f(ecse.get("total_lambda"))
    if total_l is None and lh is not None and la is not None:
        total_l = lh + la

    # Priority scoring (deterministic, research-aligned)
    score = 0.0
    reasons = []
    tier_priority = 99

    if ecse_dir == "home" and wde_dir == "home":
        score += 1000
        tier_priority = 1
        reasons.append("PRIORITY1_ECSE_HOME_AND_WDE_HOME")
    elif ecse_dir == "away" and wde_dir == "away":
        score += 850
        tier_priority = 2
        reasons.append("PRIORITY2_ECSE_AWAY_AND_WDE_AWAY")
    elif wde_dir and ecse_dir and wde_dir == ecse_dir:
        score += 500
        tier_priority = 3
        reasons.append("WDE_ECSE_AGREE_NON_HOME_AWAY_PAIR")
    elif wde_dir and ecse_dir and wde_dir != ecse_dir:
        score += 50
        tier_priority = 8
        reasons.append("DIRECTION_CONFLICT")
    else:
        score += 100
        tier_priority = 7
        reasons.append("PARTIAL_DIRECTION")

    # multi-model / market
    agree_parts = [x for x in (wde_dir, ecse_dir, mkt) if x]
    agree_n = len(agree_parts)
    agree_unique = len(set(agree_parts))
    if agree_n >= 3 and agree_unique == 1:
        score += 120
        reasons.append("UNANIMOUS_WDE_ECSE_MARKET")
    elif wde_dir and mkt and wde_dir == mkt:
        score += 60
        reasons.append("MARKET_AGREES_WDE")
    elif wde_dir and mkt and wde_dir != mkt:
        score -= 40
        reasons.append("MARKET_DISAGREES_WDE")

    if conf is not None:
        score += conf * 80
        reasons.append(f"CONF={conf:.2f}")
    if t5 is not None:
        score += min(t5, 1.0) * 70
        reasons.append(f"TOP5={t5:.3f}")
    if ent is not None:
        score += max(0.0, 2.2 - ent) * 25
        reasons.append(f"ENT={ent:.3f}")

    fresh = str(odds.get("freshness_status") or p.get("odds_freshness") or "").upper()
    if odds.get("complete") and fresh in {"ODDS_FRESH", "FRESH", "OK", ""}:
        score += 40
        reasons.append("ODDS_USABLE")
    elif fresh in {"ODDS_STALE", "STALE"}:
        score -= 15
        reasons.append("ODDS_STALE")
    elif not odds.get("complete") and not (odds.get("home") and odds.get("draw") and odds.get("away")):
        score -= 25
        reasons.append("ODDS_MISSING")

    dq = str(p.get("data_quality") or "").upper()
    if dq in {"HIGH", "GOOD", "OK"}:
        score += 15
    warnings = str(p.get("main_risk") or "")
    severe = any(x in warnings.upper() for x in ("SEVERE", "LEAKAGE", "CORRUPT", "CONFLICT_CRITICAL"))
    if severe:
        score -= 80
        reasons.append("SEVERE_WARNING")

    no_bet = bool(p.get("no_bet"))
    # do not reject; soft penalty
    if no_bet:
        score -= 10
        reasons.append("NO_BET_FLAG")

    # classification
    if severe or (wde_dir and ecse_dir and wde_dir != ecse_dir and (conf or 0) < 0.55):
        klass = "AVOID"
    elif tier_priority <= 2 and (conf or 0) >= 0.55 and (t5 or 0) >= 0.45 and not severe:
        klass = "STRONG"
    elif tier_priority <= 3 and (conf or 0) >= 0.50:
        klass = "MEDIUM"
    elif tier_priority <= 2:
        klass = "MEDIUM"
    else:
        klass = "WATCHLIST"

    # agreement score 0-100
    agreement_score = 0
    if wde_dir and ecse_dir and wde_dir == ecse_dir:
        agreement_score += 50
    if wde_dir and mkt and wde_dir == mkt:
        agreement_score += 30
    if ecse_dir and mkt and ecse_dir == mkt:
        agreement_score += 20

    opinions = research_opinions(p)
    btts = p.get("btts") or {}
    ou = p.get("ou25") or {}

    ko = _parse_dt(p.get("kickoff_utc"))
    vienna = ko.astimezone(VIENNA).strftime("%Y-%m-%d %H:%M %Z") if ko else p.get("kickoff_vienna")

    return {
        "fixture_id": p.get("fixture_id"),
        "date": (ko.astimezone(VIENNA).date().isoformat() if ko else p.get("date")),
        "kickoff_vienna": vienna,
        "kickoff_utc": p.get("kickoff_utc"),
        "country": p.get("league_country") or p.get("home_team_country"),
        "league": p.get("league") or p.get("competition"),
        "home": p.get("home_team"),
        "away": p.get("away_team"),
        "match": f"{p.get('home_team')} vs {p.get('away_team')}",
        "odds_h": odds.get("home"),
        "odds_d": odds.get("draw"),
        "odds_a": odds.get("away"),
        "odds_freshness": odds.get("freshness_status") or p.get("odds_freshness"),
        "wde_home": wde.get("home_probability"),
        "wde_draw": wde.get("draw_probability"),
        "wde_away": wde.get("away_probability"),
        "wde_decision": wde_dir,
        "wde_confidence": wde.get("confidence") if wde.get("confidence") is not None else (conf * 100 if conf else None),
        "ecse_direction": ecse_dir,
        "ecse_top1": (top_scores(ecse, 1) or [None])[0],
        "ecse_top5": " | ".join(top_scores(ecse, 5)),
        "top5_mass": t5,
        "top10_mass": _f(ecse.get("top10_mass")),
        "entropy": ent,
        "lambda_home": lh,
        "lambda_away": la,
        "total_lambda": total_l,
        "btts": btts.get("prediction") or btts.get("selection"),
        "ou25": ou.get("prediction") or ou.get("selection"),
        "dna_opinion": opinions["dna"],
        "twins_opinion": opinions["twins"],
        "exact_v2_opinion": opinions["exact_v2"],
        "hcee_opinion": opinions["hcee"],
        "lambda_v2_opinion": opinions["lambda_v2"],
        "agreement_score": agreement_score,
        "market_direction": mkt,
        "no_bet": no_bet,
        "main_risks": warnings or None,
        "data_quality": p.get("data_quality"),
        "classification": klass,
        "tier_priority": tier_priority,
        "research_score": round(score, 4),
        "score_reasons": reasons,
        "freeze_id": (p.get("freeze") or {}).get("freeze_id") or (p.get("freeze") or {}).get("prediction_id"),
        "source": p.get("source"),
        "prediction_complete": p.get("prediction_complete"),
        "why": None,  # filled after rank
    }


def select_top15(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        scored,
        key=lambda r: (
            r["tier_priority"],
            -r["research_score"],
            -(r.get("agreement_score") or 0),
            -(r.get("wde_confidence") or 0),
            str(r.get("kickoff_utc") or ""),
        ),
    )
    # diversify slightly: prefer unique leagues in top15 but never drop PRIORITY1/2 for diversity
    top: list[dict[str, Any]] = []
    league_counts: dict[str, int] = {}
    for r in ranked:
        if len(top) >= 15:
            break
        lg = str(r.get("league") or "?")
        if league_counts.get(lg, 0) >= 3 and r["tier_priority"] > 2 and len(top) >= 10:
            continue
        top.append(r)
        league_counts[lg] = league_counts.get(lg, 0) + 1
    # fill if short
    if len(top) < 15:
        ids = {r["fixture_id"] for r in top}
        for r in ranked:
            if r["fixture_id"] in ids:
                continue
            top.append(r)
            if len(top) >= 15:
                break
    for i, r in enumerate(top, 1):
        r["rank"] = i
        r["why"] = _why(r, i)
        r["final_recommendation"] = _reco(r)
    return top


def _why(r: dict[str, Any], rank: int) -> str:
    bits = [f"Rank #{rank} via research_score={r['research_score']}."]
    if r.get("tier_priority") == 1:
        bits.append("Highest-priority research rule: ECSE Direction=Home AND WDE=Home (72.6% TF forensic base).")
    elif r.get("tier_priority") == 2:
        bits.append("Second-priority mirror rule: ECSE Direction=Away AND WDE=Away.")
    elif "UNANIMOUS_WDE_ECSE_MARKET" in (r.get("score_reasons") or []):
        bits.append("WDE, ECSE and market agree on direction.")
    else:
        bits.append("Selected via multi-factor ranking (agreement, confidence, Top5 mass, entropy, odds quality).")
    if r.get("no_bet"):
        bits.append("no_bet=true but not auto-rejected; classified with soft penalty.")
    if r.get("odds_h") is None:
        bits.append("Odds incomplete/missing — not fabricated.")
    return " ".join(bits)


def _reco(r: dict[str, Any]) -> str:
    side = r.get("wde_decision")
    klass = r.get("classification")
    if klass == "AVOID":
        return f"AVOID — do not bet ({';'.join((r.get('score_reasons') or [])[:3])})"
    if klass == "STRONG":
        return f"STRONG lean {side} — research priority candidate"
    if klass == "MEDIUM":
        return f"MEDIUM lean {side} — usable research candidate"
    return f"WATCHLIST lean {side} — monitor only"


def side_top(scored: list[dict[str, Any]], side: str, n: int = 5) -> list[dict[str, Any]]:
    rows = [r for r in scored if r.get("wde_decision") == side]
    # for draws, also include ECSE draw
    if side == "draw":
        rows = [r for r in scored if r.get("wde_decision") == "draw" or r.get("ecse_direction") == "draw"]
        # prefer higher draw probability
        rows = sorted(
            rows,
            key=lambda r: (
                0 if r.get("wde_decision") == "draw" and r.get("ecse_direction") == "draw" else 1,
                -( _pct_unit(r.get("wde_draw")) or 0),
                -r["research_score"],
            ),
        )
    else:
        rows = sorted(rows, key=lambda r: (r["tier_priority"], -r["research_score"]))
    out = []
    for i, r in enumerate(rows[:n], 1):
        out.append({**r, "side_rank": i})
    return out


def run_selection(*, out_dir: Path | None = None) -> dict[str, Any]:
    run_id = _utc()
    out = out_dir or (ROOT / "artifacts" / "next_15_strongest_1x2" / run_id)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    art = latest_next5_artifact()
    if not art:
        payload = {"status": STATUS_EMPTY, "error": "no next_5_days artifact with canonical_predictions"}
        _write_json(out / "run_manifest.json", payload)
        return payload

    preds = load_predictions(art)
    upcoming = []
    for p in preds:
        ko = _parse_dt(p.get("kickoff_utc"))
        if not ko:
            continue
        # skip already started / finished
        if ko <= now:
            continue
        # skip lifecycle finished markers
        life = str(p.get("lifecycle") or "").upper()
        if "FINISHED" in life and "HAS_FREEZE" not in life:
            continue
        if not p.get("wde"):
            continue
        upcoming.append(p)

    scored = [score_candidate(p) for p in upcoming]
    top15 = select_top15(scored)
    top_home = side_top(scored, "home", 5)
    top_away = side_top(scored, "away", 5)
    top_draw = side_top(scored, "draw", 5)

    priced = sum(1 for r in top15 if r.get("odds_h") and r.get("odds_d") and r.get("odds_a"))
    status = STATUS_READY if priced >= 10 else (STATUS_PARTIAL if top15 else STATUS_EMPTY)

    _write_json(out / "universe_upcoming.json", {"n": len(scored), "rows": scored})
    _write_json(out / "top15.json", {"n": len(top15), "rows": top15})
    _write_csv(out / "top15.csv", top15)
    _write_json(out / "top5_home.json", top_home)
    _write_json(out / "top5_away.json", top_away)
    _write_json(out / "top5_draw.json", top_draw)
    _write_json(
        out / "classifications.json",
        {
            "STRONG": [r for r in scored if r["classification"] == "STRONG"],
            "MEDIUM": [r for r in scored if r["classification"] == "MEDIUM"],
            "WATCHLIST": [r for r in scored if r["classification"] == "WATCHLIST"],
            "AVOID": [r for r in scored if r["classification"] == "AVOID"],
        },
    )

    _write_reports(out, top15=top15, top_home=top_home, top_away=top_away, top_draw=top_draw, scored=scored, art=art, status=status)

    # root copies
    (ROOT / "NEXT_15_STRONGEST_1X2_REPORT.md").write_text((out / "NEXT_15_STRONGEST_1X2_REPORT.md").read_text(encoding="utf-8"), encoding="utf-8")
    (ROOT / "NEXT_15_STRONGEST_1X2_REPORT_FA.md").write_text((out / "NEXT_15_STRONGEST_1X2_REPORT_FA.md").read_text(encoding="utf-8"), encoding="utf-8")

    manifest = {
        "program": PROGRAM,
        "run_id": run_id,
        "status": status,
        "source_artifact": str(art.relative_to(ROOT)),
        "upcoming_n": len(scored),
        "top15_n": len(top15),
        "top15_priced_n": priced,
        "as_of_utc": now.isoformat(),
        "artifact_dir": str(out.relative_to(ROOT)),
        "safety": {
            "NOT_DEPLOYED": True,
            "NO_FABRICATED_ODDS": True,
            "REUSED_EXISTING_PREDICTIONS": True,
            "NO_FINISHED_REGENERATION": True,
            "CANONICAL_UNCHANGED": True,
        },
    }
    _write_json(out / "run_manifest.json", manifest)
    _write_json(ROOT / "NEXT_15_STRONGEST_1X2_SUMMARY.json", manifest)
    return {**manifest, "out_dir": str(out), "top15": top15}


def _row_md(r: dict[str, Any]) -> str:
    return (
        f"| {r.get('rank') or r.get('side_rank')} | {r.get('date')} | {r.get('match')} | {r.get('league')} | "
        f"{r.get('wde_decision')} | {r.get('ecse_direction')} | {r.get('wde_confidence')} | "
        f"{r.get('odds_h')}/{r.get('odds_d')}/{r.get('odds_a')} | {r.get('top5_mass')} | {r.get('entropy')} | "
        f"{r.get('classification')} | {r.get('no_bet')} |"
    )


def _write_reports(out: Path, **kw: Any) -> None:
    top15 = kw["top15"]
    top_home = kw["top_home"]
    top_away = kw["top_away"]
    top_draw = kw["top_draw"]
    scored = kw["scored"]
    art = kw["art"]
    status = kw["status"]

    lines = [
        "# NEXT 15 STRONGEST 1X2 SELECTION",
        "",
        f"**Status:** `{status}`",
        f"**Source artifact:** `{art}`",
        f"**Upcoming fixtures scored:** {len(scored)}",
        "",
        "## Ranking method",
        "",
        "1. ECSE Direction = Home AND WDE = Home (highest priority; research forensic 72.6% TF base)",
        "2. ECSE Direction = Away AND WDE = Away",
        "3. Multi-model / market agreement",
        "4. Canonical WDE confidence",
        "5. ECSE Top5 mass",
        "6. Low entropy",
        "7. Market agreement",
        "8. Fresh/usable odds",
        "9. Data quality",
        "10. No severe forensic warnings",
        "",
        "`no_bet` does **not** auto-reject; fixtures are classified STRONG / MEDIUM / WATCHLIST / AVOID.",
        "DNA / Twins / Exact V2 shown as UNAVAILABLE when not present in the freeze/artifact (not fabricated).",
        "",
        "## FINAL TOP 15",
        "",
        "| Rank | Date | Match | League | WDE | ECSE | Conf | Odds H/D/A | Top5 | Ent | Class | no_bet |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in top15:
        lines.append(_row_md(r))

    lines += ["", "## Candidate details", ""]
    for r in top15:
        lines += [
            f"### #{r['rank']} {r['match']}",
            f"- Fixture ID: `{r['fixture_id']}`",
            f"- Kickoff (Vienna): {r['kickoff_vienna']}",
            f"- Country / League: {r['country']} / {r['league']}",
            f"- Odds H/D/A: {r['odds_h']} / {r['odds_d']} / {r['odds_a']} ({r['odds_freshness']})",
            f"- WDE H/D/A: {r['wde_home']} / {r['wde_draw']} / {r['wde_away']} · decision={r['wde_decision']} · conf={r['wde_confidence']}",
            f"- ECSE Direction: {r['ecse_direction']}",
            f"- ECSE Top1–Top5: {r['ecse_top5']}",
            f"- Top5 mass / Entropy: {r['top5_mass']} / {r['entropy']}",
            f"- Lambda H/A/Total: {r['lambda_home']} / {r['lambda_away']} / {r['total_lambda']}",
            f"- BTTS / O/U 2.5: {r['btts']} / {r['ou25']}",
            f"- DNA / Twins / Exact V2: {r['dna_opinion']} / {r['twins_opinion']} / {r['exact_v2_opinion']}",
            f"- Agreement score: {r['agreement_score']} · Market: {r['market_direction']}",
            f"- no_bet: {r['no_bet']}",
            f"- Main risks: {r['main_risks']}",
            f"- Classification: **{r['classification']}**",
            f"- Final recommendation: {r['final_recommendation']}",
            f"- Why in Top15: {r['why']}",
            "",
        ]

    def side_table(title: str, rows: list[dict[str, Any]]) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not rows:
            lines.append("_None available in upcoming window._")
            lines.append("")
            return
        lines.append("| Rank | Date | Match | Side lean | Conf | Odds | Class |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['side_rank']} | {r['date']} | {r['match']} | WDE={r['wde_decision']} ECSE={r['ecse_direction']} | "
                f"{r['wde_confidence']} | {r['odds_h']}/{r['odds_d']}/{r['odds_a']} | {r['classification']} |"
            )
        lines.append("")

    side_table("TOP 5 HOME WINS", top_home)
    side_table("TOP 5 AWAY WINS", top_away)
    side_table("TOP 5 DRAW POSSIBILITIES", top_draw)

    lines += [
        "## Safety",
        "",
        "- NOT DEPLOYED",
        "- NO FABRICATED ODDS",
        "- REUSED EXISTING PREDICTIONS / FREEZES",
        "- NO FINISHED FIXTURE REGENERATION",
        "- CANONICAL / WDE / ECSE UNCHANGED",
        "",
    ]
    (out / "NEXT_15_STRONGEST_1X2_REPORT.md").write_text("\n".join(lines), encoding="utf-8")

    fa = [
        "# ۱۵ قوی‌ترین انتخاب ۱X۲ روزهای آینده",
        "",
        f"**وضعیت:** `{status}`",
        f"**منبع پیش‌بینی:** `{art}`",
        f"**تعداد بازی‌های آینده امتیازدهی‌شده:** {len(scored)}",
        "",
        "## روش رتبه‌بندی",
        "۱) ECSE=Home و WDE=Home (بالاترین اولویت پژوهشی)",
        "۲) ECSE=Away و WDE=Away",
        "۳) توافق چندمدلی/بازار",
        "۴) اطمینان Canonical WDE",
        "۵) جرم Top5",
        "۶) آنتروپی پایین",
        "۷) توافق بازار",
        "۸) تازگی شانس",
        "۹) کیفیت داده",
        "۱۰) نبود هشدار شدید",
        "",
        "پرچم `no_bet` به‌تنهایی حذف نمی‌کند؛ رده‌بندی STRONG/MEDIUM/WATCHLIST/AVOID است.",
        "",
        "## جدول نهایی Top15",
        "",
        "| رتبه | تاریخ | بازی | لیگ | WDE | ECSE | اطمینان | شانس | Top5 | کلاس |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in top15:
        fa.append(
            f"| {r['rank']} | {r['date']} | {r['match']} | {r['league']} | {r['wde_decision']} | {r['ecse_direction']} | "
            f"{r['wde_confidence']} | {r['odds_h']}/{r['odds_d']}/{r['odds_a']} | {r['top5_mass']} | {r['classification']} |"
        )
    fa += ["", "## جزئیات و دلیل ورود", ""]
    for r in top15:
        fa += [
            f"### #{r['rank']} {r['match']}",
            f"- شناسه: `{r['fixture_id']}` · کیک‌آف وین: {r['kickoff_vienna']}",
            f"- WDE={r['wde_decision']} ({r['wde_confidence']}) · ECSE={r['ecse_direction']}",
            f"- Top5: {r['ecse_top5']}",
            f"- Lambda کل: {r['total_lambda']} · BTTS={r['btts']} · O/U={r['ou25']}",
            f"- DNA/Twins/ExactV2: {r['dna_opinion']} / {r['twins_opinion']} / {r['exact_v2_opinion']}",
            f"- no_bet={r['no_bet']} · ریسک: {r['main_risks']}",
            f"- توصیه: {r['final_recommendation']}",
            f"- چرا در Top15: {r['why']}",
            "",
        ]
    fa += [
        "## پنج میزبان برتر",
        "",
    ]
    for r in top_home:
        fa.append(f"{r['side_rank']}. {r['match']} · conf={r['wde_confidence']} · {r['classification']}")
    fa += ["", "## پنج مهمان برتر", ""]
    for r in top_away:
        fa.append(f"{r['side_rank']}. {r['match']} · conf={r['wde_confidence']} · {r['classification']}")
    fa += ["", "## پنج احتمال تساوی", ""]
    for r in top_draw:
        fa.append(f"{r['side_rank']}. {r['match']} · WDE={r['wde_decision']} ECSE={r['ecse_direction']} · {r['classification']}")
    fa += [
        "",
        "## ایمنی",
        "NOT DEPLOYED · بدون ساخت شانس جعلی · استفاده از فریز/پیش‌بینی موجود · بدون بازتولید بازی‌های تمام‌شده",
        "",
    ]
    (out / "NEXT_15_STRONGEST_1X2_REPORT_FA.md").write_text("\n".join(fa), encoding="utf-8")
