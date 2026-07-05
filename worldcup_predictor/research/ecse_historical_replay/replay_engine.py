"""Production-path ECSE replay for historical fixtures."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from typing import Any, Iterator

from worldcup_predictor.research.ecse_historical_replay.constants import REPLAY_START_DATE
from worldcup_predictor.research.ecse_historical_replay.inventory import _competition_label, _parse_date
from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas, METHOD_VERSION as LAMBDA_VERSION
from worldcup_predictor.research.ecse_market_prior.dataset import external_row_to_ecse_odds_features
from worldcup_predictor.research.ecse_score_distribution import (
    METHOD_VERSION as DIST_VERSION,
    OTHER_SCORELINE,
    generate_score_distribution,
)


@dataclass
class ReplayRow:
    fixture_key: str
    match: str
    kickoff: str
    event_date: str
    year: str
    competition: str
    league: str
    season: str
    stage: str
    lambda_home: float
    lambda_away: float
    lambda_total: float
    data_quality_score: float
    model_version: str
    actual_score: str
    actual_home: int
    actual_away: int
    top10: list[dict[str, Any]]
    top5: list[str]
    top1: str
    actual_rank: int
    hit_rank: int | None
    top5_hit: bool
    top10_hit: bool
    prob_actual: float
    entropy: float
    top1_prob: float
    top3_mass: float
    top5_mass: float
    odds_home: float
    odds_draw: float
    odds_away: float
    leakage_pass: bool


def _entropy(probs: list[float]) -> float:
    s = 0.0
    for p in probs:
        if p > 0:
            s -= p * math.log(p)
    return round(s, 6)


def _distribution_entropy(dist: list[dict]) -> float:
    return _entropy([float(d["probability"]) for d in dist[:65]])


def replay_fixture(row_hash: str, source_file: str, raw: dict[str, Any]) -> ReplayRow | None:
    d = _parse_date(raw)
    if not d or d < REPLAY_START_DATE:
        return None
    try:
        hg = int(float(raw.get("goalsHomeFullTime")))
        ag = int(float(raw.get("goalsAwayFullTime")))
        oh = float(raw.get("oddsFT_1"))
        od = float(raw.get("oddsFT_X"))
        oa = float(raw.get("oddsFT_2"))
    except (TypeError, ValueError):
        return None
    if oh <= 1 or od <= 1 or oa <= 1 or hg < 0 or ag < 0:
        return None

    features = external_row_to_ecse_odds_features(raw)
    features["registry_fixture_id"] = 0
    lam = extract_lambdas(features)
    if not lam:
        return None
    lh = float(lam["lambda_home"])
    la = float(lam["lambda_away"])
    if lh <= 0 or la <= 0:
        return None

    dist = generate_score_distribution(lh, la)
    if not dist:
        return None

    total = sum(float(x["probability"]) for x in dist)
    if abs(total - 1.0) > 1e-4:
        return None

    top10 = [
        {
            "rank": int(e["rank"]),
            "scoreline": str(e["scoreline"]),
            "probability": round(float(e["probability"]), 6),
            "home_goals": int(e["home_goals"]),
            "away_goals": int(e["away_goals"]),
        }
        for e in dist[:10]
    ]
    top5 = [x["scoreline"] for x in top10[:5]]
    top1 = top10[0]["scoreline"]
    actual = f"{hg}-{ag}"

    rank_map = {x["scoreline"]: x["rank"] for x in top10}
    if actual in rank_map:
        actual_rank = rank_map[actual]
    else:
        full_map = {str(e["scoreline"]): int(e["rank"]) for e in dist}
        actual_rank = full_map.get(actual, 999)

    prob_map = {str(e["scoreline"]): float(e["probability"]) for e in dist}
    prob_actual = prob_map.get(actual, 0.0)

    home = str(raw.get("homeTeam") or "Home")
    away = str(raw.get("awayTeam") or "Away")
    comp = _competition_label(str(raw.get("league") or ""), source_file)
    event_hour = str(raw.get("eventHour") or "").strip()
    kickoff = f"{d}T{event_hour}" if event_hour else d

    return ReplayRow(
        fixture_key=row_hash,
        match=f"{home} vs {away}",
        kickoff=kickoff,
        event_date=d,
        year=d[:4],
        competition=comp,
        league=str(raw.get("league") or ""),
        season=str(raw.get("season") or d[:4]),
        stage=str(raw.get("round") or "league"),
        lambda_home=round(lh, 6),
        lambda_away=round(la, 6),
        lambda_total=round(lh + la, 6),
        data_quality_score=float(lam.get("data_quality_score") or 0),
        model_version=f"ECSE-REPLAY|{LAMBDA_VERSION}|{DIST_VERSION}",
        actual_score=actual,
        actual_home=hg,
        actual_away=ag,
        top10=top10,
        top5=top5,
        top1=top1,
        actual_rank=actual_rank,
        hit_rank=actual_rank if actual_rank <= 10 else None,
        top5_hit=actual_rank <= 5,
        top10_hit=actual_rank <= 10,
        prob_actual=round(prob_actual, 6),
        entropy=_distribution_entropy(dist),
        top1_prob=top10[0]["probability"],
        top3_mass=round(sum(x["probability"] for x in top10[:3]), 6),
        top5_mass=round(sum(x["probability"] for x in top10[:5]), 6),
        odds_home=oh,
        odds_draw=od,
        odds_away=oa,
        leakage_pass=True,
    )


def iter_replay_rows(conn: sqlite3.Connection) -> Iterator[ReplayRow]:
    seen: set[str] = set()
    conn.row_factory = sqlite3.Row
    for rec in conn.execute("SELECT row_hash, source_file, raw_row_json FROM external_historical_csv_raw_rows"):
        rh = str(rec["row_hash"])
        if rh in seen:
            continue
        seen.add(rh)
        try:
            raw = json.loads(rec["raw_row_json"])
        except json.JSONDecodeError:
            continue
        row = replay_fixture(rh, str(rec["source_file"]), raw)
        if row:
            yield row


def load_frozen_predictions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ecse_prediction_snapshots'").fetchone():
        return []
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT ec.fixture_id, ec.top_10_scorelines_json, ec.top_3_scores_json,
               ec.lambda_home, ec.lambda_away, ec.generated_at,
               f.home_team, f.away_team, f.kickoff_utc, f.competition_key, f.round_name,
               fr.home_goals, fr.away_goals
        FROM ecse_prediction_snapshots ec
        INNER JOIN fixtures f ON f.fixture_id = ec.fixture_id
        INNER JOIN fixture_results fr ON fr.fixture_id = ec.fixture_id
        WHERE f.kickoff_utc >= ?
        ORDER BY ec.id DESC
        """,
        (REPLAY_START_DATE,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for r in rows:
        fid = int(r["fixture_id"])
        if fid in seen:
            continue
        seen.add(fid)
        top10: list[dict] = []
        try:
            data = json.loads(r["top_10_scorelines_json"] or "[]")
            if isinstance(data, list):
                for i, item in enumerate(data[:10], 1):
                    if isinstance(item, dict):
                        top10.append({"rank": i, "scoreline": item.get("scoreline"), "probability": item.get("probability")})
                    else:
                        top10.append({"rank": i, "scoreline": str(item), "probability": None})
        except json.JSONDecodeError:
            pass
        actual = f"{r['home_goals']}-{r['away_goals']}"
        rank = next((x["rank"] for x in top10 if x.get("scoreline") == actual), 999)
        out.append(
            {
                "fixture_id": fid,
                "match": f"{r['home_team']} vs {r['away_team']}",
                "kickoff": r["kickoff_utc"],
                "competition": r["competition_key"],
                "actual_score": actual,
                "top10": top10,
                "top5": [x["scoreline"] for x in top10[:5]],
                "top1": top10[0]["scoreline"] if top10 else None,
                "actual_rank": rank,
                "top5_hit": rank <= 5,
                "dataset": "REAL_FROZEN_PREMATCH_EVALUATION",
            }
        )
    return out
