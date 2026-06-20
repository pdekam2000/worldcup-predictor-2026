"""Sportmonks xG intelligence — parse, plan verification, internal comparison (Phase 22D)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

PlanSupport = Literal["full", "partial", "none", "unknown"]
XgSource = Literal["xGFixture", "statistics", "none"]

_XG_PRIMARY_TYPE_ID = 5304
_XG_ON_TARGET_TYPE_ID = 5305
_PROBE_FILENAME = "sportmonks_xg_plan_probe.json"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _expected_rows_from_fixture(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    xg_block = raw.get("xGFixture")
    if isinstance(xg_block, dict):
        nested = xg_block.get("expected") or xg_block.get("data")
        if isinstance(nested, list):
            rows.extend(r for r in nested if isinstance(r, dict))
    elif isinstance(xg_block, list):
        rows.extend(r for r in xg_block if isinstance(r, dict))
    top = raw.get("expected")
    if isinstance(top, list):
        rows.extend(r for r in top if isinstance(r, dict))
    return rows


def _value_from_expected_row(row: dict[str, Any]) -> float | None:
    data = row.get("data")
    if isinstance(data, dict):
        val = _float_or_none(data.get("value"))
        if val is not None:
            return val
    return _float_or_none(row.get("value"))


def _pick_primary_xg(entries: list[tuple[int | None, float]]) -> float | None:
    if not entries:
        return None
    for type_id, val in entries:
        if type_id == _XG_PRIMARY_TYPE_ID:
            return val
    return entries[0][1]


def _statistics_xg_map(raw: dict[str, Any]) -> dict[str, float]:
    """Parse expected-goals from generic statistics include."""
    participants = [p for p in _safe_list(raw.get("participants")) if isinstance(p, dict)]
    statistics = _safe_list(raw.get("statistics"))
    if not statistics:
        return {}

    id_to_side: dict[int, str] = {}
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        meta = participant.get("meta") or {}
        loc = str(meta.get("location") or "").lower()
        if loc not in {"home", "away"}:
            continue
        try:
            pid = int(participant.get("id"))
            id_to_side[pid] = loc
        except (TypeError, ValueError):
            continue

    xg_hints = frozenset({"expected goals", "expected_goals", "xg", "xgoals", "expected goals (xg)"})
    xg: dict[str, float] = {}
    for entry in statistics:
        if not isinstance(entry, dict):
            continue
        type_block = entry.get("type")
        label = ""
        if isinstance(type_block, dict):
            label = str(type_block.get("name") or type_block.get("developer_name") or "").lower()
        if not any(h in label for h in xg_hints):
            continue
        data = entry.get("data")
        val = _float_or_none(data.get("value") if isinstance(data, dict) else entry.get("value"))
        if val is None:
            continue
        try:
            participant_id = int(entry.get("participant_id"))
        except (TypeError, ValueError):
            continue
        side = id_to_side.get(participant_id)
        if side:
            xg[side] = val
    return xg


def verify_xg_plan_access(raw: dict[str, Any] | None) -> dict[str, Any]:
    """
    Infer Sportmonks xG plan support from fixture payload shape.

    full — xGFixture expected rows with values
    partial — include requested but empty / statistics-only xG
    none — no xG fields at all
    unknown — no payload
    """
    if not raw:
        return {
            "plan_support": "unknown",
            "xGFixture_requested": True,
            "xGFixture_present": False,
            "expected_row_count": 0,
            "statistics_xg_present": False,
            "message": "No Sportmonks fixture payload available.",
        }

    expected_rows = _expected_rows_from_fixture(raw)
    values = [_value_from_expected_row(r) for r in expected_rows]
    has_values = any(v is not None for v in values)
    stats_xg = _statistics_xg_map(raw)
    has_stats_xg = bool(stats_xg)

    xg_fixture_key = raw.get("xGFixture") is not None or bool(expected_rows)

    if has_values:
        support: PlanSupport = "full"
        message = "xGFixture include returned team xG values — xG add-on likely active."
    elif xg_fixture_key or expected_rows:
        support = "partial"
        message = "xGFixture include present but empty — plan may be Basic-only or pre-match window."
    elif has_stats_xg:
        support = "partial"
        message = "Only in-match statistics xG available — dedicated xGFixture add-on may be missing."
    else:
        support = "none"
        message = "No Sportmonks xG data in payload — verify xG add-on for league 732."

    return {
        "plan_support": support,
        "xGFixture_requested": True,
        "xGFixture_present": xg_fixture_key,
        "expected_row_count": len(expected_rows),
        "expected_value_count": sum(1 for v in values if v is not None),
        "statistics_xg_present": has_stats_xg,
        "message": message,
    }


def load_xg_plan_probe(cache_dir: Path | str) -> dict[str, Any] | None:
    path = Path(cache_dir) / _PROBE_FILENAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_xg_plan_probe(cache_dir: Path | str, result: dict[str, Any]) -> None:
    path = Path(cache_dir) / _PROBE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_sportmonks_xg_from_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize Sportmonks xG sources from a fixture object."""
    plan = verify_xg_plan_access(raw)
    expected_rows = _expected_rows_from_fixture(raw)

    by_location: dict[str, list[tuple[int | None, float]]] = {"home": [], "away": []}
    xg_on_target: dict[str, float | None] = {"home": None, "away": None}

    for row in expected_rows:
        loc = str(row.get("location") or "").lower()
        if loc not in by_location:
            continue
        val = _value_from_expected_row(row)
        if val is None:
            continue
        type_id = row.get("type_id")
        try:
            tid = int(type_id) if type_id is not None else None
        except (TypeError, ValueError):
            tid = None
        by_location[loc].append((tid, val))
        if tid == _XG_ON_TARGET_TYPE_ID:
            xg_on_target[loc] = val

    home_xg = _pick_primary_xg(by_location["home"])
    away_xg = _pick_primary_xg(by_location["away"])

    stats_xg = _statistics_xg_map(raw)
    source: XgSource = "none"
    if home_xg is not None or away_xg is not None:
        source = "xGFixture"
    elif stats_xg:
        source = "statistics"
        home_xg = stats_xg.get("home")
        away_xg = stats_xg.get("away")

    return {
        "available": home_xg is not None or away_xg is not None,
        "source": source,
        "home_xg": home_xg,
        "away_xg": away_xg,
        "xg_on_target_home": xg_on_target.get("home"),
        "xg_on_target_away": xg_on_target.get("away"),
        "statistics_xg": stats_xg,
        "expected_rows": len(expected_rows),
        "plan_access": plan,
        "raw_xg_fixture_present": raw.get("xGFixture") is not None,
    }


def _rating_from_xg(xg: float | None, *, defensive: bool = False) -> float | None:
    if xg is None:
        return None
    if defensive:
        return round(_clamp((2.2 - xg) / 2.2 * 100.0, 0, 100), 1)
    return round(_clamp(xg / 2.5 * 100.0, 0, 100), 1)


def _rolling_xg_from_team_stats(stats: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Internal-style rolling xG from API-Football team expected-goals blocks."""
    if not stats:
        return None, None
    goals = stats.get("goals") or {}
    if not isinstance(goals, dict):
        return None, None
    for_block = goals.get("for") or {}
    against_block = goals.get("against") or {}
    xg_for = None
    xg_against = None
    if isinstance(for_block, dict):
        expected = for_block.get("expected") or {}
        if isinstance(expected, dict):
            xg_for = _float_or_none(expected.get("total") or expected.get("average"))
    if isinstance(against_block, dict):
        expected = against_block.get("expected") or {}
        if isinstance(expected, dict):
            xg_against = _float_or_none(expected.get("total") or expected.get("average"))
    return xg_for, xg_against


def _internal_xg_reference(report: MatchIntelligenceReport) -> dict[str, Any]:
    from worldcup_predictor.chance_quality.stat_extraction import extract_real_xg

    home_stats = report.home_team.statistics or {}
    away_stats = report.away_team.statistics or {}
    home_xg, home_src = extract_real_xg(report, side="home", team_stats=home_stats)
    away_xg, away_src = extract_real_xg(report, side="away", team_stats=away_stats)

    rolling_home_for, rolling_home_against = _rolling_xg_from_team_stats(home_stats)
    rolling_away_for, rolling_away_against = _rolling_xg_from_team_stats(away_stats)

    return {
        "available": home_xg is not None or away_xg is not None,
        "home_xg": home_xg,
        "away_xg": away_xg,
        "source": home_src or away_src or "none",
        "rolling_xg_for_home": rolling_home_for,
        "rolling_xg_against_home": rolling_home_against,
        "rolling_xg_for_away": rolling_away_for,
        "rolling_xg_against_away": rolling_away_against,
    }


def _xg_form_momentum(rolling_for: float | None, rolling_against: float | None) -> tuple[float | None, float | None]:
    if rolling_for is None and rolling_against is None:
        return None, None
    form = None
    if rolling_for is not None and rolling_against is not None:
        form = round(rolling_for - rolling_against, 2)
    momentum = round((rolling_for or 0) - (rolling_against or 0), 2) if rolling_for is not None else None
    return form, momentum


def _compare_xg(
    sm_home: float | None,
    sm_away: float | None,
    internal: dict[str, Any],
) -> dict[str, Any]:
    ih = internal.get("home_xg")
    ia = internal.get("away_xg")
    if sm_home is None and sm_away is None:
        return {
            "agreement_score": 50.0,
            "disagreement_score": 0.0,
            "xg_supports_internal": False,
            "available": False,
        }
    if ih is None and ia is None:
        return {
            "agreement_score": 50.0,
            "disagreement_score": 0.0,
            "xg_supports_internal": False,
            "available": False,
        }

    diffs: list[float] = []
    if sm_home is not None and ih is not None:
        diffs.append(abs(sm_home - ih))
    if sm_away is not None and ia is not None:
        diffs.append(abs(sm_away - ia))
    avg_diff = sum(diffs) / len(diffs) if diffs else 0.0
    disagreement = round(_clamp(avg_diff / 1.5, 0, 1), 3)
    agreement = round((1.0 - disagreement) * 100.0, 1)

    sm_total = (sm_home or 0) + (sm_away or 0)
    in_total = (ih or 0) + (ia or 0)
    supports = abs(sm_total - in_total) <= 0.45 and disagreement < 0.35

    return {
        "agreement_score": agreement,
        "disagreement_score": disagreement,
        "xg_supports_internal": supports,
        "available": True,
        "internal_home_xg": ih,
        "internal_away_xg": ia,
        "internal_total_xg": round(in_total, 2) if ih is not None or ia is not None else None,
        "sportmonks_total_xg": round(sm_total, 2) if sm_home is not None or sm_away is not None else None,
    }


@dataclass
class SportmonksXGIntelligenceResult:
    home_xg: float | None = None
    away_xg: float | None = None
    xg_difference: float | None = None
    xg_total: float | None = None
    xg_attack_rating_home: float | None = None
    xg_attack_rating_away: float | None = None
    xg_defense_rating_home: float | None = None
    xg_defense_rating_away: float | None = None
    xg_strength_rating: float | None = None
    xg_confidence: float = 0.0
    rolling_xg_for_home: float | None = None
    rolling_xg_for_away: float | None = None
    rolling_xg_against_home: float | None = None
    rolling_xg_against_away: float | None = None
    xg_form_home: float | None = None
    xg_form_away: float | None = None
    xg_momentum_home: float | None = None
    xg_momentum_away: float | None = None
    expected_goal_range: str | None = None
    agreement_score: float = 50.0
    disagreement_score: float = 0.0
    xg_supports_internal: bool = False
    xg_source: str = "none"
    plan_support: PlanSupport = "unknown"
    plan_access_message: str = ""
    internal_xg_source: str = "none"
    comparison_available: bool = False
    notes: list[str] = field(default_factory=list)
    version: str = "22d"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_sportmonks_xg_intelligence(
    *,
    xg_block: dict[str, Any] | None,
    report: MatchIntelligenceReport,
    xg_chance_quality_signal: dict[str, Any] | None = None,
) -> SportmonksXGIntelligenceResult:
    """Build Sportmonks xG benchmark layer — no prediction weight changes."""
    block = xg_block or {}
    sm_home = _float_or_none(block.get("home_xg"))
    sm_away = _float_or_none(block.get("away_xg"))
    source = str(block.get("source") or "none")
    plan = block.get("plan_access") or {}
    plan_support: PlanSupport = plan.get("plan_support") or "unknown"

    internal = _internal_xg_reference(report)
    if xg_chance_quality_signal:
        v2_home = (xg_chance_quality_signal.get("home") or {}).get("xg_per_match")
        v2_away = (xg_chance_quality_signal.get("away") or {}).get("xg_per_match")
        if internal.get("home_xg") is None and v2_home is not None:
            internal["home_xg"] = _float_or_none(v2_home)
        if internal.get("away_xg") is None and v2_away is not None:
            internal["away_xg"] = _float_or_none(v2_away)
        if internal.get("home_xg") or internal.get("away_xg"):
            internal["available"] = True
            internal["source"] = internal.get("source") or "xg_chance_quality_v2"

    comparison = _compare_xg(sm_home, sm_away, internal)

    xg_diff = None
    xg_total = None
    if sm_home is not None or sm_away is not None:
        h = sm_home or 0.0
        a = sm_away or 0.0
        xg_diff = round(h - a, 2)
        xg_total = round(h + a, 2)

    atk_home = _rating_from_xg(sm_home, defensive=False)
    atk_away = _rating_from_xg(sm_away, defensive=False)
    def_home = _rating_from_xg(sm_away, defensive=True)
    def_away = _rating_from_xg(sm_home, defensive=True)

    strength_vals = [v for v in (atk_home, atk_away, def_home, def_away) if v is not None]
    strength = round(sum(strength_vals) / len(strength_vals), 1) if strength_vals else None

    roll_hf, roll_ha = internal.get("rolling_xg_for_home"), internal.get("rolling_xg_against_home")
    roll_af, roll_aa = internal.get("rolling_xg_for_away"), internal.get("rolling_xg_against_away")
    form_h, mom_h = _xg_form_momentum(roll_hf, roll_ha)
    form_a, mom_a = _xg_form_momentum(roll_af, roll_aa)

    expected_range: str | None = None
    if xg_total is not None:
        low = max(0.5, xg_total - 0.6)
        high = xg_total + 0.8
        expected_range = f"{low:.1f}-{high:.1f}"

    confidence = 0.0
    if source == "xGFixture":
        confidence = 85.0 if plan_support == "full" else 55.0
    elif source == "statistics":
        confidence = 45.0
    if comparison.get("available"):
        confidence = min(100.0, confidence + 10.0)

    notes: list[str] = []
    if not block.get("available"):
        notes.append("Sportmonks xG unavailable — await cache refresh or xG add-on for WC league 732.")
    else:
        notes.append(f"Sportmonks xG loaded via {source} (benchmark only).")
    notes.append(str(plan.get("message") or ""))
    if comparison.get("available") and not comparison.get("xg_supports_internal"):
        notes.append("Sportmonks xG diverges from internal xG — trace-only, no weight change.")
    notes = [n for n in notes if n]

    return SportmonksXGIntelligenceResult(
        home_xg=sm_home,
        away_xg=sm_away,
        xg_difference=xg_diff,
        xg_total=xg_total,
        xg_attack_rating_home=atk_home,
        xg_attack_rating_away=atk_away,
        xg_defense_rating_home=def_home,
        xg_defense_rating_away=def_away,
        xg_strength_rating=strength,
        xg_confidence=round(confidence, 1),
        rolling_xg_for_home=roll_hf,
        rolling_xg_for_away=roll_af,
        rolling_xg_against_home=roll_ha,
        rolling_xg_against_away=roll_aa,
        xg_form_home=form_h,
        xg_form_away=form_a,
        xg_momentum_home=mom_h,
        xg_momentum_away=mom_a,
        expected_goal_range=expected_range,
        agreement_score=comparison.get("agreement_score", 50.0),
        disagreement_score=comparison.get("disagreement_score", 0.0),
        xg_supports_internal=bool(comparison.get("xg_supports_internal")),
        xg_source=source,
        plan_support=plan_support,
        plan_access_message=str(plan.get("message") or ""),
        internal_xg_source=str(internal.get("source") or "none"),
        comparison_available=bool(comparison.get("available")),
        notes=notes,
    )
