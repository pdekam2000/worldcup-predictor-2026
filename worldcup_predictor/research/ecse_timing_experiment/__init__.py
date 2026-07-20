"""Package init — ECSE timing experiment (research only)."""

# Keep imports lazy to avoid circular deps with canonical_ephemeral.
__all__ = [
    "run_timing_capture",
    "compare_snapshots",
    "build_stable_union",
]


def __getattr__(name: str):
    if name == "run_timing_capture":
        from worldcup_predictor.research.ecse_timing_experiment.capture import run_timing_capture

        return run_timing_capture
    if name == "compare_snapshots":
        from worldcup_predictor.research.ecse_timing_experiment.compare import compare_snapshots

        return compare_snapshots
    if name == "build_stable_union":
        from worldcup_predictor.research.ecse_timing_experiment.stable_union import build_stable_union

        return build_stable_union
    raise AttributeError(name)
