"""Phase 42B-FIX — global market consistency guard validation."""

from __future__ import annotations

import copy
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 42B-FIX validation: {passed}/{len(checks)} PASS")
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
            "correct_scores": [
                {"label": "1-0", "probability": 18.0},
                {"label": "2-1", "probability": 12.0},
            ],
        },
        "recommended_bets": [
            {
                "market_key": "goalscorer",
                "market": "Goalscorer",
                "pick": "Sebastien Haller",
                "status": "recommended",
            }
        ],
        "aggressive_pick": {
            "market_key": "goalscorer",
            "market": "Goalscorer",
            "pick": "Sebastien Haller",
        },
        "sportmonks_xg": {"available": True, "home_xg": 1.65, "away_xg": 0.22},
    }
    payload.update(overrides)
    return payload


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    record(
        "guard_module_exists",
        (root / "worldcup_predictor/prediction/market_consistency_guard.py").is_file(),
    )

    from worldcup_predictor.prediction.market_consistency_guard import apply_market_consistency_guard

    detail_src = (root / "base44-d/src/pages/PredictionDetail.jsx").read_text(encoding="utf-8")
    record("frontend_respects_display_allowed", "display_allowed" in detail_src)
    record("frontend_withheld_message", "conflicts with stronger model signals" in detail_src)
    record("frontend_withheld_panel", "WithheldMarketPanel" in detail_src)

    scoring_engine = (root / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(
        "scoring_engine_untouched",
        "market_consistency_guard" not in scoring_engine,
    )
    wde = (root / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record("wde_untouched", "market_consistency_guard" not in wde)

    display_helpers = (root / "worldcup_predictor/api/display_helpers.py").read_text(encoding="utf-8")
    record("guard_wired_in_display_helpers", "apply_market_consistency_guard" in display_helpers)

    # 1) BTTS No high + goalscorer from low-scoring team => withheld
    p1 = _base_payload()
    out1 = apply_market_consistency_guard(p1)
    gs1 = out1["detailed_markets"]["goalscorer"]
    record(
        "btts_no_high_goalscorer_withheld",
        gs1.get("display_allowed") is False and "goalscorer" in out1["consistency_guard"]["withheld_markets"],
        f"status={gs1.get('consistency_status')}",
    )

    # 2) BTTS Yes high + 0-0 correct score => withheld
    p2 = _base_payload()
    p2["detailed_markets"]["btts"] = {
        "selection": "yes",
        "probability": 0.78,
        "probabilities": {"yes": 78.0, "no": 22.0},
    }
    p2["detailed_markets"]["correct_scores"] = [{"label": "0-0", "probability": 14.0}]
    p2["detailed_markets"]["goalscorer"] = {"available": False}
    out2 = apply_market_consistency_guard(p2)
    cs2 = out2["detailed_markets"]["correct_scores"][0]
    record(
        "btts_yes_high_clean_sheet_score_withheld",
        cs2.get("display_allowed") is False,
        f"status={cs2.get('consistency_status')}",
    )

    # 3) 1X2 Home + correct score away win => withheld
    p3 = _base_payload()
    p3["detailed_markets"]["correct_scores"] = [{"label": "1-2", "probability": 11.0}]
    p3["detailed_markets"]["goalscorer"] = {"available": False}
    out3 = apply_market_consistency_guard(p3)
    cs3 = out3["detailed_markets"]["correct_scores"][0]
    record(
        "one_x_two_home_correct_score_away_withheld",
        cs3.get("display_allowed") is False,
        cs3.get("withheld_reason", "")[:80],
    )

    # 4) 1X2 Home + Double Chance X2 => withheld pick
    p4 = _base_payload()
    p4["detailed_markets"]["double_chance"] = {
        "home_or_draw": 40.0,
        "home_or_away": 42.0,
        "draw_or_away": 88.0,
    }
    p4["detailed_markets"]["goalscorer"] = {"available": False}
    p4["recommended_bets"] = [
        {"market_key": "double_chance", "market": "Double Chance", "pick": "Draw or Away", "status": "recommended"}
    ]
    out4 = apply_market_consistency_guard(p4)
    dc4 = out4["detailed_markets"]["double_chance"]
    bet4 = out4["recommended_bets"][0]
    record(
        "one_x_two_home_double_chance_x2_flagged",
        dc4.get("consistency_status") in {"warning", "withheld"}
        and bet4.get("display_allowed") is False,
        f"dc={dc4.get('consistency_status')} bet={bet4.get('display_allowed')}",
    )

    # 5) Under 2.5 high + aggressive goal timing => withheld
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
        "under_high_aggressive_timing_withheld",
        fg5.get("display_allowed") is False,
        f"status={fg5.get('consistency_status')}",
    )

    # 6) Consistent payload => unchanged display
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
    p6["detailed_markets"]["correct_scores"] = [{"label": "2-1", "probability": 13.0}]
    out6 = apply_market_consistency_guard(p6)
    gs6 = out6["detailed_markets"]["goalscorer"]
    record(
        "consistent_payload_goalscorer_ok",
        gs6.get("display_allowed") is True and gs6.get("consistency_status") == "ok",
    )
    record(
        "consistent_payload_no_withheld_markets",
        len(out6["consistency_guard"]["withheld_markets"]) == 0,
    )

    # 7) Raw audit preserved
    raw_before = copy.deepcopy(p1["detailed_markets"])
    out7 = apply_market_consistency_guard(p1)
    audit = out7["consistency_guard"]["raw_markets_audit"]
    record(
        "raw_markets_audit_preserved",
        audit.get("goalscorer", {}).get("player") == raw_before["goalscorer"]["player"],
    )
    record(
        "sanitized_differs_from_raw_when_withheld",
        out7["detailed_markets"]["goalscorer"].get("display_allowed") is False
        and audit["goalscorer"].get("display_allowed", True) is not False,
    )

    # 8) enrich_prediction_payload applies guard for users
    from worldcup_predictor.api.display_helpers import enrich_prediction_payload

    enriched_user = enrich_prediction_payload(
        p1,
        competition_key="world_cup_2026",
        season=2026,
        user_id="user-1",
        role="user",
    )
    enriched_admin = enrich_prediction_payload(
        p1,
        competition_key="world_cup_2026",
        season=2026,
        user_id="admin-1",
        role="admin",
    )
    record(
        "user_payload_guard_applied",
        enriched_user.get("consistency_guard", {}).get("applied") is True,
    )
    record(
        "user_payload_strips_raw_audit",
        "raw_markets_audit" not in enriched_user.get("consistency_guard", {}),
    )
    record(
        "admin_payload_keeps_raw_audit",
        "raw_markets_audit" in enriched_admin.get("consistency_guard", {}),
    )

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
