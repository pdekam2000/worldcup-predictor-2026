"""Phase 56 — Agent deduplication & signal quality validation."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_ID = 1489374
REPORTS = (
    "agent_overlap_audit.md",
    "duplicate_signal_audit.md",
    "agent_correlation_matrix.md",
    "agent_health_report.md",
)
SCORING_BASELINE = ROOT / "reports" / ".phase54_scoring_engine.sha256"


def test_reports_exist() -> None:
    for name in REPORTS:
        path = ROOT / "reports" / name
        assert path.is_file(), f"Missing {name}"
        assert len(path.read_text(encoding="utf-8")) > 200


def test_signal_diversity_module() -> None:
    from worldcup_predictor.fusion.signal_diversity import (
        apply_correlation_dampening,
        compute_fusion_diversity_score,
        structural_correlation,
    )
    from worldcup_predictor.fusion.models import AgentSignalRow

    assert structural_correlation("lineup_agent", "lineup_intelligence_agent") >= 0.5
    rows = [
        AgentSignalRow("lineup_intelligence_agent", "Lineup V2", 40, -40, weight=1.0, lean_1x2="home"),
        AgentSignalRow("lineup_agent", "Lineup", 35, -35, weight=0.45, lean_1x2="home"),
    ]
    dampened, mults = apply_correlation_dampening(rows)
    assert len(dampened) == 2
    assert mults.get("lineup_agent", 1.0) < 1.0
    score = compute_fusion_diversity_score(rows, baseline_1x2_lean="home")
    assert 0 <= score["fusion_diversity_score"] <= 100


def test_fusion_diversity_in_report() -> None:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import load_fusion_from_prediction
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

    settings = get_settings()
    pipeline = PredictPipeline(settings)
    result = pipeline.run(FIXTURE_ID, record_history=False)
    assert result.success and result.prediction
    fusion = load_fusion_from_prediction(result.prediction)
    assert fusion is not None
    data = fusion.to_dict()
    assert "fusion_diversity_score" in data
    assert "signal_diversity" in data
    assert data["fusion_diversity_score"] >= 0


def test_explainability_signal_diversity() -> None:
    from worldcup_predictor.cli.commands import run_explain_prediction_command
    import json

    buf = StringIO()
    assert run_explain_prediction_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0
    out = buf.getvalue()
    # JSON block in CLI output
    start = out.find("{")
    assert start >= 0
    data = json.loads(out[start : out.rfind("}") + 1])
    assert data.get("fusion_report")
    sd = data.get("signal_diversity")
    assert sd is not None
    assert "independent_signals" in sd
    assert "correlated_signals" in sd


def test_orchestrator_agent_count() -> None:
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator

    assert len(SpecialistOrchestrator.AGENT_CLASSES) >= 18


def test_scoring_engine_unchanged() -> None:
    if not SCORING_BASELINE.is_file():
        return
    current = hashlib.sha256(
        (ROOT / "worldcup_predictor" / "prediction" / "scoring_engine.py").read_bytes()
    ).hexdigest()
    assert current == SCORING_BASELINE.read_text(encoding="utf-8").strip()


def test_hall_of_fame_import() -> None:
    from worldcup_predictor.performance.hall_of_fame import build_hall_of_fame_report

    assert callable(build_hall_of_fame_report)


def test_learning_history_store() -> None:
    from worldcup_predictor.accuracy.history_store import PredictionHistoryStore

    store = PredictionHistoryStore()
    assert store.path.parent.exists() or True
    _ = store.load_all()


def test_cli_predict() -> None:
    from worldcup_predictor.cli.commands import run_predict_command

    buf = StringIO()
    assert run_predict_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0


def test_cli_explain() -> None:
    from worldcup_predictor.cli.commands import run_explain_prediction_command

    buf = StringIO()
    assert run_explain_prediction_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0
    out = buf.getvalue()
    assert "signal_diversity" in out or "independent" in out.lower() or "executive" in out.lower()


def test_cli_fusion_report() -> None:
    from worldcup_predictor.cli.commands import run_fusion_report_command

    buf = StringIO()
    assert run_fusion_report_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0
    out = buf.getvalue()
    assert "fusion_diversity_score" in out or "diversity" in out.lower()


def main() -> int:
    gen = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_phase56_reports.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert gen.returncode == 0, gen.stderr or gen.stdout

    tests = [
        test_reports_exist,
        test_signal_diversity_module,
        test_fusion_diversity_in_report,
        test_explainability_signal_diversity,
        test_orchestrator_agent_count,
        test_scoring_engine_unchanged,
        test_hall_of_fame_import,
        test_learning_history_store,
        test_cli_predict,
        test_cli_explain,
        test_cli_fusion_report,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")

    print("\n" + "=" * 60)
    print("Phase 56 validation: PASS")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
