"""Optional goalscorer odds alignment from cache (research only)."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
)

_GOALSCORER_MARKET = re.compile(r"goal\s*scor", re.I)
_ANYTIME = re.compile(r"anytime", re.I)
_FIRST = re.compile(r"first", re.I)


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _match_player(name: str, candidates: dict[int, str], threshold: float = 0.82) -> int | None:
    nn = _norm_name(name)
    best_pid: int | None = None
    best_score = 0.0
    for pid, pname in candidates.items():
        score = SequenceMatcher(None, nn, _norm_name(pname or "")).ratio()
        if score > best_score:
            best_score = score
            best_pid = pid
    return best_pid if best_score >= threshold else None


def _load_odds_picks(data: dict[str, Any], label_pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    for o in data.get("odds") or []:
        if not isinstance(o, dict):
            continue
        market = str((o.get("market") or {}).get("name") or "")
        if not _GOALSCORER_MARKET.search(market):
            continue
        label = str(o.get("label") or "")
        if not label_pattern.search(label):
            continue
        name = str(o.get("name") or label)
        try:
            odds = float(o.get("value") or 0)
        except (TypeError, ValueError):
            odds = 0.0
        if odds <= 1.0:
            continue
        picks.append({"player_name": name, "odds": odds, "implied": round(1.0 / odds, 4)})
    picks.sort(key=lambda x: x["implied"], reverse=True)
    return picks


def align_odds_with_model(
    df: pd.DataFrame,
    *,
    score_col: str = "combined_score",
    max_fixtures: int = 120,
) -> dict[str, Any]:
    """Compare model top picks vs bookmaker anytime/first picks where cache odds exist."""
    if df.empty:
        return {"status": "no_data"}

    fixture_ids = list(df["sportmonks_fixture_id"].unique())[:max_fixtures]
    overlap_fixtures = 0
    anytime_overlap = 0
    first_overlap = 0
    mapping_failures = 0
    mapping_attempts = 0
    disagreements: list[dict[str, Any]] = []

    seen_paths: set[Path] = set()
    cache_by_fid: dict[int, dict[str, Any]] = {}
    for root in _CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in root.glob("*.json"):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                sm_id = int(path.stem)
            except ValueError:
                continue
            if sm_id not in fixture_ids:
                continue
            blob = json.loads(path.read_text(encoding="utf-8"))
            data = (blob.get("payload") or {}).get("data")
            if isinstance(data, dict) and data.get("odds"):
                cache_by_fid[sm_id] = data

    for fid in fixture_ids:
        data = cache_by_fid.get(int(fid))
        if not data:
            continue
        grp = df[df["sportmonks_fixture_id"] == fid]
        if grp.empty:
            continue
        candidates = {int(r["player_id"]): str(r.get("player_name") or "") for _, r in grp.iterrows()}
        anytime_odds = _load_odds_picks(data, _ANYTIME)
        first_odds = _load_odds_picks(data, _FIRST)
        if not anytime_odds and not first_odds:
            continue
        overlap_fixtures += 1

        model_top = grp.sort_values(score_col, ascending=False).head(3)
        model_ids = [int(x) for x in model_top["player_id"].tolist()]

        for picks, key in ((anytime_odds, "anytime"), (first_odds, "first")):
            if not picks:
                continue
            book_top = picks[0]
            mapping_attempts += 1
            pid = _match_player(book_top["player_name"], candidates)
            if pid is None:
                mapping_failures += 1
                continue
            if key == "anytime":
                anytime_overlap += 1 if pid in model_ids else 0
            else:
                first_overlap += 1 if pid == model_ids[0] else 0
            if pid != model_ids[0]:
                disagreements.append({
                    "fixture_id": int(fid),
                    "market": key,
                    "book_pick": book_top["player_name"],
                    "model_top": str(model_top.iloc[0].get("player_name") or ""),
                })

    mapping_rate = round(1.0 - mapping_failures / mapping_attempts, 4) if mapping_attempts else 0.0
    return {
        "status": "ok" if overlap_fixtures else "sparse_odds",
        "fixtures_with_odds": overlap_fixtures,
        "anytime_top1_overlap_rate": round(anytime_overlap / overlap_fixtures, 4) if overlap_fixtures else None,
        "first_top1_overlap_rate": round(first_overlap / overlap_fixtures, 4) if overlap_fixtures else None,
        "player_mapping_success_rate": mapping_rate,
        "mapping_blocker": mapping_rate < 0.5 and mapping_attempts >= 10,
        "disagreement_samples": disagreements[:15],
    }
