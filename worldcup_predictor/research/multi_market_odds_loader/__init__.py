"""
Parallel multi-market research odds loader (read-only).

Reads REAL priced markets from odds_snapshots + correct_score_odds_lines.
Does NOT replace Canonical 1X2 freshness gate used for predictions.
Does NOT write production data.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    NormalizedOddsLine,
    extract_bookmakers_from_payload,
    normalize_snapshot_odds_lines,
)
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.research.winning_dna_daily_matcher.today_fixtures import open_ro

FRESH_OK = frozenset(
    {
        FreshnessStatus.FRESH_ODDS.value,
        "ODDS_FRESH",
        "FRESH_ODDS",
        "FRESH",
        "fresh",
    }
)

RESEARCH_ONLY = True
PUBLIC_VISIBLE = False
FINAL_DECISION_AUTHORITY = False


@dataclass
class MarketPrice:
    market_family: str
    selection: str
    decimal_odds: float
    bookmaker: str | None
    odds_lane: str  # REAL | ESTIMATED
    source: str
    timestamp: str | None
    freshness: str | None
    n_bookmakers: int = 1
    raw_market_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MultiMarketBundle:
    fixture_id: int
    snapshot_at: str | None
    freshness_class: str | None
    prices: list[MarketPrice] = field(default_factory=list)
    coverage: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "snapshot_at": self.snapshot_at,
            "freshness_class": self.freshness_class,
            "prices": [p.to_dict() for p in self.prices],
            "coverage": self.coverage,
            "n_prices": len(self.prices),
        }


def _median(xs: list[float]) -> float | None:
    vals = [float(x) for x in xs if x is not None and float(x) > 1.01]
    if not vals:
        return None
    return float(statistics.median(vals))


def _norm_sel(s: str) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _classify_and_select(line: NormalizedOddsLine) -> tuple[str, str] | None:
    """Map a raw line to (family, selection) for research inventory."""
    name = str(line.market_name or "").lower()
    sel = str(line.selection or "").strip()
    sel_l = sel.lower()

    # 1X2
    if name in {"match winner", "1x2", "ft_result", "match result", "home/draw/away", "full time result", "home draw away"}:
        key = {"home": "home", "draw": "draw", "away": "away"}.get(sel_l)
        if key:
            return "1x2", key

    # Double chance
    if "double chance" in name:
        mapping = {
            "home/draw": "1x",
            "home/away": "12",
            "draw/away": "x2",
            "1x": "1x",
            "12": "12",
            "x2": "x2",
        }
        key = mapping.get(sel_l.replace(" ", ""))
        if key:
            return "double_chance", key

    # DNB
    if "draw no bet" in name:
        if sel_l in {"home", "1"}:
            return "draw_no_bet", "home"
        if sel_l in {"away", "2"}:
            return "draw_no_bet", "away"

    # BTTS
    if name in {"both teams score", "btts", "both teams to score"} or "both teams" in name:
        if "yes" in sel_l:
            return "btts", "yes"
        if "no" in sel_l:
            return "btts", "no"

    # Over/Under totals (exclude team totals / halves)
    if any(t in name for t in ("first half", "second half", "corner", "team total", "home team", "away team")):
        pass
    elif "over/under" in name or "goals over" in name or name in {"totals", "total_goals", "goals"}:
        for line_v, fam_sel in (
            ("0.5", ("over_0_5", "under_0_5")),
            ("1.5", ("over_1_5", "under_1_5")),
            ("2.5", ("over_2_5", "under_2_5")),
            ("3.5", ("over_3_5", "under_3_5")),
            ("4.5", ("over_4_5", "under_4_5")),
        ):
            if line_v in sel_l:
                if sel_l.startswith("over") or " over" in f" {sel_l}":
                    return "over_under", fam_sel[0]
                if sel_l.startswith("under") or " under" in f" {sel_l}":
                    return "over_under", fam_sel[1]

    # Correct score
    if "correct score" in name or "exact score" in name:
        if "-" in sel and sel_l[0].isdigit():
            return "exact_score", sel.replace(" ", "")

    # HT result
    if ("half time" in name or "1st half" in name or "first half" in name) and any(
        x in name for x in ("result", "winner", "1x2")
    ):
        key = {"home": "home", "draw": "draw", "away": "away"}.get(sel_l)
        if key:
            return "ht_1x2", key

    # HT/FT
    if "ht/ft" in name or "half time/full time" in name or "halftime/fulltime" in name:
        cleaned = sel_l.replace(" ", "").replace("-", "/")
        if "/" in cleaned and len(cleaned.split("/")) == 2:
            return "ht_ft", cleaned

    # Asian handicap
    if "asian handicap" in name:
        return "asian_handicap", _norm_sel(sel)

    # European handicap
    if "european handicap" in name or (name.strip() == "handicap"):
        return "european_handicap", _norm_sel(sel)

    # Clean sheet
    if "clean sheet" in name:
        if "yes" in sel_l or "home" in sel_l:
            return "clean_sheet", _norm_sel(sel)
        return "clean_sheet", _norm_sel(sel)

    # Winning margin
    if "winning margin" in name:
        return "winning_margin", _norm_sel(sel)

    # Team totals
    if "team total" in name or "home team goals" in name or "away team goals" in name:
        return "team_goals", _norm_sel(sel)

    return None


def _latest_payload(conn, fixture_id: int) -> tuple[dict[str, Any] | None, str | None]:
    row = conn.execute(
        """
        SELECT snapshot_at, payload_json
        FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY snapshot_at DESC, rowid DESC
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None, None
    try:
        payload = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})
    except Exception:
        payload = {}
    return (payload if isinstance(payload, dict) else {}), str(row[0]) if row[0] else None


def _load_cs_prices(conn, fixture_id: int, *, freshness: str | None, snapshot_at: str | None) -> list[MarketPrice]:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "correct_score_odds_lines" not in tables:
        return []
    cols = {c[1] for c in conn.execute("PRAGMA table_info(correct_score_odds_lines)")}
    # Flexible column names
    sel_col = "selection" if "selection" in cols else ("scoreline" if "scoreline" in cols else None)
    odds_col = "decimal_odds" if "decimal_odds" in cols else ("odds" if "odds" in cols else None)
    if not sel_col or not odds_col:
        return []
    bm_col = "bookmaker" if "bookmaker" in cols else None
    q = f"SELECT {sel_col}, {odds_col}" + (f", {bm_col}" if bm_col else "") + " FROM correct_score_odds_lines WHERE fixture_id = ?"
    # Prefer prematch if column exists
    if "prematch_status" in cols:
        q += " AND COALESCE(prematch_status,'prematch') LIKE '%pre%'"
    rows = conn.execute(q + " LIMIT 200", (int(fixture_id),)).fetchall()
    buckets: dict[str, list[float]] = {}
    bms: dict[str, str] = {}
    for r in rows:
        sel = str(r[0]).replace(" ", "")
        try:
            odd = float(r[1])
        except Exception:
            continue
        if odd <= 1.01:
            continue
        buckets.setdefault(sel, []).append(odd)
        if bm_col and len(r) > 2 and r[2]:
            bms[sel] = str(r[2])
    out = []
    for sel, odds in buckets.items():
        med = _median(odds)
        if med is None:
            continue
        out.append(
            MarketPrice(
                market_family="exact_score",
                selection=sel,
                decimal_odds=round(med, 4),
                bookmaker=bms.get(sel),
                odds_lane="REAL",
                source="correct_score_odds_lines",
                timestamp=snapshot_at,
                freshness=freshness,
                n_bookmakers=len(odds),
                raw_market_name="Correct Score",
            )
        )
    return out


def load_multi_market_odds(
    fixture_id: int,
    *,
    kickoff_utc: str | None = None,
    require_fresh: bool = True,
) -> MultiMarketBundle:
    """
    Load all REAL market prices available for a fixture from storage.
    Freshness is taken from the Canonical 1X2 bridge for the same fixture
    (shared snapshot timing), without changing that bridge's prediction role.
    """
    conn = open_ro()
    try:
        snap_1x2 = get_latest_valid_1x2_odds_snapshot(conn, int(fixture_id), kickoff_utc=kickoff_utc)
        freshness = getattr(snap_1x2, "freshness_class", None)
        payload, snapshot_at = _latest_payload(conn, int(fixture_id))
        prices: list[MarketPrice] = []
        if payload:
            lines = normalize_snapshot_odds_lines(payload, fixture_id=int(fixture_id), captured_at=snapshot_at)
            buckets: dict[tuple[str, str], list[tuple[float, str]]] = {}
            raw_names: dict[tuple[str, str], str] = {}
            for line in lines:
                mapped = _classify_and_select(line)
                if not mapped:
                    continue
                fam, selection = mapped
                key = (fam, selection)
                buckets.setdefault(key, []).append((float(line.odd), str(line.bookmaker)))
                raw_names[key] = str(line.market_name)
            for (fam, selection), items in buckets.items():
                med = _median([o for o, _ in items])
                if med is None:
                    continue
                # prefer most common bookmaker label
                bm = items[0][1] if items else None
                prices.append(
                    MarketPrice(
                        market_family=fam,
                        selection=selection,
                        decimal_odds=round(med, 4),
                        bookmaker=bm,
                        odds_lane="REAL",
                        source="odds_snapshots",
                        timestamp=snapshot_at,
                        freshness=str(freshness) if freshness else None,
                        n_bookmakers=len({b for _, b in items}),
                        raw_market_name=raw_names.get((fam, selection)),
                    )
                )
            # Also CS table
            prices.extend(_load_cs_prices(conn, int(fixture_id), freshness=str(freshness) if freshness else None, snapshot_at=snapshot_at))

        if require_fresh:
            prices = [p for p in prices if str(p.freshness or "") in FRESH_OK]

        # Deduplicate exact_score if both snapshot and table
        seen: set[tuple[str, str]] = set()
        deduped: list[MarketPrice] = []
        for p in sorted(prices, key=lambda x: (0 if x.source == "odds_snapshots" else 1, -x.n_bookmakers)):
            key = (p.market_family, p.selection)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)

        cov = {
            "1x2": any(p.market_family == "1x2" for p in deduped),
            "double_chance": any(p.market_family == "double_chance" for p in deduped),
            "btts": any(p.market_family == "btts" for p in deduped),
            "over_under": any(p.market_family == "over_under" for p in deduped),
            "exact_score": any(p.market_family == "exact_score" for p in deduped),
            "ht_ft": any(p.market_family == "ht_ft" for p in deduped),
            "ht_1x2": any(p.market_family == "ht_1x2" for p in deduped),
        }
        return MultiMarketBundle(
            fixture_id=int(fixture_id),
            snapshot_at=snapshot_at,
            freshness_class=str(freshness) if freshness else None,
            prices=deduped,
            coverage=cov,
        )
    finally:
        conn.close()
