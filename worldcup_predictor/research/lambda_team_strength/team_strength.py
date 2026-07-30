"""Leakage-safe team attack/defense strength from historical results."""

from __future__ import annotations

import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from worldcup_predictor.research.lambda_team_strength.metrics import (
    half_life_weight,
    normalize_team,
    shrink_to_prior,
    team_match_keys,
)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip().replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(t[:19] if len(t) >= 19 else t[:10], fmt if len(t) >= 16 else "%Y-%m-%d")
        except Exception:
            continue
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


@dataclass
class MatchRecord:
    kickoff: datetime
    home_norm: str
    away_norm: str
    home_goals: int
    away_goals: int
    league: str
    season: str
    registry_id: int | None = None


@dataclass
class TeamStrengthStore:
    matches: list[MatchRecord] = field(default_factory=list)
    by_team: dict[str, list[MatchRecord]] = field(default_factory=lambda: defaultdict(list))
    league_avg_home: dict[str, float] = field(default_factory=dict)
    league_avg_away: dict[str, float] = field(default_factory=dict)
    global_avg_home: float = 1.35
    global_avg_away: float = 1.15

    def build_indexes(self) -> None:
        self.matches.sort(key=lambda m: m.kickoff)
        self.by_team.clear()
        league_h: dict[str, list[float]] = defaultdict(list)
        league_a: dict[str, list[float]] = defaultdict(list)
        gh: list[float] = []
        ga: list[float] = []
        for m in self.matches:
            self.by_team[m.home_norm].append(m)
            self.by_team[m.away_norm].append(m)
            league_h[m.league].append(m.home_goals)
            league_a[m.league].append(m.away_goals)
            gh.append(m.home_goals)
            ga.append(m.away_goals)
        self.league_avg_home = {k: sum(v) / len(v) for k, v in league_h.items() if v}
        self.league_avg_away = {k: sum(v) / len(v) for k, v in league_a.items() if v}
        if gh:
            self.global_avg_home = sum(gh) / len(gh)
        if ga:
            self.global_avg_away = sum(ga) / len(ga)

    def prior_home(self, league: str) -> float:
        return self.league_avg_home.get(league, self.global_avg_home)

    def prior_away(self, league: str) -> float:
        return self.league_avg_away.get(league, self.global_avg_away)


def load_strength_store(fi_path: str, *, max_rows: int | None = None) -> TeamStrengthStore:
    """Load finished matches from external staging (primary) + registry (supplement)."""
    store = TeamStrengthStore()
    con = sqlite3.connect(f"file:{fi_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    # Primary: long-horizon external match history
    sql_ext = """
        SELECT kickoff_utc, event_date, league, home_team, away_team,
               home_ft_goals, away_ft_goals, status
        FROM external_match_history_staging
        WHERE home_ft_goals IS NOT NULL AND away_ft_goals IS NOT NULL
          AND home_team IS NOT NULL AND away_team IS NOT NULL
    """
    if max_rows:
        sql_ext += f" LIMIT {int(max_rows)}"
    for row in con.execute(sql_ext):
        ko = _parse_dt(row["kickoff_utc"]) or _parse_dt(row["event_date"])
        if ko is None:
            continue
        # skip obvious future-dated unfinished rows if status says so
        st = str(row["status"] or "").lower()
        if st and st not in {"ft", "finished", "match finished", "aet", "pen", "after pen", ""}:
            if "sched" in st or "not started" in st or st in {"ns", "tbd"}:
                continue
        hn = normalize_team(row["home_team"] or "")
        an = normalize_team(row["away_team"] or "")
        if not hn or not an:
            continue
        store.matches.append(
            MatchRecord(
                kickoff=ko,
                home_norm=hn,
                away_norm=an,
                home_goals=int(row["home_ft_goals"]),
                away_goals=int(row["away_ft_goals"]),
                league=normalize_team(str(row["league"] or "unknown")).replace(" ", ""),
                season=str(ko.year),
                registry_id=None,
            )
        )

    # Supplement: historical registry (may use different normalizations)
    sql = """
        SELECT registry_fixture_id, kickoff_utc, match_date, league_normalized, season,
               home_team_normalized, away_team_normalized, home_team, away_team,
               home_goals, away_goals, match_status
        FROM historical_fixture_registry
        WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
    """
    if max_rows:
        sql += f" LIMIT {int(max_rows)}"
    for row in con.execute(sql):
        ko = _parse_dt(row["kickoff_utc"]) or _parse_dt(row["match_date"])
        if ko is None:
            continue
        # Prefer display names when present (better accent handling)
        hn = normalize_team(row["home_team"] or row["home_team_normalized"] or "")
        an = normalize_team(row["away_team"] or row["away_team_normalized"] or "")
        if not hn or not an:
            continue
        store.matches.append(
            MatchRecord(
                kickoff=ko,
                home_norm=hn,
                away_norm=an,
                home_goals=int(row["home_goals"]),
                away_goals=int(row["away_goals"]),
                league=str(row["league_normalized"] or "unknown"),
                season=str(row["season"] or ""),
                registry_id=int(row["registry_fixture_id"]),
            )
        )
    con.close()
    store.build_indexes()
    # alias compact keys
    extra: dict[str, list] = {}
    for key, ms in list(store.by_team.items()):
        compact = key.replace(" ", "")
        if compact != key:
            extra.setdefault(compact, [])
            seen = {id(m) for m in extra[compact]}
            for m in ms:
                if id(m) not in seen:
                    extra[compact].append(m)
                    seen.add(id(m))
    for k, v in extra.items():
        if k not in store.by_team:
            store.by_team[k] = v
        else:
            seen = {id(m) for m in store.by_team[k]}
            for m in v:
                if id(m) not in seen:
                    store.by_team[k].append(m)
    return store


def resolve_team_key(store: TeamStrengthStore, name: str) -> str:
    for k in team_match_keys(name):
        if k in store.by_team and store.by_team[k]:
            return k
    keys = team_match_keys(name)
    return keys[0] if keys else normalize_team(name)


def _team_matches_before(
    store: TeamStrengthStore, team: str, before: datetime
) -> list[MatchRecord]:
    out = []
    for m in store.by_team.get(team, []):
        if m.kickoff < before:
            out.append(m)
        # matches sorted globally but per-team lists are insertion-order from sorted global
    return out


@dataclass
class StrengthSnapshot:
    attack_home: float
    attack_away: float
    defense_home: float  # goals conceded when home
    defense_away: float
    attack_overall: float
    defense_overall: float
    n_home: int
    n_away: int
    n_total: int
    scoring_var: float
    conceding_var: float
    freq_concede_3plus: float
    freq_score_3plus: float
    freq_btts: float
    freq_over25: float
    low_data: bool
    promoted_like: bool  # few matches this season relative to history
    fallback_level: str  # team | league | global


def team_snapshot(
    store: TeamStrengthStore,
    team: str,
    before: datetime,
    league: str,
    *,
    half_life_days: float = 90.0,
    lookback: int = 40,
    prior_strength: float = 8.0,
) -> StrengthSnapshot:
    hist = _team_matches_before(store, team, before)
    hist = hist[-lookback:] if lookback else hist
    ph = store.prior_home(league)
    pa = store.prior_away(league)
    if not hist:
        return StrengthSnapshot(
            attack_home=ph,
            attack_away=pa,
            defense_home=pa,
            defense_away=ph,
            attack_overall=(ph + pa) / 2,
            defense_overall=(ph + pa) / 2,
            n_home=0,
            n_away=0,
            n_total=0,
            scoring_var=0.0,
            conceding_var=0.0,
            freq_concede_3plus=0.0,
            freq_score_3plus=0.0,
            freq_btts=0.0,
            freq_over25=0.0,
            low_data=True,
            promoted_like=True,
            fallback_level="league" if league in store.league_avg_home else "global",
        )

    # Weighted scored / conceded
    wh_sc: list[tuple[float, float]] = []
    wa_sc: list[tuple[float, float]] = []
    wh_conc: list[tuple[float, float]] = []
    wa_conc: list[tuple[float, float]] = []
    scored: list[float] = []
    conceded: list[float] = []
    c3 = s3 = btts = o25 = 0
    n_h = n_a = 0
    for m in hist:
        days = (before - m.kickoff).total_seconds() / 86400.0
        w = half_life_weight(days, half_life_days)
        if m.home_norm == team:
            n_h += 1
            wh_sc.append((m.home_goals, w))
            wh_conc.append((m.away_goals, w))
            scored.append(m.home_goals)
            conceded.append(m.away_goals)
            if m.away_goals >= 3:
                c3 += 1
            if m.home_goals >= 3:
                s3 += 1
            if m.home_goals > 0 and m.away_goals > 0:
                btts += 1
            if m.home_goals + m.away_goals > 2.5:
                o25 += 1
        else:
            n_a += 1
            wa_sc.append((m.away_goals, w))
            wa_conc.append((m.home_goals, w))
            scored.append(m.away_goals)
            conceded.append(m.home_goals)
            if m.home_goals >= 3:
                c3 += 1
            if m.away_goals >= 3:
                s3 += 1
            if m.home_goals > 0 and m.away_goals > 0:
                btts += 1
            if m.home_goals + m.away_goals > 2.5:
                o25 += 1

    def wavg(pairs: list[tuple[float, float]], prior: float, n: int) -> float:
        if not pairs:
            return prior
        sw = sum(w for _, w in pairs)
        if sw <= 0:
            return prior
        est = sum(v * w for v, w in pairs) / sw
        return shrink_to_prior(est, prior, n, prior_strength)

    att_h = wavg(wh_sc, ph, n_h)
    att_a = wavg(wa_sc, pa, n_a)
    def_h = wavg(wh_conc, pa, n_h)
    def_a = wavg(wa_conc, ph, n_a)
    att_o = shrink_to_prior(
        (sum(scored) / len(scored)) if scored else (ph + pa) / 2,
        (ph + pa) / 2,
        len(scored),
        prior_strength,
    )
    def_o = shrink_to_prior(
        (sum(conceded) / len(conceded)) if conceded else (ph + pa) / 2,
        (ph + pa) / 2,
        len(conceded),
        prior_strength,
    )

    def _var(xs: list[float]) -> float:
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)

    n = len(hist)
    return StrengthSnapshot(
        attack_home=att_h,
        attack_away=att_a,
        defense_home=def_h,
        defense_away=def_a,
        attack_overall=att_o,
        defense_overall=def_o,
        n_home=n_h,
        n_away=n_a,
        n_total=n,
        scoring_var=_var(scored),
        conceding_var=_var(conceded),
        freq_concede_3plus=c3 / n,
        freq_score_3plus=s3 / n,
        freq_btts=btts / n,
        freq_over25=o25 / n,
        low_data=n < 8,
        promoted_like=n < 12,
        fallback_level="team",
    )


def predict_lambdas_from_strength(
    home: StrengthSnapshot,
    away: StrengthSnapshot,
    league: str,
    store: TeamStrengthStore,
    *,
    mode: str = "home_away",
) -> tuple[float, float, dict[str, Any]]:
    """modes: league | overall | home_away | opponent_adj | volatility | collapse | surge | blend_market"""
    ph = store.prior_home(league)
    pa = store.prior_away(league)
    meta: dict[str, Any] = {"mode": mode, "prior_home": ph, "prior_away": pa}

    if mode == "league":
        lh, la = ph, pa
    elif mode == "overall":
        # home attack vs away defense / league
        lh = home.attack_overall * (away.defense_overall / ((ph + pa) / 2))
        la = away.attack_overall * (home.defense_overall / ((ph + pa) / 2))
    elif mode == "home_away":
        lh = 0.5 * (home.attack_home + away.defense_away)
        la = 0.5 * (away.attack_away + home.defense_home)
    elif mode == "opponent_adj":
        # geometric mean of attack and opponent defense relative to prior
        lh = math.sqrt(max(home.attack_home, 1e-6) * max(away.defense_away, 1e-6))
        la = math.sqrt(max(away.attack_away, 1e-6) * max(home.defense_home, 1e-6))
    elif mode == "volatility":
        base_h = 0.5 * (home.attack_home + away.defense_away)
        base_a = 0.5 * (away.attack_away + home.defense_home)
        vol = 0.5 * (home.scoring_var + away.scoring_var + home.conceding_var + away.conceding_var)
        # mild expansion of mean toward higher totals when volatile
        bump = min(0.35, 0.08 * math.sqrt(max(vol, 0.0)))
        lh, la = base_h + bump * 0.55, base_a + bump * 0.45
        meta["vol_bump"] = bump
    elif mode == "collapse":
        base_h = 0.5 * (home.attack_home + away.defense_away)
        base_a = 0.5 * (away.attack_away + home.defense_home)
        # if away concedes a lot recently, boost home lambda
        lh = base_h * (1.0 + 0.4 * away.freq_concede_3plus)
        la = base_a * (1.0 + 0.4 * home.freq_concede_3plus)
        meta["away_concede_3plus"] = away.freq_concede_3plus
        meta["home_concede_3plus"] = home.freq_concede_3plus
    elif mode == "surge":
        base_h = 0.5 * (home.attack_home + away.defense_away)
        base_a = 0.5 * (away.attack_away + home.defense_home)
        lh = base_h * (1.0 + 0.35 * home.freq_score_3plus)
        la = base_a * (1.0 + 0.35 * away.freq_score_3plus)
    else:
        lh = 0.5 * (home.attack_home + away.defense_away)
        la = 0.5 * (away.attack_away + home.defense_home)

    # Wider uncertainty / less aggressive shrink already in snapshot; clamp softly
    lh = max(0.2, min(5.5, lh))
    la = max(0.2, min(5.5, la))
    meta["home_n"] = home.n_total
    meta["away_n"] = away.n_total
    meta["home_low_data"] = home.low_data
    meta["away_low_data"] = away.low_data
    return lh, la, meta


_RESERVE_RE = re.compile(
    r"\b(ii|iii|2|b|u19|u20|u21|u23|youth|reserves?|women|wfc|ladies)\b",
    re.I,
)


def team_flags(name: str) -> dict[str, bool]:
    n = normalize_team(name)
    return {
        "reserve_or_youth": bool(_RESERVE_RE.search(n)),
        "women": bool(re.search(r"\b(women|wfc|ladies)\b", n)),
    }
