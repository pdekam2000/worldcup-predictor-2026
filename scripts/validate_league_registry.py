from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import sys

EXPECTED = {
    39: "premier_league",
    140: "la_liga",
    78: "bundesliga",
    135: "serie_a",
    61: "ligue_1",
    2: "champions_league",
    3: "europa_league",
    848: "conference_league",
}


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.config.competitions import get_competition
        from worldcup_predictor.config.league_registry import (
            EUROPEAN_LEAGUE_KEYS,
            LEARNING_PROFILE_KEYS,
            list_enabled_european_leagues,
            resolve_competition_by_league_id,
        )

        for league_id, key in EXPECTED.items():
            comp = resolve_competition_by_league_id(league_id)
            checks.append((f"league_{league_id}_registered", comp is not None and comp.key == key))
            if comp:
                checks.append((f"{key}_enabled", comp.enabled))
                checks.append((f"{key}_has_country", bool(comp.country)))
                checks.append((f"{key}_has_seasons", len(comp.default_seasons) >= 3))
                checks.append((f"{key}_learning_profile", comp.learning_profile_key == key))

        checks.append(("european_keys_count", len(EUROPEAN_LEAGUE_KEYS) == 8))
        checks.append(("conference_in_registry", "conference_league" in EUROPEAN_LEAGUE_KEYS))
        checks.append(("world_cup_separate", get_competition("world_cup_2026").learning_profile_key == "world_cup"))
        checks.append(("learning_profiles", len(LEARNING_PROFILE_KEYS) == 9))
        enabled = list_enabled_european_leagues()
        checks.append(("enabled_european", len(enabled) == 8))
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
