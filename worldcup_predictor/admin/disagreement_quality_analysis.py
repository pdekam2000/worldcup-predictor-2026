"""Phase 59E — Shadow vs production disagreement quality analysis (admin-only)."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.admin.elite_shadow_comparison import EliteShadowComparisonService
from worldcup_predictor.admin.elite_shadow_preview import ROOT as PROJECT_ROOT

AdminLabel = Literal["SHADOW_LEAN", "PRODUCTION_LEAN", "NO_BET", "NEEDS_RESULT_DATA"]

ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "phase59e_disagreement_quality"
ROOT_CAUSE_PATTERNS = PROJECT_ROOT / "data" / "shadow" / "root_cause_store" / "failure_patterns.json"
ROOT_CAUSE_BLAME = PROJECT_ROOT / "data" / "shadow" / "root_cause_store" / "component_blame_matrix.json"

SHADOW_WEAK_MARKETS = frozenset({"anytime_goalscorer", "first_goalscorer"})
HIGH_VALUE_SHADOW_TIERS = frozenset({"A", "B"})
RISKY_SHADOW_TIERS = frozenset({"C", "D"})
PROD_HIGH = 0.65
PROD_LOW = 0.45
COMPONENT_STRONG = 0.75
COMPONENT_WEAK = 0.45

_HOME_ALIASES = frozenset({"home", "home_win", "1", "h"})
_AWAY_ALIASES = frozenset({"away", "away_win", "2", "a"})
_DRAW_ALIASES = frozenset({"draw", "x", "d"})


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _team_tokens(name: str) -> set[str]:
    parts = {p for p in _norm_text(name).split() if len(p) > 2}
    return parts


def semantic_pick(pick: str | None, fixture: dict[str, Any]) -> str | None:
    """Map raw picks to home / away / draw / timing token for fair comparison."""
    if pick is None:
        return None
    token = _norm_text(pick)
    if not token:
        return None
    if token in _HOME_ALIASES:
        return "home"
    if token in _AWAY_ALIASES:
        return "away"
    if token in _DRAW_ALIASES:
        return "draw"

    home = _norm_text(fixture.get("home_team"))
    away = _norm_text(fixture.get("away_team"))
    home_parts = _team_tokens(home)
    away_parts = _team_tokens(away)

    if token == home or (home and home in token) or (home_parts and home_parts <= set(token.split())):
        return "home"
    if token == away or (away and away in token) or (away_parts and away_parts <= set(token.split())):
        return "away"
    if home_parts and token in home_parts:
        return "home"
    if away_parts and token in away_parts:
        return "away"
    return token


def production_confidence_bucket(conf: float | None) -> str:
    if conf is None:
        return "missing"
    if conf >= PROD_HIGH:
        return "high"
    if conf >= PROD_LOW:
        return "medium"
    return "low"


def component_agreement_score(contributions: list[dict[str, Any]]) -> float:
    active = [c for c in contributions if c.get("prediction") is not None]
    if not active:
        return 0.0
    counts = Counter(_norm_text(c.get("prediction")) for c in active)
    top = counts.most_common(1)[0][1]
    return round(top / len(active), 4)


def component_pattern(contributions: list[dict[str, Any]]) -> str:
    if not contributions:
        return "no_components"
    active = [c for c in contributions if c.get("prediction") is not None]
    if not active:
        return "no_active_predictions"
    preds = {_norm_text(c.get("prediction")) for c in active}
    if len(preds) == 1:
        return "unanimous"
    if len(preds) > 1:
        return "conflicting"
    return "sparse"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _historical_shadow_risk() -> dict[str, Any]:
    patterns = _load_json(ROOT_CAUSE_PATTERNS)
    top = patterns.get("top_patterns") or []
    tier_a_rate = 0.0
    high_conf_rate = 0.0
    for item in top:
        if item.get("pattern") == "tier_a_failures":
            tier_a_rate = float(item.get("rate") or 0)
        if item.get("pattern") == "high_confidence_miss":
            high_conf_rate = float(item.get("rate") or 0)
    return {
        "tier_a_failure_rate": tier_a_rate,
        "high_confidence_miss_rate": high_conf_rate,
        "total_incorrect_historical": int(patterns.get("total_incorrect") or 0),
    }


def _component_hurt_rates(market_id: str) -> dict[str, float]:
    blame = _load_json(ROOT_CAUSE_BLAME)
    hurt: dict[str, list[float]] = defaultdict(list)
    for segment, components in (blame.get("by_segment") or {}).items():
        if f"market={market_id}" not in segment:
            continue
        if not isinstance(components, dict):
            continue
        for cid, stats in components.items():
            if isinstance(stats, dict) and stats.get("hurt") is not None:
                hurt[cid].append(float(stats["hurt"]))
    return {cid: round(sum(vals) / len(vals), 4) for cid, vals in hurt.items()}


def _root_cause_supports_shadow(row: dict[str, Any]) -> bool:
    rc = row.get("root_cause")
    if not rc:
        return False
    records = rc if isinstance(rc, list) else [rc]
    shadow_supporting = {
        "odds_disagreement",
        "historical_prior_conflict",
        "missing_information",
    }
    for rec in records:
        reason = str(rec.get("failure_reason") or "")
        if reason in shadow_supporting:
            return True
    return False


def _root_cause_indicates_shadow_weakness(row: dict[str, Any]) -> bool:
    rc = row.get("root_cause")
    if not rc:
        return False
    records = rc if isinstance(rc, list) else [rc]
    weak = {"confidence_overestimation", "lineup_mismatch", "goalscorer_disagreement"}
    for rec in records:
        if str(rec.get("failure_reason") or "") in weak:
            return True
    return False


@dataclass
class AnalyzedRow:
    fixture_id: int
    market_id: str
    home_team: str
    away_team: str
    competition_key: str
    kickoff_utc: str | None
    shadow_pick: str | None
    production_pick: str | None
    semantic_shadow_pick: str | None
    semantic_production_pick: str | None
    raw_disagreement: bool
    true_disagreement: bool
    normalization_artifact: bool
    shadow_tier: str
    shadow_confidence: float | None
    production_confidence: float | None
    production_conf_bucket: str
    component_pattern: str
    component_agreement_score: float
    high_value_flag: bool
    risky_flag: bool
    high_value_reasons: list[str] = field(default_factory=list)
    risky_reasons: list[str] = field(default_factory=list)
    admin_label: AdminLabel = "NEEDS_RESULT_DATA"
    label_reason: str = ""
    evaluation_status: str = "pending"
    match_status: str | None = None

    def to_csv_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market_id": self.market_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition_key": self.competition_key,
            "kickoff_utc": self.kickoff_utc or "",
            "shadow_pick": self.shadow_pick or "",
            "production_pick": self.production_pick or "",
            "semantic_shadow_pick": self.semantic_shadow_pick or "",
            "semantic_production_pick": self.semantic_production_pick or "",
            "raw_disagreement": self.raw_disagreement,
            "true_disagreement": self.true_disagreement,
            "normalization_artifact": self.normalization_artifact,
            "shadow_tier": self.shadow_tier,
            "shadow_confidence": self.shadow_confidence if self.shadow_confidence is not None else "",
            "production_confidence": self.production_confidence if self.production_confidence is not None else "",
            "production_conf_bucket": self.production_conf_bucket,
            "component_pattern": self.component_pattern,
            "component_agreement_score": self.component_agreement_score,
            "high_value_flag": self.high_value_flag,
            "risky_flag": self.risky_flag,
            "high_value_reasons": "; ".join(self.high_value_reasons),
            "risky_reasons": "; ".join(self.risky_reasons),
            "admin_label": self.admin_label,
            "label_reason": self.label_reason,
            "evaluation_status": self.evaluation_status,
            "match_status": self.match_status or "",
        }


def _assign_label(analyzed: AnalyzedRow, *, hist_risk: dict[str, Any]) -> None:
    if analyzed.market_id in SHADOW_WEAK_MARKETS:
        analyzed.admin_label = "NO_BET"
        analyzed.label_reason = "goalscorer_market_non_comparable_or_empty"
        analyzed.risky_flag = True
        analyzed.risky_reasons.append("goalscorer_market")
        return

    if not analyzed.true_disagreement:
        analyzed.admin_label = "NO_BET"
        analyzed.label_reason = "semantic_agreement_or_no_edge"
        return

    shadow_tier = analyzed.shadow_tier.upper()
    prod_bucket = analyzed.production_conf_bucket
    comp_score = analyzed.component_agreement_score
    shadow_conf = analyzed.shadow_confidence or 0.0
    prod_conf = analyzed.production_confidence or 0.0

    if analyzed.evaluation_status != "evaluated":
        pending_gate = True
    else:
        pending_gate = False

    if (
        shadow_tier in HIGH_VALUE_SHADOW_TIERS
        and prod_bucket in ("low", "missing")
        and comp_score >= COMPONENT_STRONG
        and shadow_conf >= PROD_HIGH
    ):
        analyzed.high_value_flag = True
        analyzed.high_value_reasons.append("shadow_tier_ab_strong_components_weak_prod")

    if shadow_tier in HIGH_VALUE_SHADOW_TIERS and prod_bucket == "low" and comp_score >= COMPONENT_STRONG:
        analyzed.high_value_flag = True
        analyzed.high_value_reasons.append("shadow_ab_vs_low_prod_conf")

    if shadow_tier in RISKY_SHADOW_TIERS and prod_bucket == "high":
        analyzed.risky_flag = True
        analyzed.risky_reasons.append("shadow_cd_vs_high_prod")

    if analyzed.component_pattern == "conflicting":
        analyzed.risky_flag = True
        analyzed.risky_reasons.append("shadow_component_conflict")

    if hist_risk.get("tier_a_failure_rate", 0) >= 0.5 and shadow_tier == "A":
        analyzed.risky_flag = True
        analyzed.risky_reasons.append("historical_tier_a_miss_rate_high")

    if analyzed.market_id == "goal_timing" and shadow_conf < 0.4:
        analyzed.risky_flag = True
        analyzed.risky_reasons.append("goal_timing_low_shadow_conf")

    if analyzed.high_value_flag and not analyzed.risky_flag and pending_gate:
        analyzed.admin_label = "SHADOW_LEAN"
        analyzed.label_reason = "shadow_strong_prod_weak_pending_validation"
        return

    if analyzed.risky_flag and prod_bucket == "high" and shadow_tier in RISKY_SHADOW_TIERS:
        analyzed.admin_label = "PRODUCTION_LEAN"
        analyzed.label_reason = "production_high_conf_shadow_weak_tier"
        return

    if prod_conf >= shadow_conf + 0.12 and prod_bucket == "high":
        analyzed.admin_label = "PRODUCTION_LEAN"
        analyzed.label_reason = "production_confidence_materially_higher"
        return

    if shadow_conf >= prod_conf + 0.12 and shadow_tier in HIGH_VALUE_SHADOW_TIERS and comp_score >= COMPONENT_STRONG:
        analyzed.admin_label = "SHADOW_LEAN"
        analyzed.label_reason = "shadow_confidence_and_component_edge"
        return

    if comp_score < COMPONENT_WEAK or analyzed.component_pattern == "conflicting":
        analyzed.admin_label = "NO_BET"
        analyzed.label_reason = "insufficient_shadow_component_consensus"
        return

    if pending_gate:
        analyzed.admin_label = "NEEDS_RESULT_DATA"
        analyzed.label_reason = "true_disagreement_pending_outcome"
        return

    analyzed.admin_label = "NO_BET"
    analyzed.label_reason = "no_clear_admin_edge"


def analyze_comparison_rows(rows: list[dict[str, Any]]) -> tuple[list[AnalyzedRow], dict[str, Any]]:
    hist_risk = _historical_shadow_risk()
    analyzed_rows: list[AnalyzedRow] = []

    for row in rows:
        if not row.get("comparable"):
            continue
        fx = row.get("fixture") or {}
        shadow = row.get("shadow") or {}
        prod = row.get("production") or {}
        contributions = shadow.get("component_contributions") or []

        sp = shadow.get("normalized_pick")
        pp = prod.get("normalized_pick")
        sem_s = semantic_pick(sp, fx)
        sem_p = semantic_pick(pp, fx)
        true_dis = sem_s != sem_p
        raw_dis = bool(row.get("disagreement"))

        ar = AnalyzedRow(
            fixture_id=int(row.get("fixture_id") or 0),
            market_id=str(row.get("market_id") or ""),
            home_team=str(fx.get("home_team") or ""),
            away_team=str(fx.get("away_team") or ""),
            competition_key=str(fx.get("competition_key") or ""),
            kickoff_utc=fx.get("kickoff_utc"),
            shadow_pick=sp,
            production_pick=pp,
            semantic_shadow_pick=sem_s,
            semantic_production_pick=sem_p,
            raw_disagreement=raw_dis,
            true_disagreement=true_dis,
            normalization_artifact=raw_dis and not true_dis,
            shadow_tier=str(shadow.get("tier") or "").upper(),
            shadow_confidence=shadow.get("confidence"),
            production_confidence=prod.get("confidence"),
            production_conf_bucket=production_confidence_bucket(prod.get("confidence")),
            component_pattern=component_pattern(contributions),
            component_agreement_score=component_agreement_score(contributions),
            high_value_flag=False,
            risky_flag=False,
            evaluation_status=str(row.get("evaluation_status") or "pending"),
            match_status=fx.get("match_status"),
        )

        if _root_cause_supports_shadow(row):
            ar.high_value_flag = True
            ar.high_value_reasons.append("root_cause_supports_shadow_side")
        if _root_cause_indicates_shadow_weakness(row):
            ar.risky_flag = True
            ar.risky_reasons.append("root_cause_shadow_weakness")

        hurt = _component_hurt_rates(ar.market_id)
        for c in contributions:
            cid = str(c.get("component_id") or "")
            if hurt.get(cid, 0) >= 0.45:
                ar.risky_flag = True
                ar.risky_reasons.append(f"historical_hurt_{cid}")

        _assign_label(ar, hist_risk=hist_risk)
        analyzed_rows.append(ar)

    summary = _build_summary(analyzed_rows, hist_risk=hist_risk)
    return analyzed_rows, summary


def _build_summary(analyzed: list[AnalyzedRow], *, hist_risk: dict[str, Any]) -> dict[str, Any]:
    label_counts = Counter(r.admin_label for r in analyzed)
    market_disagree = Counter(r.market_id for r in analyzed if r.true_disagreement)
    market_raw_dis = Counter(r.market_id for r in analyzed if r.raw_disagreement)
    market_artifact = Counter(r.market_id for r in analyzed if r.normalization_artifact)
    tier_disagree = Counter(r.shadow_tier for r in analyzed if r.true_disagreement)
    prod_bucket_dis = Counter(r.production_conf_bucket for r in analyzed if r.true_disagreement)

    shadow_favored = [
        r.to_csv_dict()
        for r in sorted(
            [x for x in analyzed if x.admin_label == "SHADOW_LEAN"],
            key=lambda x: float(x.shadow_confidence or 0),
            reverse=True,
        )[:10]
    ]
    prod_favored = [
        r.to_csv_dict()
        for r in sorted(
            [x for x in analyzed if x.admin_label == "PRODUCTION_LEAN"],
            key=lambda x: float(x.production_confidence or 0),
            reverse=True,
        )[:10]
    ]
    no_bet = [r.to_csv_dict() for r in analyzed if r.admin_label == "NO_BET"][:15]
    needs_data = [r.to_csv_dict() for r in analyzed if r.admin_label == "NEEDS_RESULT_DATA"][:15]

    micro_test = _micro_test_readiness(analyzed, hist_risk)

    return {
        "total_rows_analyzed": len(analyzed),
        "comparable_rows": len(analyzed),
        "raw_disagreement_count": sum(1 for r in analyzed if r.raw_disagreement),
        "true_disagreement_count": sum(1 for r in analyzed if r.true_disagreement),
        "normalization_artifact_count": sum(1 for r in analyzed if r.normalization_artifact),
        "same_pick_semantic_count": sum(1 for r in analyzed if not r.true_disagreement),
        "label_counts": dict(label_counts),
        "disagreement_by_market": {
            "raw": dict(market_raw_dis),
            "true": dict(market_disagree),
            "normalization_artifacts": dict(market_artifact),
        },
        "true_disagreement_by_shadow_tier": dict(tier_disagree),
        "true_disagreement_by_production_conf_bucket": dict(prod_bucket_dis),
        "high_value_flag_count": sum(1 for r in analyzed if r.high_value_flag),
        "risky_flag_count": sum(1 for r in analyzed if r.risky_flag),
        "historical_shadow_risk": hist_risk,
        "strongest_shadow_favored": shadow_favored,
        "strongest_production_favored": prod_favored,
        "no_bet_cases_sample": no_bet,
        "needs_result_data_sample": needs_data,
        "risk_warnings": _risk_warnings(analyzed, hist_risk),
        "micro_test_readiness": micro_test,
        "recommendation": micro_test["recommendation"],
    }


def _risk_warnings(analyzed: list[AnalyzedRow], hist_risk: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    artifact_rate = sum(1 for r in analyzed if r.normalization_artifact) / max(len(analyzed), 1)
    if artifact_rate > 0.3:
        warnings.append(
            f"{sum(1 for r in analyzed if r.normalization_artifact)} rows ({artifact_rate:.0%}) are raw disagreements "
            "caused by pick normalization (e.g. away vs away_win, team name vs home/away)."
        )
    if hist_risk.get("tier_a_failure_rate", 0) >= 0.5:
        warnings.append(
            f"Historical shadow Tier A incorrect rate is {hist_risk['tier_a_failure_rate']:.1%} "
            f"({hist_risk.get('total_incorrect_historical', 0)} EGIE replay rows) — do not trust tier alone."
        )
    if all(r.evaluation_status == "pending" for r in analyzed):
        warnings.append("All comparable rows are pending evaluation — no finished-match ground truth for this fixture set.")
    if sum(1 for r in analyzed if r.admin_label == "SHADOW_LEAN") == 0:
        warnings.append("No SHADOW_LEAN labels met conservative thresholds without elevated risk flags.")
    return warnings


def _micro_test_readiness(analyzed: list[AnalyzedRow], hist_risk: dict[str, Any]) -> dict[str, Any]:
    true_dis = [r for r in analyzed if r.true_disagreement]
    shadow_lean = [r for r in analyzed if r.admin_label == "SHADOW_LEAN"]
    prod_lean = [r for r in analyzed if r.admin_label == "PRODUCTION_LEAN"]
    pending = all(r.evaluation_status == "pending" for r in analyzed)

    by_market_true = Counter(r.market_id for r in true_dis)
    ready_markets: list[str] = []
    for market, count in by_market_true.items():
        lean = sum(1 for r in analyzed if r.market_id == market and r.admin_label in ("SHADOW_LEAN", "PRODUCTION_LEAN"))
        risky = sum(1 for r in analyzed if r.market_id == market and r.risky_flag)
        if count >= 3 and lean >= 2 and risky == 0 and not pending:
            ready_markets.append(market)

    if pending:
        rec: str = "NEEDS_RESULT_DATA"
    elif ready_markets:
        rec = "MICRO_TEST_READY"
    elif hist_risk.get("tier_a_failure_rate", 0) >= 0.55 or len(shadow_lean) + len(prod_lean) < 3:
        rec = "NO_BET_RECOMMENDED"
    else:
        rec = "PARTIAL_DATA_READY"  # internal only; map to allowed set below

    if rec == "PARTIAL_DATA_READY":
        rec = "NO_BET_RECOMMENDED"

    return {
        "recommendation": rec,
        "ready_markets": ready_markets,
        "true_disagreement_markets": dict(by_market_true),
        "shadow_lean_count": len(shadow_lean),
        "production_lean_count": len(prod_lean),
        "all_pending": pending,
    }


def run_analysis(*, limit: int = 500) -> tuple[list[AnalyzedRow], dict[str, Any]]:
    comparison = EliteShadowComparisonService().build_comparison(limit=limit)
    rows = comparison.get("rows") or []
    analyzed, summary = analyze_comparison_rows(rows)
    summary["comparison_summary"] = comparison.get("summary") or {}
    return analyzed, summary


def write_artifacts(analyzed: list[AnalyzedRow], summary: dict[str, Any]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = ARTIFACT_DIR / "disagreement_quality_rows.csv"
    json_path = ARTIFACT_DIR / "summary.json"

    if analyzed:
        fieldnames = list(analyzed[0].to_csv_dict().keys())
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in analyzed:
                writer.writerow(row.to_csv_dict())
    else:
        csv_path.write_text("", encoding="utf-8")

    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return ARTIFACT_DIR
