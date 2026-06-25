"""Phase 42B-FIX config hardening — centralized consistency guard thresholds."""

from __future__ import annotations

import re
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 42B-FIX config hardening: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _base_payload(**overrides) -> dict:
    payload = {
        "status": "ok",
        "fixture_id": 900001,
        "home_team": "Germany",
        "away_team": "Ivory Coast",
        "prediction": "home",
        "confidence": 68.0,
        "detailed_markets": {
            "match_winner": {
                "selection": "home_win",
                "probabilities": {"home_win": 62.0, "draw": 22.0, "away_win": 16.0},
            },
            "over_under_25": {
                "selection": "under_2_5",
                "probability": 0.55,
                "probabilities": {"over_2_5": 45.0, "under_2_5": 55.0},
            },
            "btts": {
                "selection": "no",
                "probability": 0.817,
                "probabilities": {"yes": 18.3, "no": 81.7},
            },
            "first_goal": {
                "team": "Ivory Coast",
                "minute_range": "16-30",
                "expected_minute": 24,
            },
            "goalscorer": {
                "available": True,
                "player": "Sebastien Haller",
                "team": "Ivory Coast",
                "confidence": 0.42,
            },
            "double_chance": {
                "home_or_draw": 84.0,
                "home_or_away": 78.0,
                "draw_or_away": 38.0,
            },
            "correct_scores": [{"label": "1-0", "probability": 18.0}],
        },
        "recommended_bets": [
            {
                "market_key": "goalscorer",
                "market": "Goalscorer",
                "pick": "Sebastien Haller",
                "status": "recommended",
            }
        ],
        "sportmonks_xg": {"available": True, "home_xg": 1.65, "away_xg": 0.22},
    }
    payload.update(overrides)
    return payload


def _guard_has_no_rule_threshold_literals(guard_src: str) -> tuple[bool, str]:
    """Rule thresholds must live in config, not inline in guard comparisons."""
    forbidden = [
        r">=\s*0\.70\b",
        r"<\s*0\.35\b",
        r"<\s*0\.72\b",
        r">=\s*0\.25\b",
        r"\*\s*0\.45\b",
        r"max\(0\.05",
        r"<=\s*35\b",
    ]
    hits: list[str] = []
    for pattern in forbidden:
        if re.search(pattern, guard_src):
            hits.append(pattern)
    if hits:
        return False, ", ".join(hits)
    return True, "no inline rule thresholds"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    config_path = root / "worldcup_predictor/prediction/market_consistency_config.py"
    guard_path = root / "worldcup_predictor/prediction/market_consistency_guard.py"

    record("config_module_exists", config_path.is_file())
    guard_src = guard_path.read_text(encoding="utf-8")
    record("guard_imports_config", "market_consistency_config" in guard_src)

    from worldcup_predictor.prediction import market_consistency_config as cfg
    from worldcup_predictor.prediction.market_consistency_guard import apply_market_consistency_guard

    record("config_btts_no_default", cfg.CONSISTENCY_BTTS_NO_THRESHOLD == 0.70)
    record("config_btts_yes_default", cfg.CONSISTENCY_BTTS_YES_THRESHOLD == 0.70)
    record("config_under25_default", cfg.CONSISTENCY_UNDER25_THRESHOLD == 0.70)
    record("config_under15_default", cfg.CONSISTENCY_UNDER15_THRESHOLD == 0.70)
    record(
        "config_low_team_scoring_default",
        cfg.CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD == 0.35,
    )
    record(
        "config_strong_goalscorer_confidence_default",
        cfg.CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE == 0.72,
    )
    record(
        "config_clean_sheet_score_prob_default",
        cfg.CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD == 0.25,
    )

    ok_literals, literal_detail = _guard_has_no_rule_threshold_literals(guard_src)
    record("guard_no_inline_rule_thresholds", ok_literals, literal_detail)

    thresholds = cfg.get_consistency_thresholds()
    record("get_consistency_thresholds", isinstance(thresholds, dict) and "btts_no_threshold" in thresholds)

    # Behavioral parity — BTTS No + low-xG goalscorer withheld
    out1 = apply_market_consistency_guard(_base_payload())
    gs1 = out1["detailed_markets"]["goalscorer"]
    record(
        "btts_no_goalscorer_still_withheld",
        gs1.get("display_allowed") is False,
        f"status={gs1.get('consistency_status')}",
    )

    # Under 2.5 high + aggressive timing withheld
    p5 = _base_payload()
    p5["detailed_markets"]["over_under_25"] = {
        "selection": "under_2_5",
        "probability": 0.82,
        "probabilities": {"over_2_5": 18.0, "under_2_5": 82.0},
    }
    p5["detailed_markets"]["first_goal"] = {
        "team": "Germany",
        "minute_range": "16-30",
        "expected_minute": 22,
    }
    p5["detailed_markets"]["goalscorer"] = {"available": False}
    out5 = apply_market_consistency_guard(p5)
    fg5 = out5["detailed_markets"]["first_goal"]
    record(
        "under25_timing_still_withheld",
        fg5.get("display_allowed") is False,
        f"status={fg5.get('consistency_status')}",
    )

    # Consistent payload unchanged display
    p6 = _base_payload()
    p6["detailed_markets"]["btts"] = {
        "selection": "yes",
        "probability": 0.58,
        "probabilities": {"yes": 58.0, "no": 42.0},
    }
    p6["detailed_markets"]["goalscorer"] = {
        "available": True,
        "player": "Kai Havertz",
        "team": "Germany",
        "confidence": 0.78,
    }
    p6["detailed_markets"]["first_goal"] = {
        "team": "Germany",
        "minute_range": "46-60",
        "expected_minute": 52,
    }
    out6 = apply_market_consistency_guard(p6)
    gs6 = out6["detailed_markets"]["goalscorer"]
    record(
        "consistent_payload_unchanged",
        gs6.get("display_allowed") is True and len(out6["consistency_guard"]["withheld_markets"]) == 0,
    )

    record(
        "guard_exports_thresholds_in_audit",
        "thresholds" in out1.get("consistency_guard", {}),
    )

    # Optional env override sanity (does not mutate module for other tests if re-imported)
    import os
    import importlib

    prev = os.environ.get("WCP_CONSISTENCY_BTTS_NO_THRESHOLD")
    os.environ["WCP_CONSISTENCY_BTTS_NO_THRESHOLD"] = "0.99"
    importlib.reload(cfg)
    record(
        "env_override_supported",
        cfg.CONSISTENCY_BTTS_NO_THRESHOLD == 0.99,
        f"value={cfg.CONSISTENCY_BTTS_NO_THRESHOLD}",
    )
    if prev is None:
        os.environ.pop("WCP_CONSISTENCY_BTTS_NO_THRESHOLD", None)
    else:
        os.environ["WCP_CONSISTENCY_BTTS_NO_THRESHOLD"] = prev
    importlib.reload(cfg)

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
