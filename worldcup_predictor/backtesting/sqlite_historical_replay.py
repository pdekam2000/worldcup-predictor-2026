"""Phase 31B — offline historical replay from SQLite fixtures + results."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from worldcup_predictor.accuracy.evaluator import actual_1x2, actual_over_under
from worldcup_predictor.agents.base import AgentContext
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.api import market_ranking_engine as mre
from worldcup_predictor.api.prediction_output import build_detailed_markets, build_prediction_output
from worldcup_predictor.backtesting.historical_loader import (
    HistoricalMatchRow,
    build_form_history,
    build_intelligence_report,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.prediction.extended_markets import attach_extended_markets_to_prediction
from worldcup_predictor.prediction.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLDS: tuple[int, ...] = (40, 45, 50)
DQ_THRESHOLD_WDE = 50.0
DQ_THRESHOLD_30C = 45.0

CONFIDENCE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-40", 0.0, 40.0),
    ("40-50", 40.0, 50.0),
    ("50-55", 50.0, 55.0),
    ("55-60", 55.0, 60.0),
    ("60-65", 60.0, 65.0),
    ("65-70", 65.0, 70.0),
    ("70-75", 70.0, 75.0),
    ("75+", 75.0, 1000.0),
)

OutcomeResult = Literal["correct", "wrong", "void"]


@dataclass
class ActualOutcomes:
    home_goals: int
    away_goals: int
    actual_1x2: str
    actual_ou: str
    actual_btts: str


@dataclass
class FixtureReplayCore:
    fixture_id: int
    match_name: str
    competition_key: str
    kickoff: str
    confidence: float
    data_quality: float
    wde_no_bet: bool
    wde_no_bet_reasons: list[str]
    is_placeholder: bool
    confidence_level: str
    prediction: MatchPrediction
    detailed_markets: dict[str, Any]
    specialist_summary: dict[str, Any]
    actual: ActualOutcomes
    errors: list[str] = field(default_factory=list)


@dataclass
class PickEvaluation:
    fixture_id: int
    threshold: int
    market: str
    market_key: str
    pick: str
    selection: str
    confidence: float
    rank_score: float | None
    bucket: str
    outcome: OutcomeResult


def _parse_kickoff(value: str | None) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return datetime(2020, 1, 1)
    if raw.endswith("Z"):
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    if "T" in raw:
        return datetime.fromisoformat(raw.replace("Z", ""))
    return datetime.fromisoformat(f"{raw[:10]}T12:00:00")


def _parse_ht_score(value: str | None) -> tuple[int | None, int | None]:
    if not value or "-" not in str(value):
        return None, None
    parts = str(value).split("-", 1)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def _actual_btts(home_goals: int, away_goals: int) -> str:
    return "yes" if home_goals > 0 and away_goals > 0 else "no"


def _extract_odds_from_snapshot(payload: Any) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "odds_home": None,
        "odds_draw": None,
        "odds_away": None,
        "over_2_5_odds": None,
        "under_2_5_odds": None,
    }
    if not payload:
        return out
    data = payload
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return out
    bookmakers = data if isinstance(data, list) else (data.get("bookmakers") or data.get("response") or [])
    if isinstance(bookmakers, dict):
        bookmakers = bookmakers.get("bookmakers") or []
    if not isinstance(bookmakers, list):
        return out
    for bm in bookmakers:
        for bet in bm.get("bets") or []:
            name = str(bet.get("name") or "").lower()
            values = bet.get("values") or []
            if "match winner" in name or name == "1x2":
                for v in values:
                    val = str(v.get("value") or "").lower()
                    try:
                        odd = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if val in ("home", "1"):
                        out["odds_home"] = odd
                    elif val == "draw":
                        out["odds_draw"] = odd
                    elif val in ("away", "2"):
                        out["odds_away"] = odd
            if "over/under" in name or "goals over" in name:
                for v in values:
                    val = str(v.get("value") or "").lower()
                    try:
                        odd = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if "over 2.5" in val:
                        out["over_2_5_odds"] = odd
                    if "under 2.5" in val:
                        out["under_2_5_odds"] = odd
        if out["odds_home"]:
            break
    return out


def load_finished_match_rows(
    repo: FootballIntelligenceRepository,
    *,
    limit: int | None = None,
) -> list[HistoricalMatchRow]:
    query = """
        SELECT f.*, r.home_goals, r.away_goals, r.halftime_score, r.over_under_2_5, r.winner
        FROM fixtures f
        INNER JOIN fixture_results r ON f.fixture_id = r.fixture_id
        WHERE f.is_placeholder = 0
        ORDER BY f.kickoff_utc ASC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = repo._conn.execute(query).fetchall()
    historical: list[HistoricalMatchRow] = []
    for row in rows:
        rd = dict(row)
        fid = int(rd["fixture_id"])
        ht_h, ht_a = _parse_ht_score(rd.get("halftime_score"))
        odds = {"odds_home": None, "odds_draw": None, "odds_away": None, "over_2_5_odds": None, "under_2_5_odds": None}
        snaps = repo.fetch_odds_snapshots(fid, limit=1)
        if snaps:
            try:
                odds = _extract_odds_from_snapshot(json.loads(snaps[0]["payload_json"]))
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        historical.append(
            HistoricalMatchRow(
                fixture_id=fid,
                date=_parse_kickoff(rd.get("kickoff_utc")),
                competition=str(rd.get("competition_key") or "unknown"),
                round=str(rd.get("round_name") or ""),
                home_team=str(rd.get("home_team") or "Home"),
                away_team=str(rd.get("away_team") or "Away"),
                home_goals=int(rd["home_goals"]),
                away_goals=int(rd["away_goals"]),
                halftime_home_goals=ht_h,
                halftime_away_goals=ht_a,
                venue=str(rd.get("venue") or "Unknown"),
                referee=None,
                odds_home=odds.get("odds_home"),
                odds_draw=odds.get("odds_draw"),
                odds_away=odds.get("odds_away"),
                over_2_5_odds=odds.get("over_2_5_odds"),
                under_2_5_odds=odds.get("under_2_5_odds"),
                source="api",
                is_demo=False,
            )
        )
    return historical


def _apply_enrichment(report: MatchIntelligenceReport, repo: FootballIntelligenceRepository) -> None:
    row = repo.get_fixture_enrichment_row(report.fixture_id)
    if not row:
        return
    for key, col in (
        ("lineups", "lineups_json"),
        ("statistics", "statistics_json"),
        ("events", "events_json"),
        ("odds", "odds_json"),
    ):
        raw = row.get(col)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if key == "lineups" and parsed:
            report.lineups = {"available": True, "items": parsed}
            report.missing_data = [m for m in report.missing_data if m != "lineups"]
        elif key == "statistics" and parsed:
            report.fixture_statistics = {"items": parsed}
            report.missing_data = [m for m in report.missing_data if m not in ("fixture_statistics", "statistics")]
        elif key == "events" and parsed:
            report.fixture_events = parsed if isinstance(parsed, list) else []
        elif key == "odds" and parsed:
            report.odds = report.odds or type(report.odds)(fixture_id=report.fixture_id)  # type: ignore
            if hasattr(report.odds, "available"):
                report.odds.available = True
                report.odds.bookmakers = parsed if isinstance(parsed, list) else [parsed]
            report.missing_data = [m for m in report.missing_data if m != "odds"]


def _offline_settings(base: Settings | None = None) -> Settings:
    settings = (base or get_settings()).model_copy(
        update={
            "api_football_key": "",
            "openai_api_key": "",
            "sportmonks_api_token": "",
            "sportmonks_api_key": "",
            "the_odds_api_key": "",
            "rapid_football_stats_key": "",
            "rapid_xg_key": "",
            "rapid_open_weather_key": "",
            "rapid_football_stats_enabled": False,
            "rapid_xg_enabled": False,
            "rapid_open_weather_enabled": False,
        }
    )
    return settings


def _data_quality_pct(prediction: MatchPrediction) -> float:
    if prediction.confidence_breakdown is not None:
        score = float(prediction.confidence_breakdown.data_quality_score)
        return score * 100 if score <= 1.0 else score
    raw = (prediction.metadata or {}).get("data_quality_pct")
    if raw is not None:
        try:
            val = float(raw)
            return val * 100 if val <= 1.0 else val
        except (TypeError, ValueError):
            pass
    return float(prediction.prediction_quality_score or 0.0)


def _specialist_summary_from_report(report: MatchSpecialistReport | None) -> dict[str, Any]:
    if report is None:
        return {"aggregated_score": 50.0, "agents": {}}
    agents: dict[str, Any] = {}
    for name, sig in report.signals.items():
        agents[name] = {
            "domain": sig.domain,
            "status": sig.status,
            "impact_score": sig.impact_score,
        }
    return {
        "aggregated_score": report.aggregated_signal_score or 50.0,
        "source": report.source,
        "agents": agents,
    }


def replay_fixture_core(
    row: HistoricalMatchRow,
    form_history: dict[int, tuple[list[str], list[str]]],
    *,
    settings: Settings | None = None,
    run_specialists: bool = True,
) -> FixtureReplayCore:
    settings = _offline_settings(settings)
    home_form, away_form = form_history.get(row.fixture_id, ([], []))
    report = build_intelligence_report(row, home_form=home_form, away_form=away_form)
    repo = FootballIntelligenceRepository()
    _apply_enrichment(report, repo)
    from worldcup_predictor.backtesting.dq_recalculator import recalculate_data_quality
    recalculate_data_quality(report)

    context = AgentContext(
        settings=settings,
        competition_key=report.fixture.competition_key if report.fixture else "world_cup_2026",
        locale="en",
    )
    context.shared["intelligence_reports"] = {row.fixture_id: report}
    context.shared["phase31b_offline_replay"] = True

    specialist_report: MatchSpecialistReport | None = None
    if run_specialists:
        orchestrator = SpecialistOrchestrator(context)
        specialist_result = orchestrator.run(fixture_id=row.fixture_id)
        if specialist_result.success and isinstance(specialist_result.data, MatchSpecialistReport):
            specialist_report = specialist_result.data
            report.specialist_report = specialist_report

    engine = ScoringEngine()
    prediction = engine.predict(
        report,
        specialist_report=specialist_report,
        use_weighted_decision=True,
    )
    attach_extended_markets_to_prediction(prediction, report)
    detailed = build_detailed_markets(prediction)
    specialist_summary = _specialist_summary_from_report(specialist_report)

    wde_reasons: list[str] = []
    if prediction.audit_report and prediction.audit_report.trace:
        wde_reasons = list(prediction.audit_report.trace.no_bet_reasons or [])

    actual = ActualOutcomes(
        home_goals=row.home_goals,
        away_goals=row.away_goals,
        actual_1x2=actual_1x2(row.home_goals, row.away_goals),
        actual_ou=actual_over_under(row.home_goals, row.away_goals),
        actual_btts=_actual_btts(row.home_goals, row.away_goals),
    )

    return FixtureReplayCore(
        fixture_id=row.fixture_id,
        match_name=f"{row.home_team} vs {row.away_team}",
        competition_key=report.fixture.competition_key if report.fixture else row.competition,
        kickoff=row.date.isoformat(),
        confidence=float(prediction.confidence_score or 0.0),
        data_quality=_data_quality_pct(prediction),
        wde_no_bet=bool(prediction.no_bet_flag),
        wde_no_bet_reasons=wde_reasons,
        is_placeholder=bool(prediction.is_placeholder),
        confidence_level=str(prediction.confidence_level.value if hasattr(prediction.confidence_level, "value") else prediction.confidence_level),
        prediction=prediction,
        detailed_markets=detailed,
        specialist_summary=specialist_summary,
        actual=actual,
    )


def _non_confidence_wde_block(core: FixtureReplayCore) -> bool:
    if not core.wde_no_bet:
        return False
    if core.confidence >= 60 and core.data_quality >= DQ_THRESHOLD_WDE:
        return True
    for reason in core.wde_no_bet_reasons:
        if reason.startswith("confidence_below") or reason.startswith("confidence_level"):
            continue
        return True
    return False


def is_no_bet_at_threshold(core: FixtureReplayCore, threshold: float) -> bool:
    if core.is_placeholder:
        return True
    if core.data_quality < DQ_THRESHOLD_WDE:
        return True
    if core.confidence < threshold:
        return True
    if _non_confidence_wde_block(core):
        return True
    if core.confidence_level in ("unavailable", "low") and core.confidence < threshold:
        return True
    return False


def build_ranking_at_threshold(core: FixtureReplayCore, threshold: float) -> dict[str, Any]:
    pred = replace(core.prediction, no_bet_flag=is_no_bet_at_threshold(core, threshold))
    orig_min = mre._MIN_CONFIDENCE
    try:
        mre._MIN_CONFIDENCE = float(threshold)
        return build_prediction_output(pred, specialist_summary=core.specialist_summary)
    finally:
        mre._MIN_CONFIDENCE = orig_min


def _normalize_1x2(selection: str) -> str:
    mapping = {"home": "home_win", "away": "away_win", "home_win": "home_win", "away_win": "away_win", "draw": "draw"}
    return mapping.get(selection, selection)


def evaluate_selection(
    market_key: str,
    selection: str,
    actual: ActualOutcomes,
) -> OutcomeResult:
    sel = (selection or "").strip().lower()
    mk = (market_key or "").strip().lower()
    if not sel or sel in ("none", "tbd", "unknown"):
        return "void"

    if mk in ("1x2", "match_winner", "match_winner_ft"):
        pred = _normalize_1x2(sel)
        return "correct" if pred == actual.actual_1x2 else "wrong"

    if mk in ("over_under_2_5", "over_under_25", "ou_2_5"):
        return "correct" if sel == actual.actual_ou else "wrong"

    if mk == "btts":
        return "correct" if sel == actual.actual_btts else "wrong"

    if mk == "double_chance":
        a = actual.actual_1x2
        if sel == "home_or_draw":
            return "correct" if a in ("home_win", "draw") else "wrong"
        if sel == "home_or_away":
            return "correct" if a in ("home_win", "away_win") else "wrong"
        if sel == "draw_or_away":
            return "correct" if a in ("draw", "away_win") else "wrong"

    if mk == "first_goal_team":
        return "void"

    return "void"


def _pick_rows_from_output(
    core: FixtureReplayCore,
    threshold: int,
    output: dict[str, Any],
) -> list[PickEvaluation]:
    rows: list[PickEvaluation] = []
    no_bet = bool(output.get("no_bet"))

    def add_pick(pick: dict[str, Any] | None, bucket: str) -> None:
        if not pick or no_bet:
            return
        mk = str(pick.get("market_key") or "")
        sel = str(pick.get("selection") or pick.get("pick") or "")
        outcome = evaluate_selection(mk, sel, core.actual)
        rows.append(
            PickEvaluation(
                fixture_id=core.fixture_id,
                threshold=threshold,
                market=str(pick.get("market") or mk),
                market_key=mk,
                pick=str(pick.get("pick") or sel),
                selection=sel,
                confidence=core.confidence,
                rank_score=float(pick.get("market_rank_score")) if pick.get("market_rank_score") is not None else None,
                bucket=bucket,
                outcome=outcome,
            )
        )

    add_pick(output.get("safe_pick"), "safe")
    add_pick(output.get("value_pick"), "value")
    add_pick(output.get("aggressive_pick"), "aggressive")

    for rec in output.get("recommended_bets") or []:
        if str(rec.get("status") or "").lower() == "no_bet":
            continue
        mk = str(rec.get("market") or "").lower().replace(" ", "_")
        sel = str(rec.get("pick") or "")
        if mk == "double_chance":
            sel_map = {
                "home or draw": "home_or_draw",
                "home or away": "home_or_away",
                "draw or away": "draw_or_away",
            }
            sel = sel_map.get(sel.lower(), sel)
        if "over/under" in mk or mk == "over/under_2.5":
            mk = "over_under_2_5"
            sel = "over_2_5" if "over" in sel.lower() else "under_2_5"
        outcome = evaluate_selection(mk, sel, core.actual)
        rows.append(
            PickEvaluation(
                fixture_id=core.fixture_id,
                threshold=threshold,
                market=str(rec.get("market") or mk),
                market_key=mk,
                pick=str(rec.get("pick") or sel),
                selection=sel,
                confidence=core.confidence,
                rank_score=float(rec.get("market_rank_score")) if rec.get("market_rank_score") is not None else None,
                bucket=str(rec.get("bucket") or "recommended").lower(),
                outcome=outcome,
            )
        )

    dm = output.get("detailed_markets") or core.detailed_markets
    for mk, key, block_key in (
        ("match_winner", "1x2", "match_winner"),
        ("over_under_2_5", "over_under_2_5", "over_under_25"),
        ("btts", "btts", "btts"),
    ):
        block = dm.get(block_key) or {}
        sel = str(block.get("selection") or "")
        if not sel:
            continue
        outcome = evaluate_selection(key, sel, core.actual)
        rows.append(
            PickEvaluation(
                fixture_id=core.fixture_id,
                threshold=threshold,
                market=mk,
                market_key=key,
                pick=sel,
                selection=sel,
                confidence=core.confidence,
                rank_score=None,
                bucket="model",
                outcome=outcome,
            )
        )

    dc = dm.get("double_chance") or {}
    dc_probs = dc.get("probabilities") if isinstance(dc.get("probabilities"), dict) else dc
    if isinstance(dc_probs, dict) and dc_probs:
        best = max(dc_probs.items(), key=lambda kv: float(kv[1] or 0))
        outcome = evaluate_selection("double_chance", str(best[0]), core.actual)
        rows.append(
            PickEvaluation(
                fixture_id=core.fixture_id,
                threshold=threshold,
                market="double_chance",
                market_key="double_chance",
                pick=str(best[0]),
                selection=str(best[0]),
                confidence=core.confidence,
                rank_score=None,
                bucket="model",
                outcome=outcome,
            )
        )

    return rows


def _aggregate_picks(picks: list[PickEvaluation]) -> dict[str, Any]:
    scored = [p for p in picks if p.outcome in ("correct", "wrong")]
    correct = sum(1 for p in scored if p.outcome == "correct")
    wrong = sum(1 for p in scored if p.outcome == "wrong")
    void = sum(1 for p in picks if p.outcome == "void")
    total = len(scored)
    rank_scores = [p.rank_score for p in picks if p.rank_score is not None]
    return {
        "total_picks": total,
        "correct": correct,
        "wrong": wrong,
        "void": void,
        "winrate": round(correct / total, 4) if total else None,
        "coverage": total,
        "average_rank_score": round(mean(rank_scores), 4) if rank_scores else None,
    }


def run_sqlite_historical_replay(
    *,
    db_path: str | Path | None = None,
    limit: int | None = None,
    run_specialists: bool = True,
) -> dict[str, Any]:
    repo = FootballIntelligenceRepository(path=str(db_path) if db_path else None)
    rows = load_finished_match_rows(repo, limit=limit)
    form_history = build_form_history(rows)
    settings = _offline_settings()

    cores: list[FixtureReplayCore] = []
    all_picks: list[PickEvaluation] = []
    errors = 0

    for idx, row in enumerate(rows):
        try:
            core = replay_fixture_core(row, form_history, settings=settings, run_specialists=run_specialists)
            cores.append(core)
            for threshold in CONFIDENCE_THRESHOLDS:
                output = build_ranking_at_threshold(core, float(threshold))
                all_picks.extend(_pick_rows_from_output(core, threshold, output))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.exception("Replay failed fixture %s: %s", row.fixture_id, exc)
        if (idx + 1) % 100 == 0:
            logger.info("Replay progress %s/%s", idx + 1, len(rows))

    repo.close()

    threshold_summary: dict[str, Any] = {}
    for threshold in CONFIDENCE_THRESHOLDS:
        nb = sum(1 for c in cores if is_no_bet_at_threshold(c, float(threshold)))
        total = len(cores) or 1
        th_picks = [p for p in all_picks if p.threshold == threshold]
        bucket_picks = {
            "safe_pick": _aggregate_picks([p for p in th_picks if p.bucket == "safe"]),
            "value_pick": _aggregate_picks([p for p in th_picks if p.bucket == "value"]),
            "aggressive_pick": _aggregate_picks([p for p in th_picks if p.bucket == "aggressive"]),
            "recommended_bets": _aggregate_picks([p for p in th_picks if p.bucket in ("safe", "value", "recommended")]),
        }
        market_picks: dict[str, Any] = {}
        for mk in ("1x2", "over_under_2_5", "btts", "double_chance", "match_winner"):
            market_picks[mk] = _aggregate_picks([p for p in th_picks if p.market_key in (mk, "match_winner") and p.bucket == "model"])
        threshold_summary[str(threshold)] = {
            "total_matches": len(cores),
            "no_bet_count": nb,
            "no_bet_rate": round(nb / total, 4),
            "recommendation_rate": round(1 - nb / total, 4),
            "average_confidence": round(mean([c.confidence for c in cores]), 2) if cores else 0.0,
            "markets": market_picks,
            "ranked_picks": bucket_picks,
        }

    conf_bucket_stats: dict[str, Any] = {}
    for label, lo, hi in CONFIDENCE_BUCKETS:
        bucket_cores = [c for c in cores if lo <= c.confidence < hi]
        if not bucket_cores:
            conf_bucket_stats[label] = {"count": 0, "winrate_1x2": None}
            continue
        correct = 0
        total = 0
        for c in bucket_cores:
            sel = _normalize_1x2(str(c.prediction.one_x_two.selection or ""))
            if sel:
                total += 1
                if sel == c.actual.actual_1x2:
                    correct += 1
        conf_bucket_stats[label] = {
            "count": len(bucket_cores),
            "winrate_1x2": round(correct / total, 4) if total else None,
        }

    return {
        "meta": {
            "phase": "31B",
            "total_finished_matches": len(rows),
            "replayed_ok": len(cores),
            "errors": errors,
            "confidence_thresholds": list(CONFIDENCE_THRESHOLDS),
            "dq_threshold_wde": DQ_THRESHOLD_WDE,
            "dq_threshold_30c": DQ_THRESHOLD_30C,
            "run_specialists": run_specialists,
            "external_api_calls": 0,
        },
        "threshold_matrix": threshold_summary,
        "confidence_bucket_analysis": conf_bucket_stats,
        "cores": cores,
        "picks": all_picks,
    }


def write_replay_artifacts(result: dict[str, Any], artifacts_dir: Path) -> tuple[Path, Path]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary_path = artifacts_dir / "backtest_ranked_picks_summary.json"
    csv_path = artifacts_dir / "backtest_ranked_picks_full.csv"

    summary = {
        "meta": result["meta"],
        "threshold_matrix": result["threshold_matrix"],
        "confidence_bucket_analysis": result["confidence_bucket_analysis"],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    picks: list[PickEvaluation] = result["picks"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "fixture_id",
                "threshold",
                "market",
                "market_key",
                "pick",
                "selection",
                "confidence",
                "rank_score",
                "bucket",
                "outcome",
            ],
        )
        writer.writeheader()
        for p in picks:
            writer.writerow(
                {
                    "fixture_id": p.fixture_id,
                    "threshold": p.threshold,
                    "market": p.market,
                    "market_key": p.market_key,
                    "pick": p.pick,
                    "selection": p.selection,
                    "confidence": p.confidence,
                    "rank_score": p.rank_score,
                    "bucket": p.bucket,
                    "outcome": p.outcome,
                }
            )

    return summary_path, csv_path
