"""Phase 50B validation — real provider, reset, diagnostics."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_compute_credits() -> None:
    from worldcup_predictor.providers.odds_api_credit.config import compute_odds_api_credits

    assert compute_odds_api_credits("eu", "h2h,totals") == 2
    assert compute_odds_api_credits("us,eu", "h2h") == 2


def test_validation_source_reset() -> None:
    db = Path(tempfile.gettempdir()) / f"p50b_{uuid.uuid4().hex}.db"
    os.environ["FOOTBALL_DB_PATH"] = str(db)
    from worldcup_predictor.providers.odds_api_credit import repository as repo_mod

    repo_mod._repo = None
    try:
        repo = repo_mod.get_odds_api_repository()
        for i in range(5):
            repo.record_usage(endpoint="test", fixture_id=i, credits_used=1, source="validation")
        repo.record_usage(endpoint="test", fixture_id=99, credits_used=1, source="live")
        from datetime import date

        day = date.today().isoformat()
        deleted = repo.delete_validation_usage(day)
        assert deleted == 5
        assert repo.sum_credits_for_date(day) == 1
    finally:
        repo_mod._repo = None
        try:
            db.unlink()
        except OSError:
            pass


def test_team_match_fuzzy() -> None:
    from worldcup_predictor.providers.the_odds_api_provider import teams_match

    assert teams_match("Germany", "Germany")
    assert teams_match("USA", "United States")
    assert teams_match("Curacao", "Curaçao")


def test_diagnostics_missing_key() -> None:
    from worldcup_predictor.config.settings import Settings
    from worldcup_predictor.providers.odds_api_diagnostics import run_odds_api_diagnostics

    bare = Settings(THE_ODDS_API_KEY="")
    payload = run_odds_api_diagnostics(1489374, settings=bare, dry_run=True)
    assert payload["key_loaded"] is False


def main() -> int:
    tests = [
        test_compute_credits,
        test_validation_source_reset,
        test_team_match_fuzzy,
        test_diagnostics_missing_key,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nPhase 50B validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
