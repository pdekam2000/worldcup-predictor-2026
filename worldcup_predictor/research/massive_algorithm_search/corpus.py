"""Largest legitimate prematch research corpus (read-only)."""
from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.prediction_engine_75 import phase1 as p1
from worldcup_predictor.research.prediction_engine_75 import phase2 as p2

ROOT = Path(__file__).resolve().parents[3]

COHORT_TF = "TRUE_FORWARD"
COHORT_IMMUTABLE = "HISTORICAL_IMMUTABLE_PREMATCH_FREEZE"
COHORT_PROVIDER = "HISTORICAL_PROVIDER_PREMATCH"
COHORT_RECOVERED = "HISTORICAL_RESULT_RECOVERED"
COHORT_REPLAY = "HISTORICAL_REPLAY"


@dataclass
class MassiveRow:
    fixture_id: int
    kickoff_utc: str | None
    predicted_at: str | None
    odds_snapshot_at: str | None
    cohort: str
    source: str
    league: str | None
    match: str | None
    wde_decision: str | None
    home_p: float | None
    draw_p: float | None
    away_p: float | None
    confidence: float | None
    no_bet: bool | None
    ecse_direction: str | None
    top5_mass: float | None
    top10_mass: float | None
    entropy: float | None
    lambda_home: float | None
    lambda_away: float | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    implied_home: float | None = None
    implied_draw: float | None = None
    implied_away: float | None = None
    book_margin: float | None = None
    favorite_strength: float | None = None
    balanced_market: bool | None = None
    fav_odds: float | None = None
    market_favorite: str | None = None
    actual_1x2: str | None = None
    final_score: str | None = None
    exclusion_reason: str | None = None
    has_wde: bool = False
    has_ecse: bool = False
    has_odds: bool = False
    feature_flags: dict[str, bool] = field(default_factory=dict)

    def edge(self) -> float | None:
        probs = [p for p in (self.home_p, self.draw_p, self.away_p) if p is not None]
        return max(probs) if probs else None

    def lambda_total(self) -> float | None:
        if self.lambda_home is None and self.lambda_away is None:
            return None
        return float(self.lambda_home or 0) + float(self.lambda_away or 0)


def _enrich_market(r: MassiveRow) -> None:
    if not (r.odds_home and r.odds_draw and r.odds_away):
        return
    ih, id_, ia = 1 / r.odds_home, 1 / r.odds_draw, 1 / r.odds_away
    s = ih + id_ + ia
    r.implied_home, r.implied_draw, r.implied_away = ih / s, id_ / s, ia / s
    r.book_margin = round(s - 1.0, 4)
    r.fav_odds = min(r.odds_home, r.odds_draw, r.odds_away)
    r.favorite_strength = round(1.0 / r.fav_odds, 4)
    imps = sorted([r.implied_home, r.implied_draw, r.implied_away], reverse=True)
    r.balanced_market = (imps[0] - imps[1]) <= 0.08
    r.market_favorite = min(
        [("home", r.odds_home), ("draw", r.odds_draw), ("away", r.odds_away)],
        key=lambda x: x[1],
    )[0]
    r.has_odds = True


def _from_phase2(r: p2.RowV2) -> MassiveRow:
    cohort = COHORT_IMMUTABLE if r.cohort in {p2.COHORT_PREMATCH, "HISTORICAL_PREMATCH_FREEZE"} else (
        COHORT_REPLAY if r.cohort == p2.COHORT_REPLAY else str(r.cohort)
    )
    if r.cohort == p2.COHORT_TF:
        cohort = COHORT_TF
    m = MassiveRow(
        fixture_id=r.fixture_id,
        kickoff_utc=r.kickoff_utc,
        predicted_at=r.predicted_at or r.frozen_at,
        odds_snapshot_at=r.odds_snapshot_at,
        cohort=cohort,
        source=r.source,
        league=r.league,
        match=r.match,
        wde_decision=r.wde_decision,
        home_p=r.home_p,
        draw_p=r.draw_p,
        away_p=r.away_p,
        confidence=r.confidence,
        no_bet=r.no_bet,
        ecse_direction=r.ecse_direction or r.ft_marginal,
        top5_mass=r.top5_mass,
        top10_mass=r.top10_mass,
        entropy=r.entropy,
        lambda_home=r.lambda_home,
        lambda_away=r.lambda_away,
        odds_home=r.odds_home,
        odds_draw=r.odds_draw,
        odds_away=r.odds_away,
        actual_1x2=r.actual_1x2,
        final_score=r.final_score,
        exclusion_reason=r.exclusion_reason,
        has_wde=bool(r.wde_decision),
        has_ecse=bool(r.ecse_direction or r.ft_marginal or r.top5_mass is not None),
        feature_flags=dict(r.feature_flags or {}),
    )
    _enrich_market(m)
    return m


def _attach_ecse_only_rows(by_fid: dict[int, MassiveRow], exclusions: list[dict]) -> None:
    """Add ECSE-frozen + result fixtures not already present (provider/freeze cohort)."""
    db = ROOT / "data" / "football_intelligence.db"
    if not db.exists():
        return
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT e.fixture_id, e.kickoff_utc, e.generated_at, e.lambda_home, e.lambda_away,
                   e.top_10_scorelines_json, e.top_5_scores_json, e.model_version, e.home_team, e.away_team,
                   fr.home_goals, fr.away_goals, fr.final_score, fr.regulation_home_goals, fr.regulation_away_goals,
                   fx.competition_key
            FROM ecse_prediction_snapshots e
            JOIN fixture_results fr ON fr.fixture_id = e.fixture_id
            LEFT JOIN fixtures fx ON fx.fixture_id = e.fixture_id
            WHERE COALESCE(e.is_frozen,0)=1 AND fr.home_goals IS NOT NULL
            """
        ).fetchall()
        # odds map for these fids
        fids = {int(r["fixture_id"]) for r in rows}
        odds_map = p2._attach_odds_map(conn, fids) if fids else {}
        for r in rows:
            fid = int(r["fixture_id"])
            if fid in by_fid:
                continue
            ko = str(r["kickoff_utc"] or "") or None
            gen = str(r["generated_at"] or "") or None
            reason = None
            ko_dt, g_dt = p1._parse_dt(ko), p1._parse_dt(gen)
            if ko_dt and g_dt and g_dt >= ko_dt:
                reason = "POST_KICKOFF_PREDICTION"
                exclusions.append({"fixture_id": fid, "reason": reason, "source": "ecse_only"})
            if r["regulation_home_goals"] is not None and r["regulation_away_goals"] is not None:
                hg, ag = int(r["regulation_home_goals"]), int(r["regulation_away_goals"])
            else:
                hg, ag = int(r["home_goals"]), int(r["away_goals"])
            actual = "home" if hg > ag else "away" if ag > hg else "draw"
            h, d, a, t3, t5, direction = p2.scoreline_masses(r["top_10_scorelines_json"] or r["top_5_scores_json"])
            m = MassiveRow(
                fixture_id=fid,
                kickoff_utc=ko,
                predicted_at=gen,
                odds_snapshot_at=None,
                cohort=COHORT_PROVIDER if reason is None else COHORT_PROVIDER,
                source="ecse_prediction_snapshots+fixture_results",
                league=str(r["competition_key"] or "") or None,
                match=f"{r['home_team']} vs {r['away_team']}" if r["home_team"] else None,
                wde_decision=None,
                home_p=h,
                draw_p=d,
                away_p=a,
                confidence=None,
                no_bet=None,
                ecse_direction=direction,
                top5_mass=t5,
                top10_mass=None,
                entropy=(-sum(x * math.log(x) for x in (h, d, a) if x and x > 0)) if h is not None else None,
                lambda_home=r["lambda_home"],
                lambda_away=r["lambda_away"],
                odds_home=None,
                odds_draw=None,
                odds_away=None,
                actual_1x2=actual,
                final_score=str(r["final_score"] or f"{hg}-{ag}"),
                exclusion_reason=reason,
                has_wde=False,
                has_ecse=True,
                feature_flags={"ecse_only": True},
            )
            if fid in odds_map:
                o = odds_map[fid]
                od_dt = p1._parse_dt(o.get("snapshot_at"))
                if ko_dt and od_dt and od_dt >= ko_dt:
                    exclusions.append({"fixture_id": fid, "reason": "POST_KICKOFF_ODDS_SKIPPED", "source": "ecse_only"})
                else:
                    m.odds_home, m.odds_draw, m.odds_away = o["home"], o["draw"], o["away"]
                    m.odds_snapshot_at = o.get("snapshot_at")
                    _enrich_market(m)
            if reason is None and m.actual_1x2 and m.ecse_direction:
                by_fid[fid] = m
    finally:
        conn.close()


def build_massive_corpus() -> tuple[list[MassiveRow], list[dict[str, Any]], dict[str, Any]]:
    exclusions: list[dict[str, Any]] = []
    p2_rows, p2_ex, p2_inv = p2.build_expanded_corpus()
    exclusions.extend(p2_ex)
    by_fid: dict[int, MassiveRow] = {}
    for r in p2_rows:
        by_fid[r.fixture_id] = _from_phase2(r)

    before = len(by_fid)
    _attach_ecse_only_rows(by_fid, exclusions)
    ecse_added = len(by_fid) - before

    rows = sorted(by_fid.values(), key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    usable = [r for r in rows if r.exclusion_reason is None and r.actual_1x2 and (r.has_wde or r.has_ecse)]
    priced = [r for r in usable if r.has_odds]
    wde_usable = [r for r in usable if r.has_wde]
    kos = [r.kickoff_utc for r in usable if r.kickoff_utc]
    leagues = sorted({r.league or "?" for r in usable})
    audit = {
        "phase2_inventory": p2_inv,
        "n_raw": len(rows),
        "n_usable_prematch_labeled": len(usable),
        "n_priced": len(priced),
        "n_with_wde": len(wde_usable),
        "n_ecse_only_added": ecse_added,
        "n_true_forward": sum(1 for r in usable if r.cohort == COHORT_TF),
        "cohort_counts": dict(Counter(r.cohort for r in usable)),
        "exclusion_counts": dict(Counter(r.exclusion_reason or "OK" for r in rows)),
        "date_range": {"min": min(kos) if kos else None, "max": max(kos) if kos else None},
        "leagues_n": len(leagues),
        "leagues_sample": leagues[:40],
        "sources": list(Counter(r.source for r in usable).keys()),
    }
    return rows, exclusions, audit


def usable_rows(rows: list[MassiveRow]) -> list[MassiveRow]:
    return [r for r in rows if r.exclusion_reason is None and r.actual_1x2 and (r.has_wde or r.has_ecse)]


def chrono_split(rows: list[MassiveRow], *, train=0.6, val=0.2) -> dict[str, list[MassiveRow]]:
    data = sorted(usable_rows(rows), key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    n = len(data)
    i1 = int(n * train)
    i2 = int(n * (train + val))
    return {"train": data[:i1], "validation": data[i1:i2], "holdout_sealed": data[i2:]}
