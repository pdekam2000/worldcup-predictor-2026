"""Shared metrics for lambda / exact-score evaluation."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution


def fnum(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def parse_teams(match_name: str | None) -> tuple[str, str]:
    if not match_name:
        return "", ""
    for sep in (" vs ", " v ", " - "):
        if sep in match_name:
            a, b = match_name.split(sep, 1)
            return a.strip(), b.strip()
    return match_name.strip(), ""


def normalize_team(name: str) -> str:
    s = (name or "").lower().strip()
    # fold common latin accents for matching
    trans = str.maketrans(
        {
            "á": "a",
            "à": "a",
            "ä": "a",
            "å": "a",
            "ã": "a",
            "â": "a",
            "é": "e",
            "è": "e",
            "ê": "e",
            "ë": "e",
            "í": "i",
            "ì": "i",
            "î": "i",
            "ï": "i",
            "ó": "o",
            "ò": "o",
            "ö": "o",
            "ô": "o",
            "õ": "o",
            "ú": "u",
            "ù": "u",
            "ü": "u",
            "û": "u",
            "ý": "y",
            "ñ": "n",
            "ç": "c",
            "ø": "o",
            "æ": "ae",
            "š": "s",
            "ž": "z",
            "č": "c",
            "ć": "c",
            "đ": "d",
            "ő": "o",
            "ű": "u",
        }
    )
    s = s.translate(trans)
    for ch in ("'", ".", "/", "-", "&", "(", ")", ","):
        s = s.replace(ch, " ")
    s = "".join(c for c in s if c.isalnum() or c.isspace())
    tokens = [t for t in s.split() if t]
    # drop common club suffixes / noise tokens (keep if only token)
    drop = {
        "ff",
        "if",
        "fk",
        "fc",
        "cf",
        "afc",
        "sc",
        "sk",
        "bk",
        "ik",
        "ac",
        "as",
        "ssc",
        "sv",
        "vfl",
        "vfb",
        "tsg",
        "rc",
        "cd",
        "ud",
        "sd",
        "ca",
        "club",
        "de",
        "the",
    }
    if len(tokens) > 1:
        tokens = [t for t in tokens if t not in drop]
    return " ".join(tokens)


def team_match_keys(name: str) -> list[str]:
    """Candidate keys for historical lookup (spaced + compact)."""
    n = normalize_team(name)
    if not n:
        return []
    keys = [n, n.replace(" ", "")]
    # also try without leading ifk/hk/ir style prefixes when multi-token
    parts = n.split()
    if len(parts) >= 2 and parts[0] in {"ifk", "hk", "ir", "fc", "cf", "afc", "bk", "ik"}:
        rest = " ".join(parts[1:])
        keys.extend([rest, rest.replace(" ", "")])
    # unique preserve order
    out: list[str] = []
    for k in keys:
        if k and k not in out:
            out.append(k)
    return out


def rank_of_score(dist: list[dict[str, Any]], ah: int, aa: int) -> int | None:
    label = f"{ah}-{aa}"
    for e in dist:
        if e.get("scoreline") == label:
            return int(e["rank"])
    # outside named grid
    return None


def exact_hits(dist: list[dict[str, Any]], ah: int, aa: int) -> dict[str, Any]:
    rank = rank_of_score(dist, ah, aa)
    tops = [e["scoreline"] for e in dist if e.get("scoreline") != "OTHER"]
    label = f"{ah}-{aa}"
    return {
        "rank": rank,
        "top1": bool(tops and tops[0] == label),
        "top5": bool(label in tops[:5]),
        "top10": bool(label in tops[:10]),
        "outside_grid": rank is None,
    }


def mae(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return sum(abs(a - p) for a, p in pairs) / len(pairs)


def mean(xs: list[float]) -> float | None:
    if not xs:
        return None
    return sum(xs) / len(xs)


def evaluate_lambda_pair(
    lh: float,
    la: float,
    ah: int,
    aa: int,
    *,
    use_dixon_coles: bool = False,
    max_goals: int = 7,
) -> dict[str, Any]:
    dist = generate_score_distribution(
        lh, la, max_goals=max_goals, use_dixon_coles=use_dixon_coles
    )
    hits = exact_hits(dist, ah, aa)
    pred_tot = lh + la
    act_tot = ah + aa
    return {
        "lambda_home": lh,
        "lambda_away": la,
        "lambda_total": pred_tot,
        "home_err": ah - lh,
        "away_err": aa - la,
        "total_err": act_tot - pred_tot,
        "abs_total_err": abs(act_tot - pred_tot),
        **hits,
        "top5_list": [e["scoreline"] for e in dist[:5] if e.get("scoreline") != "OTHER"],
        "top10_list": [e["scoreline"] for e in dist[:10] if e.get("scoreline") != "OTHER"],
        "dist": dist,
    }


def cohort_metrics(rows: list[dict[str, Any]], prefix: str = "") -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    def rate(key: str) -> float:
        return sum(1 for r in rows if r.get(key)) / n

    tot_err = [float(r["total_err"]) for r in rows if r.get("total_err") is not None]
    abs_err = [float(r["abs_total_err"]) for r in rows if r.get("abs_total_err") is not None]
    pred = [float(r["lambda_total"]) for r in rows if r.get("lambda_total") is not None]
    act = [float(r["ah"] + r["aa"]) for r in rows]
    out = {
        f"{prefix}n": n,
        f"{prefix}exact_top1": rate("top1"),
        f"{prefix}exact_top5": rate("top5"),
        f"{prefix}exact_top10": rate("top10"),
        f"{prefix}lambda_mae": mae([(a, p) for a, p in zip(act, pred)]) if pred else None,
        f"{prefix}total_goal_mae": mean(abs_err),
        f"{prefix}mean_total_err": mean(tot_err),  # + => underestimation
        f"{prefix}mean_pred_total": mean(pred),
        f"{prefix}mean_act_total": mean(act),
    }
    return out


def clip_lambda(x: float, floor: float = 0.15, ceil: float = 6.0) -> float:
    return min(max(float(x), floor), ceil)


def shrink_to_prior(estimate: float, prior: float, n: int, prior_strength: float = 8.0) -> float:
    """Bayesian-style shrink toward prior with sample size n."""
    w = n / (n + prior_strength)
    return w * estimate + (1.0 - w) * prior


def half_life_weight(days_ago: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    return math.pow(0.5, max(days_ago, 0.0) / half_life_days)
