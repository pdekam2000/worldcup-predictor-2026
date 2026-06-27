"""Phase 35 — accuracy-driven optimization from real evaluated predictions."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.admin.accuracy_center import _parse_detail, _parse_payload
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

_DISCLAIMER = (
    "Advisory analytics from real evaluated predictions only. "
    "No model weights, WDE thresholds, or National Team Intelligence were modified."
)

CONFIDENCE_BUCKETS: list[tuple[str, float, float | None]] = [
    ("0-50", 0, 50),
    ("50-55", 50, 55),
    ("55-60", 55, 60),
    ("60-65", 60, 65),
    ("65-70", 65, 70),
    ("70-75", 70, 75),
    ("75-80", 75, 80),
    ("80+", 80, None),
]

Outcome = Literal["correct", "wrong", "pending", "unknown", "void"]


@dataclass
class BucketStats:
    key: str
    correct: int = 0
    wrong: int = 0
    pending: int = 0
    unknown: int = 0

    @property
    def predictions(self) -> int:
        return self.correct + self.wrong + self.pending + self.unknown

    @property
    def settled(self) -> int:
        return self.correct + self.wrong

    def record(self, status: str | None) -> None:
        s = str(status or "unknown").lower()
        if s == "correct":
            self.correct += 1
        elif s == "wrong":
            self.wrong += 1
        elif s == "pending":
            self.pending += 1
        else:
            self.unknown += 1

    def to_dict(self, *, midpoint: float | None = None) -> dict[str, Any]:
        wr = _winrate(self.correct, self.settled)
        roi = _roi_proxy(self.correct, self.wrong)
        out: dict[str, Any] = {
            "key": self.key,
            "label": self.key,
            "predictions": self.predictions,
            "correct": self.correct,
            "wrong": self.wrong,
            "pending": self.pending,
            "unknown": self.unknown,
            "settled": self.settled,
            "winrate": wr,
            "roi_proxy": roi,
        }
        if midpoint is not None and wr is not None:
            out["expected_winrate"] = round(midpoint / 100.0, 4)
            out["calibration_gap"] = round(wr - midpoint / 100.0, 4)
        return out


def _winrate(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(correct / total, 4)


def _roi_proxy(correct: int, wrong: int) -> float | None:
    settled = correct + wrong
    if settled <= 0:
        return None
    return round((correct - wrong) / settled, 4)


def _normalize_confidence(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val <= 1.0:
        val *= 100.0
    return val


def _confidence_bucket(conf: float | None) -> str:
    if conf is None:
        return "unknown"
    for key, low, high in CONFIDENCE_BUCKETS:
        if high is None and conf >= low:
            return key
        if high is not None and low <= conf < high:
            return key
    return "80+"


def _bucket_midpoint(key: str) -> float | None:
    for label, low, high in CONFIDENCE_BUCKETS:
        if label == key:
            if high is None:
                return low + 10.0
            return (low + high) / 2.0
    return None


def _status_category(status: str | None) -> Outcome | str:
    s = str(status or "").lower()
    if s in {"correct", "wrong", "pending", "void"}:
        return s  # type: ignore[return-value]
    return "unknown"


def _eval_ht_result(payload: dict[str, Any], actual: str | None) -> str:
    if not actual:
        return "unknown"
    ht = (payload.get("detailed_markets") or {}).get("halftime") or {}
    probs = ht.get("probabilities") or {}
    if not probs:
        sel = ht.get("selection")
        if not sel:
            return "void"
        pred = str(sel).lower()
    else:
        pred = max(probs, key=lambda k: float(probs.get(k) or 0)).replace("home_win", "home_win")
        mapping = {"home": "home_win", "away": "away_win", "draw": "draw"}
        pred = mapping.get(pred, pred)
    return "correct" if pred == actual else "wrong"


def _eval_first_team_to_score(payload: dict[str, Any], outcome_home_first: bool | None) -> str:
    fg = (payload.get("detailed_markets") or {}).get("first_goal") or {}
    team = fg.get("team")
    if not team or outcome_home_first is None:
        return "void"
    home = str(payload.get("home_team") or "")
    away = str(payload.get("away_team") or "")
    pred_home = team.lower() in home.lower() if home else False
    pred_away = team.lower() in away.lower() if away else False
    if pred_home and outcome_home_first:
        return "correct"
    if pred_away and not outcome_home_first:
        return "correct"
    if pred_home or pred_away:
        return "wrong"
    return "unknown"


def _collect_market_statuses(
    ev: dict[str, Any],
    payload: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, str | None]:
    markets = detail.get("markets") or {}
    out: dict[str, str | None] = {
        "1X2": markets.get("1x2") or ev.get("market_1x2_status"),
        "Double Chance": markets.get("double_chance") or ev.get("market_dc_status"),
        "BTTS": markets.get("btts") or ev.get("market_btts_status"),
        "Over 2.5": None,
        "Under 2.5": None,
        "HT Result": None,
        "First Team To Score": None,
    }
    ou = markets.get("over_under_2_5") or ev.get("market_ou_status")
    ou_sel = ((payload.get("probabilities") or {}).get("over_under_2_5") or {}).get("selection")
    if ou_sel and "over" in str(ou_sel).lower():
        out["Over 2.5"] = ou
        out["Under 2.5"] = "wrong" if ou == "correct" else ("correct" if ou == "wrong" else ou)
    elif ou_sel and "under" in str(ou_sel).lower():
        out["Under 2.5"] = ou
        out["Over 2.5"] = "wrong" if ou == "correct" else ("correct" if ou == "wrong" else ou)
    else:
        out["Over 2.5"] = ou if ou_sel and "over" in str(ou_sel).lower() else None
        out["Under 2.5"] = ou if ou_sel and "under" in str(ou_sel).lower() else None

    actual = ev.get("actual_result") or detail.get("actual_result")
    if actual and ev.get("overall_status") in {"correct", "wrong", "pending"}:
        out["HT Result"] = _eval_ht_result(payload, actual)

    return out


def _agent_signals(payload: dict[str, Any]) -> dict[str, bool]:
    nat = payload.get("national_team_intelligence") or {}
    specialist = payload.get("specialist_summary") or {}
    agents = specialist.get("agents") or {}
    signals: dict[str, bool] = {
        "Consensus Agent": (specialist.get("aggregated_score") is not None),
        "National Form": nat.get("national_form_score") is not None,
        "National H2H": nat.get("national_h2h_score") is not None,
        "Injury Impact": nat.get("injury_impact_score") is not None,
        "Squad Strength": nat.get("squad_strength_score") is not None,
    }
    for name, block in agents.items():
        if isinstance(block, dict) and str(block.get("status", "")).lower() in {"available", "partial"}:
            label = name.replace("_", " ").title()
            signals[label] = True
    return signals


def build_accuracy_optimization_report(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    """Full Phase 35 report from real evaluated production predictions."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    evaluations = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)

    conf_buckets: dict[str, BucketStats] = {b[0]: BucketStats(key=b[0]) for b in CONFIDENCE_BUCKETS}
    conf_buckets["unknown"] = BucketStats(key="unknown")

    rec_stats: dict[str, BucketStats] = {
        "Safe Pick": BucketStats(key="Safe Pick"),
        "Value Pick": BucketStats(key="Value Pick"),
        "Aggressive Pick": BucketStats(key="Aggressive Pick"),
        "Caution Pick": BucketStats(key="Caution Pick"),
        "Best Available Pick": BucketStats(key="Best Available Pick"),
        "Official Picks": BucketStats(key="Official Picks"),
        "Caution Picks": BucketStats(key="Caution Picks"),
        "Recommended Bets": BucketStats(key="Recommended Bets"),
    }

    market_stats: dict[str, BucketStats] = defaultdict(lambda: BucketStats(key=""))
    agent_stats: dict[str, BucketStats] = defaultdict(lambda: BucketStats(key=""))
    agent_baseline = BucketStats(key="baseline")

    for ev in evaluations:
        fid = int(ev["fixture_id"])
        payload = _parse_payload(repo.get_worldcup_stored_prediction(fid))
        detail = _parse_detail(ev)
        markets_detail = detail.get("markets") or {}

        conf = _normalize_confidence(payload.get("confidence"))
        bucket_key = _confidence_bucket(conf)
        conf_buckets.setdefault(bucket_key, BucketStats(key=bucket_key))
        overall = ev.get("overall_status") or detail.get("status")
        conf_buckets[bucket_key].record(overall)
        agent_baseline.record(overall)

        no_bet = bool(ev.get("no_bet") or payload.get("no_bet"))
        pick_tier = str(detail.get("pick_tier") or payload.get("pick_tier") or ("caution" if no_bet else "official"))
        if pick_tier == "official" and not no_bet:
            rec_stats["Official Picks"].record(overall)
        else:
            rec_stats["Caution Picks"].record(overall)

        for key, label in (
            ("safe_pick", "Safe Pick"),
            ("value_pick", "Value Pick"),
            ("aggressive_pick", "Aggressive Pick"),
            ("caution_pick", "Caution Pick"),
            ("best_available_pick", "Best Available Pick"),
        ):
            st = markets_detail.get(key) or ev.get(f"{key}_status")
            if st not in {None, "void"}:
                rec_stats[label].record(st)

        for i, rec in enumerate(payload.get("recommended_bets") or []):
            if isinstance(rec, dict):
                st = markets_detail.get(f"recommended_{i}")
                if st:
                    rec_stats["Recommended Bets"].record(st)

        for mname, st in _collect_market_statuses(ev, payload, detail).items():
            if st and st not in {"void"}:
                if not market_stats[mname].key:
                    market_stats[mname].key = mname
                market_stats[mname].record(st)

        for agent, present in _agent_signals(payload).items():
            if not present:
                continue
            if not agent_stats[agent].key:
                agent_stats[agent].key = agent
            agent_stats[agent].record(overall)

    confidence_analysis = []
    for key, _, _ in CONFIDENCE_BUCKETS:
        mid = _bucket_midpoint(key)
        confidence_analysis.append(conf_buckets[key].to_dict(midpoint=mid))
    if conf_buckets["unknown"].predictions:
        confidence_analysis.append(conf_buckets["unknown"].to_dict())

    calibration_rows = []
    for row in confidence_analysis:
        if row.get("settled", 0) < 1:
            continue
        gap = row.get("calibration_gap")
        expected = row.get("expected_winrate")
        actual = row.get("winrate")
        label = "calibrated"
        if gap is not None:
            if gap < -0.05:
                label = "overconfident"
            elif gap > 0.05:
                label = "underconfident"
        calibration_rows.append({
            **row,
            "assessment": label,
            "summary": (
                f"Confidence ~{row['label']}: predicted {round((expected or 0) * 100, 1)}% "
                f"vs actual {round((actual or 0) * 100, 1)}% ({label})"
            ),
        })

    recommendation_analysis = [rec_stats[k].to_dict() for k in rec_stats if rec_stats[k].predictions > 0]
    recommendation_analysis.sort(key=lambda x: (x.get("winrate") is None, -(x.get("winrate") or 0)))

    market_analysis = [v.to_dict() for v in market_stats.values() if v.predictions > 0]
    market_analysis.sort(key=lambda x: (x.get("winrate") is None, -(x.get("winrate") or 0)))

    baseline_wr = _winrate(agent_baseline.correct, agent_baseline.settled)
    agent_analysis = []
    for name, stats in agent_stats.items():
        wr = _winrate(stats.correct, stats.settled)
        contribution = None
        if wr is not None and baseline_wr is not None:
            contribution = round(wr - baseline_wr, 4)
        agent_analysis.append({
            **stats.to_dict(),
            "label": name,
            "contribution_vs_baseline": contribution,
        })
    agent_analysis.sort(key=lambda x: (x.get("winrate") is None, -(x.get("winrate") or 0)))

    best_markets = [m for m in market_analysis if m.get("winrate") is not None][:5]
    worst_markets = sorted(
        [m for m in market_analysis if m.get("winrate") is not None],
        key=lambda x: x.get("winrate") or 0,
    )[:5]
    best_buckets = sorted(
        [b for b in confidence_analysis if b.get("settled", 0) >= 1],
        key=lambda x: x.get("winrate") or 0,
        reverse=True,
    )[:3]
    worst_buckets = sorted(
        [b for b in confidence_analysis if b.get("settled", 0) >= 1],
        key=lambda x: x.get("winrate") or 0,
    )[:3]

    strongest_rec = recommendation_analysis[0] if recommendation_analysis else None
    suggestions = _build_suggestions(
        confidence_analysis, market_analysis, recommendation_analysis, agent_analysis, calibration_rows,
    )

    insights = _build_insights(
        confidence_analysis, market_analysis, recommendation_analysis, agent_analysis, calibration_rows,
    )

    return {
        "status": "ok",
        "schema_version": "35-v1",
        "competition_key": competition_key,
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "disclaimer": _DISCLAIMER,
        "sample_size": {
            "evaluations": len(evaluations),
            "settled": agent_baseline.settled,
            "pending": agent_baseline.pending,
        },
        "confidence_bucket_analysis": confidence_analysis,
        "recommendation_analysis": recommendation_analysis,
        "market_analysis": market_analysis,
        "agent_analysis": agent_analysis,
        "calibration_audit": calibration_rows,
        "recommendation_quality_audit": {
            "strongest_category": strongest_rec,
            "official_vs_caution": {
                "official": rec_stats["Official Picks"].to_dict(),
                "caution": rec_stats["Caution Picks"].to_dict(),
            },
            "safe_value_aggressive": {
                "safe": rec_stats["Safe Pick"].to_dict(),
                "value": rec_stats["Value Pick"].to_dict(),
                "aggressive": rec_stats["Aggressive Pick"].to_dict(),
            },
        },
        "best_markets": best_markets,
        "worst_markets": worst_markets,
        "best_confidence_buckets": best_buckets,
        "worst_confidence_buckets": worst_buckets,
        "top_agents": [a for a in agent_analysis if a.get("winrate") is not None][:5],
        "weakest_agents": sorted(
            [a for a in agent_analysis if a.get("winrate") is not None],
            key=lambda x: x.get("winrate") or 0,
        )[:5],
        "improvement_suggestions": suggestions,
        "insights": insights,
    }


def _build_suggestions(
    confidence: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    calibration: list[dict[str, Any]],
) -> list[str]:
    out: list[str] = []
    for row in calibration:
        if row.get("assessment") == "overconfident" and row.get("settled", 0) >= 3:
            out.append(
                f"Bucket {row['label']} is overconfident — consider tighter display or weight review "
                f"(gap {row.get('calibration_gap'):+.1%})."
            )
        elif row.get("assessment") == "underconfident" and row.get("settled", 0) >= 3:
            out.append(f"Bucket {row['label']} is underconfident — strong signal may be under-weighted.")

    for m in markets:
        if m.get("settled", 0) >= 3 and (m.get("winrate") or 0) >= 0.65:
            out.append(f"Prioritize {m['label']} market in recommendations (winrate {m['winrate']:.1%}).")
        elif m.get("settled", 0) >= 3 and (m.get("winrate") or 0) <= 0.4:
            out.append(f"Reduce emphasis on {m['label']} until sample improves (winrate {m['winrate']:.1%}).")

    if recommendations:
        top = recommendations[0]
        if top.get("settled", 0) >= 2:
            out.append(f"Strongest recommendation type so far: {top['label']} ({top.get('winrate', 0):.1%}).")

    for a in agents:
        c = a.get("contribution_vs_baseline")
        if c is not None and a.get("settled", 0) >= 3 and c >= 0.1:
            out.append(f"Increase advisory weight for {a['label']} (+{c:.1%} vs baseline).")
        elif c is not None and a.get("settled", 0) >= 3 and c <= -0.1:
            out.append(f"Review {a['label']} — underperforming baseline by {abs(c):.1%}.")

    return out[:12]


def _build_insights(
    confidence: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    calibration: list[dict[str, Any]],
) -> dict[str, Any]:
    conf_correlates = None
    settled_buckets = [b for b in confidence if b.get("settled", 0) >= 2]
    if len(settled_buckets) >= 2:
        high = [b for b in settled_buckets if b["label"] in {"70-75", "75-80", "80+"}]
        low = [b for b in settled_buckets if b["label"] in {"0-50", "50-55", "55-60"}]
        if high and low:
            hw = sum(b.get("winrate") or 0 for b in high) / len(high)
            lw = sum(b.get("winrate") or 0 for b in low) / len(low)
            conf_correlates = hw > lw

    return {
        "confidence_correlates_with_reality": conf_correlates,
        "best_market": markets[0]["label"] if markets else None,
        "strongest_recommendation": recommendations[0]["label"] if recommendations else None,
        "top_agent": agents[0]["label"] if agents else None,
        "overconfident_buckets": [c["label"] for c in calibration if c.get("assessment") == "overconfident"],
        "underconfident_buckets": [c["label"] for c in calibration if c.get("assessment") == "underconfident"],
    }


def generate_and_store_optimization_report_v2(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    settings = settings or get_settings()
    report = build_accuracy_optimization_report(settings=settings, competition_key=competition_key)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    report_id = repo.insert_learning_report(
        competition_key=competition_key,
        report_type="advisory_v2",
        payload=report,
    )
    report["report_id"] = report_id
    return report
