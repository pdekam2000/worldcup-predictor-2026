"""Phase K2 — direct first-goal market audit (UEFA cache, no production changes)."""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.egie.uefa_club.feature_extractors import _fixture_data, _float, parse_match_result
from worldcup_predictor.egie.uefa_club.odds_intelligence import (
    SHARP_BOOKMAKERS,
    SOFT_BOOKMAKERS,
    _book_tier,
    _bookmaker_name,
    _implied,
    _parse_ts,
    _pick_side_from_implied,
    parse_uefa_odds_deep,
)
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache, uefa_data_root

K2Strategy = Literal["A", "B", "C", "D", "E", "F"]

K2_LABELS: dict[str, str] = {
    "A": "consensus_match_winner",
    "B": "closing_match_winner",
    "C": "sharp_match_winner",
    "D": "direct_first_team_to_score",
    "E": "sharp_first_team_to_score",
    "F": "combined_fg_consensus",
}

FG_MARKET_RULES: tuple[tuple[str, str, str], ...] = (
    ("first_team_to_score", "First Team To Score", r"first team to score|team to score first"),
    ("last_team_to_score", "Last Team To Score", r"last team to score"),
    ("home_team_score_goal", "Home Team Score a Goal", r"home team score a goal"),
    ("away_team_score_goal", "Away Team Score a Goal", r"away team score a goal"),
    ("first_half_exact_goals", "First Half Exact Goals", r"first half exact goals"),
    ("first_10_min_winner", "First 10 min Winner", r"first 10 min winner"),
    ("time_of_first_corner", "Time of First Corner", r"time of first corner"),
    ("team_goalscorer", "Team Goalscorer", r"team goalscorer"),
)


def _classify_fg_market(name: str) -> str | None:
    n = name.lower()
    for key, _label, pattern in FG_MARKET_RULES:
        if re.search(pattern, n):
            return key
    if re.search(r"first.*goal|goal.*first", n) and "correct score" not in n:
        return "other_first_goal_related"
    return None


def _fts_side(label: str) -> str | None:
    lab = label.lower().strip()
    if lab in ("1", "home"):
        return "home"
    if lab in ("2", "away"):
        return "away"
    if lab in ("x", "draw", "no goal", "none"):
        return "none"
    return None


def parse_first_goal_markets(payload: Any) -> dict[str, Any]:
    """Extended parse: per-tier FTS + per-book snapshots."""
    base = parse_uefa_odds_deep(payload)
    raw = _fixture_data(payload)
    out = dict(base)
    if not raw:
        return out

    fts_all: dict[str, list[float]] = defaultdict(list)
    fts_sharp: dict[str, list[float]] = defaultdict(list)
    fts_soft: dict[str, list[float]] = defaultdict(list)
    fts_by_book: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    fg_market_hits: Counter[str] = Counter()

    for entry in raw.get("odds") or []:
        if not isinstance(entry, dict):
            continue
        mname = str((entry.get("market") or {}).get("name") or entry.get("market_description") or "")
        fg_key = _classify_fg_market(mname)
        if fg_key:
            fg_market_hits[fg_key] += 1
        if fg_key != "first_team_to_score":
            continue
        label = str(entry.get("label") or entry.get("name") or "")
        side = _fts_side(label)
        if side not in ("home", "away"):
            continue
        dec = _float(entry.get("value") or entry.get("dp3"))
        impl = _implied(dec)
        if impl is None:
            continue
        bname = _bookmaker_name(entry)
        tier = _book_tier(bname)
        fts_all[side].append(impl)
        if tier == "sharp":
            fts_sharp[side].append(impl)
        elif tier == "soft":
            fts_soft[side].append(impl)
        if bname:
            fts_by_book[bname.lower()][side].append(impl)

    def _mean(vals: list[float]) -> float | None:
        return round(statistics.mean(vals), 4) if vals else None

    out["sharp_first_team_score_home"] = _mean(fts_sharp["home"])
    out["sharp_first_team_score_away"] = _mean(fts_sharp["away"])
    out["soft_first_team_score_home"] = _mean(fts_soft["home"])
    out["soft_first_team_score_away"] = _mean(fts_soft["away"])
    out["fg_market_hits"] = dict(fg_market_hits)
    out["fts_bookmaker_count"] = len(fts_by_book)
    out["fts_by_book"] = {
        bk: {s: _mean(v) for s, v in sides.items()}
        for bk, sides in fts_by_book.items()
    }
    return out


def _cache_paths(settings=None) -> list[Path]:
    from worldcup_predictor.config.settings import get_settings

    settings = settings or get_settings()
    root_base = uefa_data_root(settings)
    seen: set[int] = set()
    paths: list[Path] = []
    for root in (
        root_base / "egie" / "uefa_club" / "raw",
        root_base / "data" / "egie" / "uefa_club" / "raw",
    ):
        if not root.is_dir():
            continue
        for p in root.glob("*.json"):
            try:
                fid = int(p.stem)
            except ValueError:
                continue
            if fid in seen:
                continue
            seen.add(fid)
            paths.append(p)
    return paths


def audit_first_goal_market_inventory() -> dict[str, Any]:
    paths = _cache_paths()
    market_fixture: Counter[str] = Counter()
    market_rows: Counter[str] = Counter()
    label_samples: dict[str, list[str]] = defaultdict(list)
    books: Counter[str] = Counter()

    for path in paths:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        raw = _fixture_data(blob.get("payload")) or {}
        seen_markets: set[str] = set()
        for entry in raw.get("odds") or []:
            if not isinstance(entry, dict):
                continue
            mname = str((entry.get("market") or {}).get("name") or entry.get("market_description") or "")
            key = _classify_fg_market(mname)
            if not key:
                continue
            market_rows[key] += 1
            seen_markets.add(key)
            lab = str(entry.get("label") or "")
            if len(label_samples[key]) < 8 and lab not in label_samples[key]:
                label_samples[key].append(lab)
            b = _bookmaker_name(entry)
            if b:
                books[b] += 1
        for k in seen_markets:
            market_fixture[k] += 1

    n = len(paths)
    markets = []
    for key, label, pattern in FG_MARKET_RULES:
        markets.append(
            {
                "market_key": key,
                "market_name": label,
                "pattern": pattern,
                "fixture_coverage": market_fixture.get(key, 0),
                "fixture_coverage_pct": round(100 * market_fixture.get(key, 0) / n, 2) if n else 0,
                "odds_row_count": market_rows.get(key, 0),
                "sample_labels": label_samples.get(key, []),
                "egie_usage": "D5/D6 enrichment" if key == "first_team_to_score" else "not wired",
            }
        )
    if market_fixture.get("other_first_goal_related"):
        markets.append(
            {
                "market_key": "other_first_goal_related",
                "fixture_coverage": market_fixture["other_first_goal_related"],
                "fixture_coverage_pct": round(100 * market_fixture["other_first_goal_related"] / n, 2),
            }
        )

    return {
        "fixtures_audited": n,
        "first_goal_related_markets": markets,
        "top_bookmakers_in_fg_markets": dict(books.most_common(15)),
        "primary_direct_fg_market": "first_team_to_score",
    }


def audit_first_goal_coverage() -> dict[str, Any]:
    paths = _cache_paths()
    n = len(paths)
    fields = {
        "consensus_match_winner": ("consensus_implied_home", "consensus_implied_away"),
        "closing_match_winner": ("closing_implied_home", "closing_implied_away"),
        "sharp_match_winner": ("sharp_implied_home", "sharp_implied_away"),
        "direct_fts_consensus": ("first_team_score_home", "first_team_score_away"),
        "sharp_fts": ("sharp_first_team_score_home", "sharp_first_team_score_away"),
    }
    counts = {k: 0 for k in fields}
    sharp_books = Counter()
    all_books = Counter()

    for path in paths:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        deep = parse_first_goal_markets(blob.get("payload"))
        for key, (hk, ak) in fields.items():
            if deep.get(hk) is not None and deep.get(ak) is not None:
                counts[key] += 1
        for bk in (deep.get("fts_by_book") or {}):
            all_books[bk] += 1
            if any(s in bk for s in SHARP_BOOKMAKERS):
                sharp_books[bk] += 1

    rows = []
    for key, (hk, ak) in fields.items():
        c = counts[key]
        rows.append(
            {
                "signal": key,
                "fixture_coverage": c,
                "fixture_coverage_pct": round(100 * c / n, 2) if n else 0,
                "bookmaker_coverage": c,
                "sharp_bookmaker_coverage": counts.get("sharp_fts", 0) if "fts" in key else counts.get("sharp_match_winner", 0),
                "historical_coverage_note": "Same cache as API-J UEFA finished fixtures",
            }
        )

    return {
        "fixtures_audited": n,
        "signals": rows,
        "fts_bookmakers_with_data": len(all_books),
        "sharp_fts_bookmakers": dict(sharp_books.most_common(10)),
    }


def _predict_k2(deep: dict[str, Any], strategy: K2Strategy) -> str | None:
    if strategy == "A":
        return _pick_side_from_implied(deep.get("consensus_implied_home"), deep.get("consensus_implied_away"))
    if strategy == "B":
        return _pick_side_from_implied(deep.get("closing_implied_home"), deep.get("closing_implied_away"))
    if strategy == "C":
        return _pick_side_from_implied(deep.get("sharp_implied_home"), deep.get("sharp_implied_away"))
    if strategy == "D":
        return _pick_side_from_implied(deep.get("first_team_score_home"), deep.get("first_team_score_away"))
    if strategy == "E":
        return _pick_side_from_implied(deep.get("sharp_first_team_score_home"), deep.get("sharp_first_team_score_away"))
    if strategy == "F":
        mh, ma = deep.get("consensus_implied_home"), deep.get("consensus_implied_away")
        fh, fa = deep.get("first_team_score_home"), deep.get("first_team_score_away")
        if mh is None or ma is None:
            return _pick_side_from_implied(fh, fa)
        if fh is None or fa is None:
            return _pick_side_from_implied(mh, ma)
        return _pick_side_from_implied((mh + fh) / 2, (ma + fa) / 2)
    return None


def _egie_pick_from_pressure(home: float, away: float) -> str:
    """Mirror baseline tie-band after +0.05 pressure nudge."""
    home_rate = 0.33 + (0.05 if home > away + 0.02 else 0.0)
    away_rate = 0.33 + (0.05 if away > home + 0.02 else 0.0)
    if abs(home_rate - away_rate) < 0.04:
        return "none"
    return "home" if home_rate > away_rate else "away"


def _signal_probs(deep: dict[str, Any], strategy: K2Strategy) -> tuple[float | None, float | None]:
    if strategy == "A":
        return deep.get("consensus_implied_home"), deep.get("consensus_implied_away")
    if strategy == "B":
        return deep.get("closing_implied_home"), deep.get("closing_implied_away")
    if strategy == "C":
        return deep.get("sharp_implied_home"), deep.get("sharp_implied_away")
    if strategy == "D":
        return deep.get("first_team_score_home"), deep.get("first_team_score_away")
    if strategy == "E":
        return deep.get("sharp_first_team_score_home"), deep.get("sharp_first_team_score_away")
    if strategy == "F":
        mh, ma = deep.get("consensus_implied_home"), deep.get("consensus_implied_away")
        fh, fa = deep.get("first_team_score_home"), deep.get("first_team_score_away")
        if None in (mh, ma, fh, fa):
            return mh or fh, ma or fa
        return (mh + fh) / 2, (ma + fa) / 2
    return None, None


def run_k2_backtest(fixtures: list[dict[str, Any]], *, settings=None) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings

    settings = settings or get_settings()
    strategies: tuple[K2Strategy, ...] = ("A", "B", "C", "D", "E", "F")
    results = {
        s: {
            "direct_correct": 0,
            "direct_wrong": 0,
            "egie_correct": 0,
            "egie_wrong": 0,
            "egie_pending": 0,
            "coverage": 0,
            "total_evaluable": 0,
        }
        for s in strategies
    }

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        if sm_id <= 0:
            continue
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        deep = parse_first_goal_markets(cache.get("payload"))
        result = parse_match_result(cache.get("payload"), home_team=str(fx.get("home_team") or ""), away_team=str(fx.get("away_team") or ""))
        actual = result.get("first_goal_team_side")
        if actual not in ("home", "away", "none"):
            continue

        for strategy in strategies:
            h, a = _signal_probs(deep, strategy)
            if h is None or a is None:
                continue
            results[strategy]["coverage"] += 1
            direct = _predict_k2(deep, strategy)
            egie_pick = _egie_pick_from_pressure(float(h), float(a))

            if actual == "none":
                continue
            results[strategy]["total_evaluable"] += 1

            if direct is not None:
                if direct == actual:
                    results[strategy]["direct_correct"] += 1
                else:
                    results[strategy]["direct_wrong"] += 1

            if egie_pick == "none":
                results[strategy]["egie_pending"] += 1
            elif egie_pick == actual:
                results[strategy]["egie_correct"] += 1
            else:
                results[strategy]["egie_wrong"] += 1

    summary = {}
    for s, r in results.items():
        ev = r["total_evaluable"]
        direct_decided = r["direct_correct"] + r["direct_wrong"]
        egie_decided = r["egie_correct"] + r["egie_wrong"]
        summary[s] = {
            "label": K2_LABELS[s],
            "coverage_fixtures": r["coverage"],
            "evaluable_with_goal": ev,
            "direct_fg_accuracy": round(r["direct_correct"] / direct_decided, 4) if direct_decided else None,
            "egie_fg_hit_rate": round(r["egie_correct"] / egie_decided, 4) if egie_decided else None,
            "egie_pending": r["egie_pending"],
            "egie_pending_rate": round(r["egie_pending"] / ev, 4) if ev else None,
            "direct_correct": r["direct_correct"],
            "direct_wrong": r["direct_wrong"],
            "egie_correct": r["egie_correct"],
            "egie_wrong": r["egie_wrong"],
        }
    return {"strategies": summary, "fixtures_in_mapping": len(fixtures)}


def analyze_bookmaker_fg_accuracy(fixtures: list[dict[str, Any]], *, settings=None) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings

    settings = settings or get_settings()
    book_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    mw_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        deep = parse_first_goal_markets(cache.get("payload"))
        result = parse_match_result(cache.get("payload"), home_team=str(fx.get("home_team") or ""), away_team=str(fx.get("away_team") or ""))
        actual = result.get("first_goal_team_side")
        if actual not in ("home", "away"):
            continue

        for bk, sides in (deep.get("fts_by_book") or {}).items():
            pred = _pick_side_from_implied(sides.get("home"), sides.get("away"))
            if pred is None:
                continue
            book_stats[bk]["total"] += 1
            if pred == actual:
                book_stats[bk]["correct"] += 1

        pred_mw = _pick_side_from_implied(deep.get("consensus_implied_home"), deep.get("consensus_implied_away"))
        if pred_mw:
            key = "consensus_match_winner"
            mw_stats[key]["total"] += 1
            if pred_mw == actual:
                mw_stats[key]["correct"] += 1

    ranked = []
    for bk, st in book_stats.items():
        if st["total"] < 5:
            continue
        tier = _book_tier(bk)
        ranked.append(
            {
                "bookmaker": bk,
                "tier": tier,
                "fts_fg_hit_rate": round(st["correct"] / st["total"], 4),
                "sample_size": st["total"],
            }
        )
    ranked.sort(key=lambda x: (x["fts_fg_hit_rate"], x["sample_size"]), reverse=True)

    focus = ["pinnacle", "sbo", "bet365", "1xbet", "betway", "williamhill"]
    focus_rows = [r for r in ranked if any(f in r["bookmaker"] for f in focus)]
    present = {f for r in focus_rows for f in focus if f in r["bookmaker"]}
    absent_focus = [f for f in focus if f not in present and not any(f in r["bookmaker"] for r in ranked)]

    return {
        "fts_per_bookmaker": ranked[:25],
        "focus_bookmakers": focus_rows,
        "focus_bookmakers_absent": absent_focus,
        "baseline_consensus_mw": mw_stats.get("consensus_match_winner"),
        "note": "Per-book accuracy uses First Team To Score market only",
    }


def rank_k2_signals(backtest: dict[str, Any], book_analysis: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for key, data in (backtest.get("strategies") or {}).items():
        hr = data.get("direct_fg_accuracy")
        rows.append(
            {
                "signal": key,
                "label": data.get("label"),
                "fg_hit_rate": hr,
                "egie_fg_hit_rate": data.get("egie_fg_hit_rate"),
                "coverage": data.get("coverage_fixtures"),
                "pending_rate": data.get("egie_pending_rate"),
                "source": "k2_backtest",
            }
        )

    best_fts_book = (book_analysis.get("fts_per_bookmaker") or [None])[0]
    if best_fts_book:
        rows.append(
            {
                "signal": "best_fts_book",
                "label": f"FTS @ {best_fts_book.get('bookmaker')}",
                "fg_hit_rate": best_fts_book.get("fts_fg_hit_rate"),
                "coverage": best_fts_book.get("sample_size"),
                "source": "per_bookmaker",
            }
        )

    def tier(hr: float | None) -> str:
        if hr is None:
            return "C"
        if hr >= 0.78:
            return "S"
        if hr >= 0.74:
            return "A"
        if hr >= 0.65:
            return "B"
        return "C"

    for r in rows:
        r["tier"] = tier(r.get("fg_hit_rate"))

    rows.sort(key=lambda x: (float(x.get("fg_hit_rate") or 0), int(x.get("coverage") or 0)), reverse=True)

    robust = [
        r
        for r in rows
        if r.get("fg_hit_rate") is not None and int(r.get("coverage") or 0) >= 50
    ]
    strongest_robust = robust[0] if robust else None
    strongest_peak = rows[0] if rows else None
    strongest = strongest_robust or strongest_peak

    return {
        "ranked": rows,
        "strongest_signal": strongest,
        "strongest_signal_robust": strongest_robust,
        "strongest_signal_peak": strongest_peak,
        "min_coverage_for_robust": 50,
    }
