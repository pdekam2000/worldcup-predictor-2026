"""Phase API-K — UEFA Sportmonks odds deep parse, audit, and sub-strategy enrichment."""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.egie.uefa_club.feature_extractors import _fixture_data, _float
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import uefa_data_root

OddsSubStrategy = Literal["A", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]

ODDS_SUBSTRATEGY_LABELS: dict[str, str] = {
    "A": "baseline",
    "D1": "opening_odds_only",
    "D2": "closing_odds_only",
    "D3": "odds_movement_only",
    "D4": "implied_probabilities_only",
    "D5": "first_goal_odds_only",
    "D6": "team_to_score_first_only",
    "D7": "sharp_consensus_odds",
    "D8": "full_odds_package",
}

SHARP_BOOKMAKERS = frozenset(
    {"pinnacle", "sbo", "sbobet", "asianodds", "betfair", "matchbook"}
)
SOFT_BOOKMAKERS = frozenset(
    {"bet365", "williamhill", "1xbet", "betway", "10bet", "unibet", "bwin", "betclic", "tipico"}
)

MARKET_ALIASES: dict[str, tuple[str, ...]] = {
    "match_winner": ("fulltime result", "match winner", "1x2", "full time result"),
    "double_chance": ("double chance",),
    "btts": ("both teams to score", "both teams score"),
    "over_under": ("goals over/under", "goal line", "alternative goal line"),
    "first_team_to_score": ("first team to score", "first goal", "team to score first"),
    "half_time_result": ("half time result", "1st half result"),
    "first_half_goals": ("1st half goals", "first half goals"),
    "home_team_goals": ("home team goals", "home team score a goal"),
    "away_team_goals": ("away team goals", "away team score a goal"),
    "correct_score": ("correct score",),
    "asian_handicap": ("asian handicap",),
}


def _implied(decimal: float | None) -> float | None:
    if decimal is None or decimal <= 1.0:
        return None
    return round(1.0 / decimal, 4)


def _market_key(name: str) -> str | None:
    n = name.lower().strip()
    for key, hints in MARKET_ALIASES.items():
        if any(h in n for h in hints):
            return key
    return None


def _parse_ts(value: Any) -> float:
    if not value:
        return 0.0
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return 0.0


def _side_from_label(label: str) -> str | None:
    lab = label.lower().strip()
    if lab in ("1", "home"):
        return "home"
    if lab in ("2", "away"):
        return "away"
    if lab in ("x", "draw"):
        return "draw"
    if lab in ("yes", "over"):
        return "yes"
    if lab in ("no", "under"):
        return "no"
    return None


def _bookmaker_name(entry: dict[str, Any]) -> str:
    return str((entry.get("bookmaker") or {}).get("name") or "").strip()


def _book_tier(name: str) -> str:
    low = name.lower()
    if any(s in low for s in SHARP_BOOKMAKERS):
        return "sharp"
    if any(s in low for s in SOFT_BOOKMAKERS):
        return "soft"
    return "other"


def parse_uefa_odds_deep(payload: Any) -> dict[str, Any]:
    """Extract opening/closing/consensus/sharp/soft and specialty markets from Sportmonks odds[]."""
    raw = _fixture_data(payload)
    empty: dict[str, Any] = {
        "opening_implied_home": None,
        "opening_implied_draw": None,
        "opening_implied_away": None,
        "closing_implied_home": None,
        "closing_implied_draw": None,
        "closing_implied_away": None,
        "consensus_implied_home": None,
        "consensus_implied_draw": None,
        "consensus_implied_away": None,
        "sharp_implied_home": None,
        "sharp_implied_away": None,
        "soft_implied_home": None,
        "soft_implied_away": None,
        "movement_home": None,
        "movement_away": None,
        "first_team_score_home": None,
        "first_team_score_away": None,
        "btts_yes_implied": None,
        "over_25_implied": None,
        "favorite_strength": None,
        "market_counts": {},
        "bookmaker_count": 0,
        "has_match_winner": False,
        "has_first_team_to_score": False,
        "has_movement": False,
    }
    if not raw:
        return empty

    odds = raw.get("odds")
    if not isinstance(odds, list) or not odds:
        return empty

    market_counts: Counter[str] = Counter()
    books: set[str] = set()
    mw_by_time: dict[str, list[tuple[float, str, float, str]]] = defaultdict(list)
    fts_implied: dict[str, list[float]] = defaultdict(list)
    mw_implied_all: dict[str, list[float]] = defaultdict(list)
    sharp_mw: dict[str, list[float]] = defaultdict(list)
    soft_mw: dict[str, list[float]] = defaultdict(list)
    btts_yes: list[float] = []
    over_25: list[float] = []

    for entry in odds:
        if not isinstance(entry, dict):
            continue
        mname = str((entry.get("market") or {}).get("name") or entry.get("market_description") or "")
        mkey = _market_key(mname)
        if mkey:
            market_counts[mkey] += 1
        bname = _bookmaker_name(entry)
        if bname:
            books.add(bname.lower())
        label = str(entry.get("label") or entry.get("name") or "")
        side = _side_from_label(label)
        dec = _float(entry.get("value") or entry.get("dp3") or entry.get("odd"))
        impl = _implied(dec)
        if impl is None:
            continue
        ts = _parse_ts(entry.get("created_at"))
        tier = _book_tier(bname)

        if mkey == "match_winner" and side in ("home", "draw", "away"):
            mw_by_time["all"].append((ts, side, impl, bname))
            mw_implied_all[side].append(impl)
            if tier == "sharp":
                sharp_mw[side].append(impl)
            elif tier == "soft":
                soft_mw[side].append(impl)
        elif mkey == "first_team_to_score" and side in ("home", "away"):
            fts_implied[side].append(impl)
        elif mkey == "btts" and side == "yes":
            btts_yes.append(impl)
        elif mkey == "over_under" and side == "yes":
            total = str(entry.get("total") or entry.get("name") or "")
            if total in ("2.5", "2.50", "2.5 goals"):
                over_25.append(impl)

    def _mean(vals: list[float]) -> float | None:
        return round(statistics.mean(vals), 4) if vals else None

    def _opening_closing(side: str) -> tuple[float | None, float | None]:
        rows = [(t, impl) for t, s, impl, _ in mw_by_time["all"] if s == side]
        if not rows:
            return None, None
        rows.sort(key=lambda x: x[0])
        return rows[0][1], rows[-1][1]

    oh, ch = _opening_closing("home")
    od, cd = _opening_closing("draw")
    oa, ca = _opening_closing("away")

    out = dict(empty)
    out["opening_implied_home"], out["closing_implied_home"] = oh, ch
    out["opening_implied_draw"], out["closing_implied_draw"] = od, cd
    out["opening_implied_away"], out["closing_implied_away"] = oa, ca
    out["consensus_implied_home"] = _mean(mw_implied_all["home"])
    out["consensus_implied_draw"] = _mean(mw_implied_all["draw"])
    out["consensus_implied_away"] = _mean(mw_implied_all["away"])
    out["sharp_implied_home"] = _mean(sharp_mw["home"])
    out["sharp_implied_away"] = _mean(sharp_mw["away"])
    out["soft_implied_home"] = _mean(soft_mw["home"])
    out["soft_implied_away"] = _mean(soft_mw["away"])
    if ch is not None and oh is not None:
        out["movement_home"] = round(ch - oh, 4)
        out["has_movement"] = True
    if ca is not None and oa is not None:
        out["movement_away"] = round(ca - oa, 4)
    out["first_team_score_home"] = _mean(fts_implied["home"])
    out["first_team_score_away"] = _mean(fts_implied["away"])
    out["btts_yes_implied"] = _mean(btts_yes)
    out["over_25_implied"] = _mean(over_25)
    out["market_counts"] = dict(market_counts)
    out["bookmaker_count"] = len(books)
    out["has_match_winner"] = bool(mw_implied_all["home"])
    out["has_first_team_to_score"] = bool(fts_implied["home"] or fts_implied["away"])

    hi = out["consensus_implied_home"] or 0
    ai = out["consensus_implied_away"] or 0
    if hi or ai:
        out["favorite_strength"] = round(abs(hi - ai), 4)

    # Legacy fields for feature store compatibility
    out["odds_implied_home"] = out["consensus_implied_home"]
    out["odds_implied_draw"] = out["consensus_implied_draw"]
    out["odds_implied_away"] = out["consensus_implied_away"]
    out["implied_home"] = out["consensus_implied_home"]
    out["implied_draw"] = out["consensus_implied_draw"]
    out["implied_away"] = out["consensus_implied_away"]
    out["first_goal_odds"] = out["first_team_score_home"]
    out["odds_movement"] = out["movement_home"]
    return out


def _cache_paths(settings=None) -> list[Path]:
    from worldcup_predictor.config.settings import get_settings

    settings = settings or get_settings()
    seen: set[int] = set()
    paths: list[Path] = []
    for root in (
        uefa_data_root(settings) / "egie" / "uefa_club" / "raw",
        uefa_data_root(settings) / "data" / "egie" / "uefa_club" / "raw",
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


def audit_odds_inventory(*, fixture_count: int | None = None) -> dict[str, Any]:
    paths = _cache_paths()
    n = len(paths)
    market_fixture_hits: Counter[str] = Counter()
    field_hits: Counter[str] = Counter()
    bookmakers: Counter[str] = Counter()

    inventory_fields = [
        ("match_winner", "Match Winner / Fulltime Result", "consensus_implied_home", "parse_uefa_odds_deep"),
        ("double_chance", "Double Chance", None, "available in cache, not wired to EGIE"),
        ("btts", "Both Teams To Score", "btts_yes_implied", "parse_uefa_odds_deep"),
        ("over_under", "Over/Under 2.5", "over_25_implied", "parse_uefa_odds_deep"),
        ("first_team_to_score", "First Team To Score", "first_team_score_home", "parse_uefa_odds_deep"),
        ("first_half_goals", "1st Half Goals", None, "cache only"),
        ("asian_handicap", "Asian Handicap", None, "cache only"),
        ("movement", "Odds Movement", "movement_home", "opening vs closing 1X2"),
        ("consensus", "Market Consensus", "consensus_implied_home", "mean across books"),
        ("sharp_soft", "Sharp vs Soft", "sharp_implied_home", "Pinnacle/SBO vs recreational"),
    ]

    with_odds = 0
    for path in paths:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        deep = parse_uefa_odds_deep(blob.get("payload"))
        if deep.get("has_match_winner"):
            with_odds += 1
        for key, count in (deep.get("market_counts") or {}).items():
            market_fixture_hits[key] += 1
        for field in (
            "consensus_implied_home",
            "consensus_implied_away",
            "consensus_implied_draw",
            "opening_implied_home",
            "closing_implied_home",
            "movement_home",
            "first_team_score_home",
            "btts_yes_implied",
            "over_25_implied",
            "sharp_implied_home",
        ):
            if deep.get(field) is not None:
                field_hits[field] += 1
        payload = _fixture_data(blob.get("payload")) or {}
        for entry in payload.get("odds") or []:
            if isinstance(entry, dict):
                b = _bookmaker_name(entry)
                if b:
                    bookmakers[b] += 1

    rows = []
    for mkey, label, feat, usage in inventory_fields:
        rows.append(
            {
                "market": label,
                "market_key": mkey,
                "source_provider": "sportmonks",
                "storage_location": "data/egie/uefa_club/raw/{fixture_id}.json -> payload.data.odds[]",
                "feature_name": feat,
                "feature_usage": usage,
                "fixture_coverage_pct": round(100 * market_fixture_hits.get(mkey, 0) / n, 2) if n and mkey in MARKET_ALIASES else round(100 * field_hits.get(feat or "", 0) / n, 2) if feat and n else None,
                "fixtures_with_market": market_fixture_hits.get(mkey, field_hits.get(feat or "", 0)),
            }
        )

    legacy_egie = [
        {
            "feature_name": "odds_implied_home",
            "source_provider": "sportmonks",
            "storage_location": "UefaClubFeatureStore via parse_uefa_odds",
            "coverage_pct": round(100 * field_hits["consensus_implied_home"] / n, 2) if n else 0,
            "feature_usage": "enrich_agent_outputs -> first_goal_pressure (Strategy D)",
        },
        {
            "feature_name": "odds_implied_away",
            "source_provider": "sportmonks",
            "coverage_pct": round(100 * field_hits["consensus_implied_away"] / n, 2) if n else 0,
            "feature_usage": "enrich_agent_outputs -> first_goal_pressure",
        },
        {
            "feature_name": "odds_implied_draw",
            "source_provider": "sportmonks",
            "coverage_pct": round(100 * field_hits["consensus_implied_draw"] / n, 2) if n else 0,
            "feature_usage": "odds_goal_intelligence agent signal only (not FG pick path)",
        },
        {
            "feature_name": "first_goal_odds",
            "source_provider": "sportmonks",
            "coverage_pct": round(100 * field_hits["first_team_score_home"] / n, 2) if n else 0,
            "feature_usage": "parsed but not used in production enrichment",
        },
        {
            "feature_name": "odds_movement",
            "source_provider": "sportmonks",
            "coverage_pct": round(100 * field_hits["movement_home"] / n, 2) if n else 0,
            "feature_usage": "stored on ProviderFeatureVector; not applied in Strategy D enrichment",
        },
    ]

    return {
        "fixtures_audited": n,
        "fixtures_with_any_odds": with_odds,
        "market_inventory": rows,
        "legacy_egie_fields": legacy_egie,
        "top_bookmakers": dict(bookmakers.most_common(15)),
        "field_coverage": {k: round(100 * v / n, 2) for k, v in field_hits.items()} if n else {},
    }


def _pick_side_from_implied(home: float | None, away: float | None) -> str | None:
    if home is None or away is None:
        return None
    if abs(home - away) < 0.02:
        return None
    return "home" if home > away else "away"


def compute_odds_attribution(
    fixtures: list[dict[str, Any]],
    *,
    settings=None,
) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
    from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
    from worldcup_predictor.goal_timing.evaluation import minute_to_range

    settings = settings or get_settings()
    signals = {
        "consensus_1x2": ("consensus_implied_home", "consensus_implied_away"),
        "opening_1x2": ("opening_implied_home", "opening_implied_away"),
        "closing_1x2": ("closing_implied_home", "closing_implied_away"),
        "sharp_1x2": ("sharp_implied_home", "sharp_implied_away"),
        "soft_1x2": ("soft_implied_home", "soft_implied_away"),
        "first_team_to_score": ("first_team_score_home", "first_team_score_away"),
        "movement_direction": ("movement_home", "movement_away"),
    }
    stats = {k: {"fg_correct": 0, "fg_total": 0, "range_correct": 0, "range_total": 0, "minute_soft": 0, "minute_total": 0} for k in signals}
    stats["favorite_strength"] = {"fg_correct": 0, "fg_total": 0}

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        if sm_id <= 0:
            continue
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        deep = parse_uefa_odds_deep(cache.get("payload"))
        result = parse_match_result(cache.get("payload"), home_team=str(fx.get("home_team") or ""), away_team=str(fx.get("away_team") or ""))
        actual_fg = result.get("first_goal_team_side")
        actual_min = result.get("first_goal_minute")
        actual_range = minute_to_range(actual_min)
        if actual_fg not in ("home", "away", "none"):
            continue

        for sig, (hk, ak) in signals.items():
            if sig == "movement_direction":
                mh, ma = deep.get(hk), deep.get(ak)
                if mh is None and ma is None:
                    continue
                pred = "home" if (mh or 0) > (ma or 0) else "away" if (ma or 0) > (mh or 0) else None
            else:
                pred = _pick_side_from_implied(deep.get(hk), deep.get(ak))
            if pred is None or actual_fg == "none":
                continue
            bucket = stats[sig]
            bucket["fg_total"] += 1
            if pred == actual_fg:
                bucket["fg_correct"] += 1

        fav_h = deep.get("consensus_implied_home")
        fav_a = deep.get("consensus_implied_away")
        if fav_h is not None and fav_a is not None and actual_fg in ("home", "away"):
            stats["favorite_strength"]["fg_total"] += 1
            fav = "home" if fav_h >= fav_a else "away"
            if fav == actual_fg:
                stats["favorite_strength"]["fg_correct"] += 1

    def _rate(d: dict[str, int]) -> float | None:
        return round(d["fg_correct"] / d["fg_total"], 4) if d.get("fg_total") else None

    ranked = sorted(
        [{"signal": k, "fg_hit_rate": _rate(v), **v} for k, v in stats.items()],
        key=lambda x: float(x.get("fg_hit_rate") or 0),
        reverse=True,
    )
    return {
        "signals": ranked,
        "note": "Direct market-implied side vs actual FG (independent of EGIE model)",
    }


def analyze_market_efficiency(fixtures: list[dict[str, Any]], *, settings=None) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
    from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache

    settings = settings or get_settings()
    markets = {
        "match_winner_favorite": {"correct": 0, "total": 0},
        "first_team_to_score": {"correct": 0, "total": 0},
        "over_25_favorite": {"correct": 0, "total": 0},
    }
    stability: list[float] = []
    favorite_reliability = {"favorite_wins_fg": 0, "underdog_wins_fg": 0, "total": 0}

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        deep = parse_uefa_odds_deep(cache.get("payload"))
        result = parse_match_result(cache.get("payload"), home_team=str(fx.get("home_team") or ""), away_team=str(fx.get("away_team") or ""))
        actual_fg = result.get("first_goal_team_side")
        total_goals = int(result.get("home_goals") or 0) + int(result.get("away_goals") or 0)

        ch, oh = deep.get("closing_implied_home"), deep.get("opening_implied_home")
        if ch is not None and oh is not None:
            stability.append(abs(ch - oh))

        h, a = deep.get("consensus_implied_home"), deep.get("consensus_implied_away")
        if h is not None and a is not None and actual_fg in ("home", "away"):
            markets["match_winner_favorite"]["total"] += 1
            fav = "home" if h >= a else "away"
            if fav == actual_fg:
                markets["match_winner_favorite"]["correct"] += 1
            favorite_reliability["total"] += 1
            if fav == actual_fg:
                favorite_reliability["favorite_wins_fg"] += 1
            else:
                favorite_reliability["underdog_wins_fg"] += 1

        fh, fa = deep.get("first_team_score_home"), deep.get("first_team_score_away")
        if fh is not None and fa is not None and actual_fg in ("home", "away"):
            markets["first_team_to_score"]["total"] += 1
            pick = "home" if fh >= fa else "away"
            if pick == actual_fg:
                markets["first_team_to_score"]["correct"] += 1

        ou = deep.get("over_25_implied")
        if ou is not None:
            markets["over_25_favorite"]["total"] += 1
            pred_over = ou > 0.5
            if (total_goals > 2.5) == pred_over:
                markets["over_25_favorite"]["correct"] += 1

    def _hr(m: dict[str, int]) -> float | None:
        return round(m["correct"] / m["total"], 4) if m["total"] else None

    return {
        "markets": {k: {**v, "hit_rate": _hr(v)} for k, v in markets.items()},
        "line_stability": {
            "mean_abs_open_close_home_move": round(statistics.mean(stability), 4) if stability else None,
            "samples": len(stability),
        },
        "favorite_reliability": {
            **favorite_reliability,
            "favorite_fg_rate": round(favorite_reliability["favorite_wins_fg"] / favorite_reliability["total"], 4)
            if favorite_reliability["total"]
            else None,
        },
        "highly_predictive_markets": sorted(
            [k for k, v in markets.items() if (_hr(v) or 0) >= 0.55],
            key=lambda k: _hr(markets[k]) or 0,
            reverse=True,
        ),
    }


def analyze_sharp_vs_soft(fixtures: list[dict[str, Any]], *, settings=None) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
    from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache

    settings = settings or get_settings()
    tiers = {
        "sharp": {"fg_correct": 0, "fg_total": 0, "fixtures_with_data": 0},
        "soft": {"fg_correct": 0, "fg_total": 0, "fixtures_with_data": 0},
        "consensus": {"fg_correct": 0, "fg_total": 0, "fixtures_with_data": 0},
    }

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        deep = parse_uefa_odds_deep(cache.get("payload"))
        result = parse_match_result(cache.get("payload"), home_team=str(fx.get("home_team") or ""), away_team=str(fx.get("away_team") or ""))
        actual_fg = result.get("first_goal_team_side")
        if actual_fg not in ("home", "away"):
            continue

        for tier, hk, ak in (
            ("sharp", "sharp_implied_home", "sharp_implied_away"),
            ("soft", "soft_implied_home", "soft_implied_away"),
            ("consensus", "consensus_implied_home", "consensus_implied_away"),
        ):
            pred = _pick_side_from_implied(deep.get(hk), deep.get(ak))
            if pred is None:
                continue
            tiers[tier]["fixtures_with_data"] += 1
            tiers[tier]["fg_total"] += 1
            if pred == actual_fg:
                tiers[tier]["fg_correct"] += 1

    bookmaker_level_available = any(tiers[t]["fg_total"] > 0 for t in ("sharp", "soft"))
    return {
        "bookmaker_level_data_available": bookmaker_level_available,
        "sharp_books": sorted(SHARP_BOOKMAKERS),
        "soft_books": sorted(SOFT_BOOKMAKERS),
        "comparison": {
            tier: {
                **data,
                "fg_hit_rate": round(data["fg_correct"] / data["fg_total"], 4) if data["fg_total"] else None,
            }
            for tier, data in tiers.items()
        },
        "limitation": None if bookmaker_level_available else "No bookmaker-tier splits in payload",
    }


def analyze_odds_movement(fixtures: list[dict[str, Any]], *, settings=None) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
    from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache

    settings = settings or get_settings()
    static = {"correct": 0, "total": 0}
    movement = {"correct": 0, "total": 0}
    steam_home = {"correct": 0, "total": 0}
    reverse = {"correct": 0, "total": 0}

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        deep = parse_uefa_odds_deep(cache.get("payload"))
        result = parse_match_result(cache.get("payload"), home_team=str(fx.get("home_team") or ""), away_team=str(fx.get("away_team") or ""))
        actual_fg = result.get("first_goal_team_side")
        if actual_fg not in ("home", "away"):
            continue

        closing_pred = _pick_side_from_implied(deep.get("closing_implied_home"), deep.get("closing_implied_away"))
        if closing_pred:
            static["total"] += 1
            if closing_pred == actual_fg:
                static["correct"] += 1

        mh, ma = deep.get("movement_home"), deep.get("movement_away")
        if mh is not None or ma is not None:
            move_pred = "home" if (mh or 0) > (ma or 0) else "away" if (ma or 0) > (mh or 0) else None
            if move_pred:
                movement["total"] += 1
                if move_pred == actual_fg:
                    movement["correct"] += 1
            if (mh or 0) > 0.02:
                steam_home["total"] += 1
                if actual_fg == "home":
                    steam_home["correct"] += 1
            open_pred = _pick_side_from_implied(deep.get("opening_implied_home"), deep.get("opening_implied_away"))
            if open_pred and closing_pred and open_pred != closing_pred:
                reverse["total"] += 1
                if closing_pred == actual_fg:
                    reverse["correct"] += 1

    def _hr(d: dict[str, int]) -> float | None:
        return round(d["correct"] / d["total"], 4) if d["total"] else None

    move_hr, static_hr = _hr(movement), _hr(static)
    return {
        "static_closing_odds": {**static, "hit_rate": static_hr},
        "movement_direction": {**movement, "hit_rate": move_hr},
        "steam_moves_home": {**steam_home, "hit_rate": _hr(steam_home)},
        "reverse_line_moves": {**reverse, "hit_rate": _hr(reverse)},
        "movement_outperforms_static": (move_hr or 0) > (static_hr or 0) if move_hr and static_hr else None,
    }


def rank_odds_signals(
    attribution: dict[str, Any],
    backtest: dict[str, Any],
) -> dict[str, Any]:
    base_fg = float((backtest.get("strategies") or {}).get("A", {}).get("first_goal_team_hit_rate") or 0)
    rows: list[dict[str, Any]] = []

    for strat in ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"):
        s = (backtest.get("strategies") or {}).get(strat) or {}
        fg = s.get("first_goal_team_hit_rate")
        delta = (float(fg) - base_fg) if fg is not None else None
        cov = (s.get("coverage") or {}).get("with_odds_data", 0)
        rows.append(
            {
                "signal": strat,
                "label": ODDS_SUBSTRATEGY_LABELS.get(strat, strat),
                "egie_fg_hit_rate": fg,
                "fg_delta_vs_a": round(delta, 4) if delta is not None else None,
                "coverage": cov,
                "pending_rate": s.get("fg_pending_rate"),
            }
        )

    for item in attribution.get("signals") or []:
        rows.append(
            {
                "signal": f"direct_{item.get('signal')}",
                "label": f"Direct market: {item.get('signal')}",
                "direct_fg_hit_rate": item.get("fg_hit_rate"),
                "fg_delta_vs_a": None,
                "coverage": item.get("fg_total"),
            }
        )

    def _tier(delta: float | None, hr: float | None) -> str:
        d = delta if delta is not None else 0
        h = hr or 0
        if d >= 0.20 or h >= 0.65:
            return "S"
        if d >= 0.08 or h >= 0.55:
            return "A"
        if d >= 0.02 or h >= 0.48:
            return "B"
        return "C"

    for r in rows:
        r["tier"] = _tier(r.get("fg_delta_vs_a"), r.get("egie_fg_hit_rate") or r.get("direct_fg_hit_rate"))

    rows.sort(
        key=lambda x: float(x.get("fg_delta_vs_a") or x.get("egie_fg_hit_rate") or x.get("direct_fg_hit_rate") or 0),
        reverse=True,
    )
    return {"ranked_signals": rows, "baseline_a_fg": base_fg, "tier_legend": {"S": "highest", "A": "strong", "B": "moderate", "C": "little value"}}
