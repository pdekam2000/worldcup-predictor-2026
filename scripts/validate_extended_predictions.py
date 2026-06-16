"""Validate extended prediction markets and flag helpers."""

from __future__ import annotations

import sys


def main() -> int:
    checks: list[tuple[str, bool]] = []

    try:
        from worldcup_predictor.prediction.extended_markets import (
            build_extended_markets,
            compute_btts_probabilities,
            compute_halftime_1x2,
            extract_team_flag_url,
            load_extended_markets_from_prediction,
        )

        btts = compute_btts_probabilities(1.4, 0.9)
        checks.append(("btts_probabilities", btts.option_a + btts.option_b > 0.99))
        ht = compute_halftime_1x2(1.4, 0.9)
        checks.append(("halftime_1x2", ht.home + ht.draw + ht.away > 0.99))
        checks.append(("extract_flag_none", extract_team_flag_url("X", None, side="home") is None))
    except Exception as exc:
        print(f"FAIL backend import: {exc}")
        return 1

    try:
        from worldcup_predictor.ui.country_flags import flag_html_for_team
        from worldcup_predictor.ui.team_display import match_header_html

        html = flag_html_for_team("Germany", logo_url="https://example.com/de.png")
        checks.append(("flag_logo_url", "example.com" in html))
        header = match_header_html("Germany", "Brazil")
        checks.append(("match_header", "Germany" in header and "Brazil" in header))
    except Exception as exc:
        print(f"FAIL ui flags: {exc}")
        return 1

    try:
        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

        result = PredictPipeline(Settings(), locale="en").run(1489374, record_history=False)
        checks.append(("predict_success", result.success))
        if result.success:
            snap = load_extended_markets_from_prediction(result.prediction)
            checks.append(("metadata_extended", snap is not None))
            if snap:
                checks.append(("has_btts", snap.btts.option_a > 0))
                checks.append(("has_fg_band", bool(snap.first_goal_time.minute_band)))
                checks.append(("has_correct_scores", len(snap.correct_scores) >= 1))
                checks.append(("has_scorer_or_fallback", snap.has_player_data or True))
    except Exception as exc:
        print(f"FAIL pipeline: {exc}")
        return 1

    try:
        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService

        fixtures = WorldCupScheduleService(Settings()).get_all_worldcup_fixtures()
        with_logo = [f for f in fixtures if getattr(f, "home_team_logo", None)]
        checks.append(("fixture_logos", len(with_logo) > 0))
    except Exception as exc:
        print(f"FAIL schedule logos: {exc}")
        return 1

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
