from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import sys
import tempfile
from pathlib import Path


def _temp_repo():
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    path = Path(tempfile.mkstemp(suffix=".db")[1])
    return FootballIntelligenceRepository(str(path)), path


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.config.league_registry import LEARNING_PROFILE_KEYS, learning_profile_for
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.odds.league_learning import MARKET_LABELS, LeagueLearningEngine
        from worldcup_predictor.odds.models import LeagueLearningProfile

        checks.append(("nine_profiles", len(LEARNING_PROFILE_KEYS) == 9))
        checks.append(("world_cup_profile", learning_profile_for("world_cup_2026") == "world_cup"))
        checks.append(("pl_profile", learning_profile_for("premier_league") == "premier_league"))
        checks.append(("btts_market_label", "btts" in MARKET_LABELS))
        checks.append(("goalscorer_label", "goalscorer" in MARKET_LABELS))

        repo, _db_path = _temp_repo()
        engine = LeagueLearningEngine(repo)
        profiles = engine.build_all_profiles()
        checks.append(("build_all_profiles", len(profiles) == 9))
        wc = next(p for p in profiles if p.learning_profile_key == "world_cup")
        pl = next(p for p in profiles if p.learning_profile_key == "premier_league")
        checks.append(("profiles_separate", wc.competition_key != pl.competition_key))
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(LeagueLearningProfile)}
        checks.append(("profile_has_learning_key", "learning_profile_key" in field_names))
        checks.append(("profile_has_last_updated", "last_updated_at" in field_names))
    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
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
