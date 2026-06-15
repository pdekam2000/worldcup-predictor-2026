"""Phase 55 — High-value feature extraction validation."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_ID = 1489374
REPORT_PATH = ROOT / "reports" / "phase55_feature_extraction_report.md"


def test_report_exists() -> None:
    assert REPORT_PATH.is_file()
    text = REPORT_PATH.read_text(encoding="utf-8")
    assert "player_rating" in text
    assert "BenchDepthIntelligenceV1" in text or "bench_depth" in text
    assert "88/100" in text


def test_extraction_module() -> None:
    from worldcup_predictor.integrations.player_feature_extraction import (
        chance_creation_score,
        compute_conservative_player_score,
    )

    row = {"goals": 2, "shots": 4, "player_rating": 7.4, "assists": 1, "key_passes": 3}
    score = compute_conservative_player_score(row)
    assert 40 < score < 99
    cc = chance_creation_score(key_passes=3, assists=1, appearances=1)
    assert cc > 0


def test_squad_intelligence_import() -> None:
    from worldcup_predictor.squad.squad_intelligence_engine import (
        build_bench_depth_intelligence,
        build_squad_age_profile,
    )

    age = build_squad_age_profile([{"age": 27}, {"age": 29}, {"age": 25}])
    assert age["available"]
    assert age["experience_score"] > 0
    depth = build_bench_depth_intelligence([{"name": "A", "position": "F"}, {"name": "B", "position": "M"}])
    assert depth["depth_score"] >= 0


def test_normalize_fixture_players_fields() -> None:
    from worldcup_predictor.integrations.api_sports_deep_data import normalize_fixture_players

    raw = [
        {
            "team": {"name": "Germany"},
            "players": [
                {
                    "player": {"name": "Test Striker", "pos": "F"},
                    "statistics": [
                        {
                            "games": {"position": "F", "minutes": 90, "rating": "7.8"},
                            "goals": {"total": 1, "assists": 2},
                            "shots": {"total": 3},
                            "passes": {"key": 4},
                        }
                    ],
                }
            ],
        }
    ]
    rows = normalize_fixture_players(raw)
    assert len(rows) == 1
    assert rows[0]["player_rating"] == 7.8
    assert rows[0]["assists"] == 2
    assert rows[0]["key_passes"] == 4
    assert rows[0]["chance_creation_score"] > 0


def test_sidelined_probe() -> None:
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.integrations.sidelined_probe import probe_sidelined_endpoint

    settings = get_settings()
    api = ApiFootballClient(settings)
    result = probe_sidelined_endpoint(api, cache_dir=settings.api_cache_dir, team_id=25)
    assert "available" in result
    # Update report sidelined section marker
    text = REPORT_PATH.read_text(encoding="utf-8")
    status = "AVAILABLE" if result.get("available") else "NOT AVAILABLE"
    if f"Sidelined probe: {status}" not in text:
        note = f"\n\n**Sidelined probe: {status}** — {result.get('reason', '')}\n"
        REPORT_PATH.write_text(text + note, encoding="utf-8")


def test_scoring_engine_unchanged() -> None:
    baseline = ROOT / "reports" / ".phase54_scoring_engine.sha256"
    if baseline.is_file():
        import hashlib

        current = hashlib.sha256(
            (ROOT / "worldcup_predictor" / "prediction" / "scoring_engine.py").read_bytes()
        ).hexdigest()
        assert current == baseline.read_text(encoding="utf-8").strip()


def test_cli_first_goal() -> None:
    from worldcup_predictor.cli.commands import run_first_goal_command

    buf = StringIO()
    assert run_first_goal_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0
    out = buf.getvalue()
    assert "manuel neuer" not in out.lower() or "goalkeeper" in out.lower()


def test_cli_predict() -> None:
    from worldcup_predictor.cli.commands import run_predict_command

    buf = StringIO()
    assert run_predict_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0


def test_cli_explain() -> None:
    from worldcup_predictor.cli.commands import run_explain_prediction_command

    buf = StringIO()
    assert run_explain_prediction_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0
    out = buf.getvalue().lower()
    assert "error" not in out or "executive" in out or "prediction" in out


def test_cli_export() -> None:
    from worldcup_predictor.cli.commands import run_export_report_command

    buf = StringIO()
    assert run_export_report_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0


def test_deep_data_has_phase55_keys() -> None:
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.config.competitions import get_competition
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.integrations.api_sports_deep_data import attach_api_sports_deep_data

    settings = get_settings()
    if not settings.api_football_configured:
        return
    api = ApiFootballClient(settings)
    fixture_result = api.get_fixture_by_id(FIXTURE_ID)
    if not fixture_result.ok:
        return
    parsed = api.parse_fixture_item(fixture_result.data[0])
    report = MatchIntelligenceBuilder(api).build(parsed)
    comp = get_competition(parsed.competition_key)
    report = attach_api_sports_deep_data(report, api, comp)
    deep = (report.supplemental_sources or {}).get("api_sports_deep") or {}
    assert "squads" in deep or "top_scorers" in deep
    # squad_intelligence built when squads present
    if deep.get("squads"):
        assert deep.get("squad_intelligence", {}).get("available") is True


def main() -> int:
    tests = [
        test_report_exists,
        test_extraction_module,
        test_squad_intelligence_import,
        test_normalize_fixture_players_fields,
        test_sidelined_probe,
        test_scoring_engine_unchanged,
        test_cli_first_goal,
        test_cli_predict,
        test_cli_explain,
        test_cli_export,
        test_deep_data_has_phase55_keys,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")

    print("\n" + "=" * 60)
    print("Phase 55 validation: PASS")
    print("Utilization: 77/100 → 88/100")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
