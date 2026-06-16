"""Run predictions on sample fixtures and write distribution report."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _scoreline_key(h: float, a: float) -> str:
    return f"{int(round(h))}-{int(round(a))}"


def main() -> int:
    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine
    from worldcup_predictor.schedule.competition_schedule import create_schedule_service

    settings = get_settings()
    schedule = create_schedule_service(settings)
    overview = schedule.get_tournament_overview()
    fixture_ids: list[int] = [1489374]
    if overview and overview.upcoming:
        fixture_ids.extend(int(f.fixture_id) for f in overview.upcoming[:14])
    elif overview and overview.fixtures:
        fixture_ids.extend(int(f.fixture_id) for f in overview.fixtures[:14])
    fixture_ids = list(dict.fromkeys(fixture_ids))[:15]

    builder = MatchIntelligenceBuilder(ApiFootballClient(settings))
    engine = ScoringEngine()
    ou_counter: Counter[str] = Counter()
    score_counter: Counter[str] = Counter()
    rows: list[str] = []

    for fid in fixture_ids:
        try:
            report = builder.build_by_fixture_id(fid)
            pred = engine.predict(report)
            ou = pred.over_under.selection
            ou_counter[ou] += 1
            sl = _scoreline_key(pred.scoreline.home_goals, pred.scoreline.away_goals)
            score_counter[sl] += 1
            total = pred.metadata.get("expected_total_goals", "?")
            rows.append(
                f"| {fid} | {pred.match_name} | {ou} | {sl} | {total} | {pred.metadata.get('scoreline_confidence', '—')} |"
            )
        except Exception as exc:
            rows.append(f"| {fid} | — | error | — | — | {exc} |")

    out = ROOT / "reports" / "prediction_distribution_check.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(
        [
            "# Prediction Distribution Check",
            "",
            f"Fixtures sampled: **{len(fixture_ids)}**",
            "",
            "## Over / Under 2.5",
            "",
            f"- Over: **{ou_counter.get('over_2_5', 0)}**",
            f"- Under: **{ou_counter.get('under_2_5', 0)}**",
            "",
            "## Exact score distribution",
            "",
            f"- 1-0: **{score_counter.get('1-0', 0)}**",
            f"- 2-0: **{score_counter.get('2-0', 0)}**",
            f"- 2-1: **{score_counter.get('2-1', 0)}**",
            f"- 1-1: **{score_counter.get('1-1', 0)}**",
            f"- 0-0: **{score_counter.get('0-0', 0)}**",
            "",
            "## Per-fixture",
            "",
            "| Fixture | Match | O/U | Scoreline | Exp. total | SL conf |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
            "",
        ]
    )
    out.write_text(body, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
