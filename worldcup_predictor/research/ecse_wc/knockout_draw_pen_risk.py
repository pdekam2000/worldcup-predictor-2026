"""PHASE ECSE-WC-2 — Owner-only knockout draw/PEN risk signal (no public prediction changes)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot, ensure_ecse_live_tables, get_snapshot
from worldcup_predictor.research.ecse_wc.wc_shadow_enhancer_evaluation import _is_knockout_round
from worldcup_predictor.research.ecse_x2_m6.odds import build_probs_for_fixture

PHASE = "ECSE-WC-2"
DEFAULT_COMPETITION_KEY = "world_cup_2026"

RISK_JSONL = Path("artifacts/ecse_wc_knockout_draw_pen_risk.jsonl")
RISK_SUMMARY = Path("artifacts/ecse_wc_knockout_draw_pen_risk_summary.json")

RiskLevel = Literal["HIGH", "MEDIUM", "LOW", "NONE"]

DRAW_PROB_HIGH = 0.26
UNDER_25_HIGH = 0.52
BALANCED_PROB_MAX = 0.55
LAMBDA_TOTAL_LOW = 2.6
HOME_FAVORITE_SUPPRESS_MIN = 0.52


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _score_rank(top10: list[dict[str, Any]], scoreline: str) -> int | None:
    for row in top10:
        if str(row.get("scoreline")) == scoreline:
            return int(row.get("rank"))
    return None


def _top1_scoreline(top10: list[dict[str, Any]], fallback: str | None = None) -> str | None:
    if top10:
        return str(top10[0].get("scoreline") or fallback or "")
    return fallback


def _parse_scoreline(scoreline: str | None) -> tuple[int, int] | None:
    if not scoreline or "-" not in str(scoreline):
        return None
    try:
        h, a = str(scoreline).split("-", 1)
        return int(h.strip()), int(a.strip())
    except (TypeError, ValueError):
        return None


def _normalize_1x2(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).lower().strip().replace(" ", "_")
    mapping = {
        "home": "home_win",
        "away": "away_win",
        "1": "home_win",
        "x": "draw",
        "2": "away_win",
        "draw": "draw",
    }
    return mapping.get(text, text)


def _load_wde_signals(fixture_id: int, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    store = WorldcupPredictionStore(settings)
    payload = store.get(fixture_id, competition_key=DEFAULT_COMPETITION_KEY)
    if not payload:
        return {}
    one_x_two = payload.get("one_x_two") or {}
    over_under = payload.get("over_under") or {}
    pick = _normalize_1x2(
        one_x_two.get("selection") if isinstance(one_x_two, dict) else payload.get("predicted_1x2")
    )
    ou = (
        str(over_under.get("selection") or payload.get("predicted_over_under_2_5") or "")
        .lower()
        .replace(" ", "_")
    )
    btts = (payload.get("extended_markets") or {}).get("btts") or {}
    btts_pick = None
    if btts:
        yes = float(btts.get("yes") or btts.get("option_a") or 0)
        btts_pick = "yes" if yes >= 0.5 else "no"
    explanation = payload.get("explanation")
    reason = ""
    if isinstance(explanation, dict):
        reason = str(explanation.get("en") or explanation.get("de") or "")
    elif explanation:
        reason = str(explanation)
    return {
        "predicted_1x2": pick,
        "predicted_over_under_2_5": ou or None,
        "no_bet_flag": bool(payload.get("no_bet_flag", False)),
        "btts_pick": btts_pick,
        "short_reason": reason.lower(),
    }


def _collect_market_support(
    *,
    wde: dict[str, Any],
    probs: dict[str, float | None],
    home_prob: float | None,
    away_prob: float | None,
    lambda_home: float | None,
    lambda_away: float | None,
    rank_1_1: int | None,
) -> tuple[list[str], int]:
    """Return (signal_names, support_count)."""
    signals: list[str] = []
    draw_prob = probs.get("ft_draw") or probs.get("draw_proxy")
    under_25 = probs.get("ou_under_25")
    btts_yes = probs.get("btts_yes")

    if wde.get("predicted_1x2") == "draw":
        signals.append("wde_pick_draw")
    if wde.get("no_bet_flag"):
        reason = wde.get("short_reason") or ""
        ou = str(wde.get("predicted_over_under_2_5") or "").lower()
        if "draw" in reason or ou.startswith("under"):
            signals.append("wde_no_bet_draw_under_lean")
    if draw_prob is not None and float(draw_prob) >= DRAW_PROB_HIGH:
        signals.append("draw_probability_high")
    if under_25 is not None and float(under_25) >= UNDER_25_HIGH:
        signals.append("under_25_probability_high")
    if (
        btts_yes is not None
        and under_25 is not None
        and float(btts_yes) >= 0.50
        and float(under_25) >= 0.50
    ):
        signals.append("btts_yes_under_25_conflict")
    if (
        home_prob is not None
        and away_prob is not None
        and float(home_prob) < BALANCED_PROB_MAX
        and float(away_prob) < BALANCED_PROB_MAX
    ):
        signals.append("balanced_ish_probs")
    if lambda_home is not None and lambda_away is not None:
        if float(lambda_home) + float(lambda_away) < LAMBDA_TOTAL_LOW:
            signals.append("lambda_low_scoring")
    if rank_1_1 is not None and rank_1_1 <= 5:
        if draw_prob is not None and float(draw_prob) >= 0.22:
            signals.append("ecse_1_1_top5_with_draw_odds")
    return signals, len(signals)


def _should_suppress_home_favorite(
    *,
    top10: list[dict[str, Any]],
    top1: str | None,
    home_prob: float | None,
    wde: dict[str, Any],
    draw_prob: float | None,
    rank_1_1: int | None,
    support_signals: list[str],
) -> bool:
    """Avoid false draw/PEN risk on clear home-favorite knockout profiles (e.g. Brazil vs Japan)."""
    weak_only = {"lambda_low_scoring", "ecse_1_1_top5_with_draw_odds"}
    strong_supports = [s for s in support_signals if s not in weak_only]
    if strong_supports:
        return False
    if home_prob is None or float(home_prob) < HOME_FAVORITE_SUPPRESS_MIN:
        return False
    if wde.get("predicted_1x2") not in (None, "home_win"):
        return False
    parsed = _parse_scoreline(top1 or _top1_scoreline(top10))
    if not parsed or parsed[0] <= parsed[1]:
        return False
    if draw_prob is not None and float(draw_prob) >= DRAW_PROB_HIGH:
        return False
    if rank_1_1 is None or rank_1_1 < 3 or rank_1_1 > 5:
        return False
    return True


def _risk_level(
    *,
    knockout: bool,
    rank_1_1: int | None,
    rank_0_0: int | None,
    support_count: int,
    balanced_ish: bool,
) -> RiskLevel:
    if not knockout:
        return "NONE"
    draw_like = rank_1_1 is not None or rank_0_0 is not None
    if not draw_like:
        return "NONE"
    if rank_1_1 is not None and rank_1_1 <= 5 and support_count >= 1:
        return "HIGH"
    if rank_1_1 is not None and rank_1_1 <= 10 and (balanced_ish or support_count >= 1):
        return "MEDIUM"
    if draw_like and support_count >= 1:
        return "LOW"
    if rank_1_1 is not None and rank_1_1 <= 10:
        return "LOW"
    if rank_0_0 is not None and rank_0_0 <= 10:
        return "LOW"
    return "NONE"


def _owner_note(
    *,
    risk_level: RiskLevel,
    rank_1_1: int | None,
    rank_0_0: int | None,
    recommended_cover: list[str],
    knockout: bool,
) -> str:
    if risk_level == "NONE":
        return "No knockout draw/PEN risk detected."
    covers = ", ".join(recommended_cover) if recommended_cover else "—"
    if rank_1_1 is not None:
        if rank_1_1 <= 5:
            base = (
                "Knockout draw/PEN risk: 1-1 is in ECSE Top-10 and should be considered as cover score."
            )
        elif rank_1_1 <= 10:
            base = f"1-1 appears but only rank {rank_1_1}; use as cover, not main pick."
        else:
            base = "Knockout draw/PEN risk detected."
    elif rank_0_0 is not None:
        base = f"0-0 in ECSE Top-10 (rank {rank_0_0}); consider as low-scoring cover in knockout."
    else:
        base = "Knockout draw/PEN risk detected."
    if risk_level in ("MEDIUM", "HIGH") and "balanced_ish_probs" in covers or risk_level == "MEDIUM":
        if rank_1_1 and rank_1_1 <= 5:
            pass
        elif not rank_1_1 or rank_1_1 > 3:
            base = f"{base} Balanced knockout profile; avoid relying on single exact score."
    note = f"{base} Recommended cover: {covers}. Owner-only research — not public prediction."
    if not knockout:
        return "No knockout draw/PEN risk detected."
    return note


def compute_knockout_draw_pen_risk(
    *,
    competition_key: str,
    round_name: str | None,
    top10: list[dict[str, Any]],
    top1: str | None = None,
    lambda_home: float | None = None,
    lambda_away: float | None = None,
    home_prob: float | None = None,
    away_prob: float | None = None,
    wde: dict[str, Any] | None = None,
    probs: dict[str, float | None] | None = None,
    match_outcome_type: str | None = None,
    penalty_score: str | None = None,
    actual_score: str | None = None,
) -> dict[str, Any]:
    """Deterministic owner-only knockout draw/PEN risk payload."""
    wde = wde or {}
    probs = probs or {}
    knockout = (
        competition_key == DEFAULT_COMPETITION_KEY and _is_knockout_round(round_name)
    )
    rank_1_1 = _score_rank(top10, "1-1")
    rank_0_0 = _score_rank(top10, "0-0")
    draw_like_in_top10 = rank_1_1 is not None or rank_0_0 is not None

    if away_prob is None and home_prob is not None:
        draw_p = probs.get("ft_draw") or probs.get("draw_proxy")
        if draw_p is not None:
            away_prob = max(0.0, 1.0 - float(home_prob) - float(draw_p))
        else:
            away_prob = max(0.0, 1.0 - float(home_prob))

    support_signals, support_count = _collect_market_support(
        wde=wde,
        probs=probs,
        home_prob=home_prob,
        away_prob=away_prob,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        rank_1_1=rank_1_1,
    )
    balanced_ish = "balanced_ish_probs" in support_signals
    draw_prob = probs.get("ft_draw") or probs.get("draw_proxy")

    active = (
        knockout
        and draw_like_in_top10
        and (support_count >= 1 or balanced_ish or (rank_1_1 is not None and rank_1_1 <= 10))
    )
    if active and _should_suppress_home_favorite(
        top10=top10,
        top1=top1,
        home_prob=home_prob,
        wde=wde,
        draw_prob=float(draw_prob) if draw_prob is not None else None,
        rank_1_1=rank_1_1,
        support_signals=support_signals,
    ):
        active = False
        support_signals.append("suppressed_home_favorite_profile")

    level = _risk_level(
        knockout=knockout and active,
        rank_1_1=rank_1_1,
        rank_0_0=rank_0_0,
        support_count=support_count,
        balanced_ish=balanced_ish,
    )
    if not active:
        level = "NONE"

    recommended: list[str] = []
    if rank_1_1 is not None and level != "NONE":
        recommended.append("1-1")
    if rank_0_0 is not None and level != "NONE" and "1-1" not in recommended:
        recommended.append("0-0")
    elif rank_0_0 is not None and level != "NONE" and rank_0_0 <= 6:
        if "0-0" not in recommended:
            recommended.append("0-0")

    mot = str(match_outcome_type or "").upper()
    pen_draw_label = (
        "PEN draw" if mot == "PEN" and actual_score == "1-1" else None
    )

    if actual_score and mot == "FT":
        parsed_actual = _parse_scoreline(actual_score)
        if parsed_actual and parsed_actual[0] != parsed_actual[1]:
            return {
                "knockout_draw_pen_risk": False,
                "risk_level": "NONE",
                "rank_1_1": rank_1_1,
                "rank_0_0": rank_0_0,
                "recommended_cover_scores": [],
                "draw_pen_risk_label": None,
                "support_signals": support_signals,
                "support_signal_count": support_count,
                "knockout_round": knockout,
                "match_outcome_type": mot or None,
                "penalty_score": penalty_score,
                "pen_draw_label": pen_draw_label,
                "owner_note": "No knockout draw/PEN risk detected.",
                "owner_only": True,
                "public_output_changed": False,
            }

    return {
        "knockout_draw_pen_risk": level != "NONE",
        "risk_level": level,
        "rank_1_1": rank_1_1,
        "rank_0_0": rank_0_0,
        "recommended_cover_scores": recommended,
        "draw_pen_risk_label": (
            "Draw/PEN risk" if level != "NONE" else None
        ),
        "support_signals": support_signals,
        "support_signal_count": support_count,
        "knockout_round": knockout,
        "match_outcome_type": mot or None,
        "penalty_score": penalty_score,
        "pen_draw_label": pen_draw_label,
        "owner_note": _owner_note(
            risk_level=level,
            rank_1_1=rank_1_1,
            rank_0_0=rank_0_0,
            recommended_cover=recommended,
            knockout=knockout,
        ),
        "owner_only": True,
        "public_output_changed": False,
    }


def evaluate_fixture_knockout_risk(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    snap = get_snapshot(conn, fixture_id)
    if not snap:
        return None

    snap = _hydrate_snapshot(dict(snap))
    fx = conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc,
               round_name, status
        FROM fixtures WHERE fixture_id = ?
        """,
        (fixture_id,),
    ).fetchone()
    result = conn.execute(
        """
        SELECT final_score, match_outcome_type, penalty_score
        FROM fixture_results WHERE fixture_id = ?
        """,
        (fixture_id,),
    ).fetchone()

    competition_key = str(
        snap.get("competition_key") or (dict(fx)["competition_key"] if fx else DEFAULT_COMPETITION_KEY)
    )
    round_name = snap.get("round_name") or (dict(fx).get("round_name") if fx else None)
    top10 = snap.get("top_10_scorelines") or []
    prediction = {
        "fixture_id": fixture_id,
        "raw_features": snap.get("raw_features") or {},
        "lambda_home": snap.get("lambda_home"),
        "lambda_away": snap.get("lambda_away"),
    }
    probs, _coverage, _snap_id = build_probs_for_fixture(conn, fixture_id, prediction)
    home_prob = probs.get("ft_home")
    away_prob = probs.get("ft_away")
    wde = _load_wde_signals(fixture_id, settings)

    risk = compute_knockout_draw_pen_risk(
        competition_key=competition_key,
        round_name=round_name,
        top10=top10,
        top1=snap.get("top_1_score") or _top1_scoreline(top10),
        lambda_home=snap.get("lambda_home"),
        lambda_away=snap.get("lambda_away"),
        home_prob=float(home_prob) if home_prob is not None else None,
        away_prob=float(away_prob) if away_prob is not None else None,
        wde=wde,
        probs=probs,
        match_outcome_type=(
            (dict(result).get("match_outcome_type") if result else None)
            or (dict(fx).get("status") if fx else None)
        ),
        penalty_score=dict(result).get("penalty_score") if result else None,
        actual_score=dict(result).get("final_score") if result else None,
    )

    return {
        "phase": PHASE,
        "fixture_id": fixture_id,
        "match": f"{snap.get('home_team')} vs {snap.get('away_team')}",
        "kickoff_time": snap.get("kickoff_utc"),
        "competition_key": competition_key,
        "round_name": round_name,
        "prediction_top1": snap.get("top_1_score"),
        "actual_score": dict(result).get("final_score") if result else None,
        "evaluated_at": _utc_now(),
        **risk,
    }


def load_wc_ecse_snapshot_fixtures(
    conn: sqlite3.Connection,
    *,
    competition_key: str = DEFAULT_COMPETITION_KEY,
) -> list[int]:
    ensure_ecse_live_tables(conn)
    rows = conn.execute(
        """
        SELECT DISTINCT s.fixture_id
        FROM ecse_prediction_snapshots s
        WHERE COALESCE(s.competition_key, ?) = ?
        ORDER BY s.fixture_id
        """,
        (competition_key, competition_key),
    ).fetchall()
    return [int(r["fixture_id"]) for r in rows]


def run_historical_knockout_scan(
    conn: sqlite3.Connection,
    *,
    competition_key: str = DEFAULT_COMPETITION_KEY,
) -> dict[str, Any]:
    """Scan finished WC knockout-like fixtures with provider-backed results."""
    ensure_ecse_live_tables(conn)
    rows = conn.execute(
        """
        SELECT
            f.fixture_id,
            f.home_team,
            f.away_team,
            f.round_name,
            f.status AS fixture_status,
            r.final_score,
            r.match_outcome_type,
            r.penalty_score,
            r.home_goals,
            r.away_goals,
            e.rank_of_actual_score,
            s.top_10_scorelines_json
        FROM fixtures f
        INNER JOIN fixture_results r ON r.fixture_id = f.fixture_id
        LEFT JOIN ecse_prediction_snapshots s ON s.fixture_id = f.fixture_id
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id = s.id
        WHERE f.competition_key = ?
        ORDER BY f.kickoff_utc
        """,
        (competition_key,),
    ).fetchall()

    pen_aet = 0
    score_1_1_pen = 0
    score_0_0_pen = 0
    ecse_has_1_1 = 0
    ecse_has_0_0 = 0
    ranks_1_1: list[int] = []
    ranks_0_0: list[int] = []
    knockout_finished = 0
    cases: list[dict[str, Any]] = []

    for raw in rows:
        row = dict(raw)
        if not _is_knockout_round(row.get("round_name")):
            continue
        knockout_finished += 1
        mot = str(row.get("match_outcome_type") or row.get("fixture_status") or "").upper()
        if mot in {"PEN", "AET"}:
            pen_aet += 1
        score = str(row.get("final_score") or "")
        if mot == "PEN" and score == "1-1":
            score_1_1_pen += 1
        if mot == "PEN" and score == "0-0":
            score_0_0_pen += 1

        top10_raw = row.get("top_10_scorelines_json")
        top10: list[dict[str, Any]] = []
        if top10_raw:
            try:
                top10 = json.loads(top10_raw) if isinstance(top10_raw, str) else list(top10_raw)
            except (json.JSONDecodeError, TypeError):
                top10 = []
        r11 = _score_rank(top10, "1-1")
        r00 = _score_rank(top10, "0-0")
        if r11 is not None:
            ecse_has_1_1 += 1
            ranks_1_1.append(r11)
        if r00 is not None:
            ecse_has_0_0 += 1
            ranks_0_0.append(r00)
        cases.append(
            {
                "fixture_id": row["fixture_id"],
                "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                "final_score": score,
                "match_outcome_type": mot,
                "penalty_score": row.get("penalty_score"),
                "rank_1_1": r11,
                "rank_0_0": r00,
                "actual_rank": row.get("rank_of_actual_score"),
            }
        )

    avg_1_1 = round(sum(ranks_1_1) / len(ranks_1_1), 2) if ranks_1_1 else None
    avg_0_0 = round(sum(ranks_0_0) / len(ranks_0_0), 2) if ranks_0_0 else None
    enough_data = knockout_finished >= 8 and pen_aet >= 3

    return {
        "knockout_finished_count": knockout_finished,
        "pen_aet_count": pen_aet,
        "pen_1_1_count": score_1_1_pen,
        "pen_0_0_count": score_0_0_pen,
        "ecse_top10_with_1_1": ecse_has_1_1,
        "ecse_top10_with_0_0": ecse_has_0_0,
        "avg_rank_1_1": avg_1_1,
        "avg_rank_0_0": avg_0_0,
        "cases": cases,
        "enough_data_for_signal": enough_data,
        "scan_note": (
            "Enough knockout/PEN history for owner signal calibration."
            if enough_data
            else "Early sample — owner signal should remain note-only until more WC knockout results arrive."
        ),
    }


@dataclass
class KnockoutRiskRunResult:
    fixture_count: int
    flagged_count: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def run_knockout_draw_pen_risk_evaluation(
    conn: sqlite3.Connection,
    *,
    competition_key: str = DEFAULT_COMPETITION_KEY,
    settings: Settings | None = None,
    jsonl_path: Path | None = None,
    summary_path: Path | None = None,
    penalty_backfill: dict[str, Any] | None = None,
) -> KnockoutRiskRunResult:
    settings = settings or get_settings()
    fixture_ids = load_wc_ecse_snapshot_fixtures(conn, competition_key=competition_key)
    rows: list[dict[str, Any]] = []
    for fid in fixture_ids:
        row = evaluate_fixture_knockout_risk(conn, fid, settings=settings)
        if row:
            rows.append(row)

    historical = run_historical_knockout_scan(conn, competition_key=competition_key)
    flagged = [r for r in rows if r.get("knockout_draw_pen_risk")]

    by_level: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
    for r in rows:
        level = str(r.get("risk_level") or "NONE")
        by_level[level] = by_level.get(level, 0) + 1

    summary = {
        "phase": PHASE,
        "generated_at": _utc_now(),
        "competition_key": competition_key,
        "fixture_count": len(rows),
        "flagged_count": len(flagged),
        "by_risk_level": by_level,
        "historical_scan": historical,
        "penalty_backfill": penalty_backfill or {},
        "flagged_fixtures": [
            {
                "fixture_id": r["fixture_id"],
                "match": r.get("match"),
                "risk_level": r.get("risk_level"),
                "rank_1_1": r.get("rank_1_1"),
                "rank_0_0": r.get("rank_0_0"),
                "recommended_cover_scores": r.get("recommended_cover_scores"),
                "owner_note": r.get("owner_note"),
            }
            for r in flagged
        ],
        "public_output_changed": False,
        "disclaimer": "Owner/internal research signal only. No public prediction changes.",
    }

    target_jsonl = jsonl_path or RISK_JSONL
    target_summary = summary_path or RISK_SUMMARY
    target_jsonl.parent.mkdir(parents=True, exist_ok=True)
    target_summary.parent.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(r, default=str) for r in rows)
    target_jsonl.write_text(lines + ("\n" if lines else ""), encoding="utf-8")
    target_summary.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    return KnockoutRiskRunResult(
        fixture_count=len(rows),
        flagged_count=len(flagged),
        rows=rows,
        summary=summary,
    )


def load_knockout_draw_pen_risk_summary(path: Path | None = None) -> dict[str, Any] | None:
    target = path or RISK_SUMMARY
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_knockout_draw_pen_risk_rows(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or RISK_JSONL
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
