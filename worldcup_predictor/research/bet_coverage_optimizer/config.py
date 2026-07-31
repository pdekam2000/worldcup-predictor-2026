"""Research-only Bet Coverage Optimizer configuration (no hardcoded scoring weights)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.models import ScoringWeights

ALLOWED_TOP_N: frozenset[int] = frozenset({8, 10, 12})
DEFAULT_TOP_N = 8
DEFAULT_TOP_CANDIDATES = 5

# Default YAML-compatible layout (also written to default_config.json)
DEFAULT_CONFIG: dict[str, Any] = {
    "research_only": True,
    "owner_only": True,
    "top_n_scores": 8,
    "exact_count": 3,
    "total_selections": 4,
    "top_candidates": 5,
    "min_odds": 1.55,
    "coverage_weights": {
        "covered_probability_mass": 0.35,
        "non_exact_probability_mass": 0.20,
        "exact_overlap_probability_mass": 0.15,
        "estimated_edge": 0.20,
        "log_odds": 0.10,
    },
    "penalties": {
        "stale_penalty": 1.0,
        "redundant_penalty": 0.35,
        "narrow_mass_penalty": 0.25,
        "narrow_mass_threshold": 0.05,
    },
    "coupon_optimizer": {
        "candidate_pool_per_fixture": 5,
        "stake_per_ticket": 1.0,
        "diversification_weight": 0.15,
        "overlap_penalty_weight": 0.20,
        "ev_weight": 0.65,
    },
    "insurance": {
        "enabled": True,
        "min_odds": 1.55,
        "max_odds": 25.0,
        "min_incremental_uncovered_mass": 0.03,
        "max_primary_overlap_ratio": 0.85,
        "top_k_candidates": 5,
        "max_insurance_tickets": 15,
        "min_insurance_tickets": 3,
        "allow_triple_insurance": False,
        "min_two_leg_joint_mass": 0.02,
        "research_freshness_max_age_hours": 48.0,
    },
    "insurance_weights": {
        "incremental_uncovered_probability_mass": 0.40,
        "residual_risk_reduction": 0.20,
        "estimated_edge": 0.15,
        "log_odds": 0.10,
        "diversification": 0.10,
        "primary_overlap_penalty": 0.05,
    },
    "budget": {
        "total_budget_eur": 400.0,
        "main_budget_ratio": 0.80,
        "insurance_budget_ratio": 0.20,
        "min_stake_per_ticket_eur": 1.0,
        "max_stake_per_ticket_eur": 20.0,
        "rounding_step_eur": 0.50,
        "stake_mode": "equal",
        "kelly_enabled": False,
    },
}

_WEIGHT_KEY_MAP = {
    "covered_probability_mass": "covered_mass",
    "non_exact_probability_mass": "non_exact_mass",
    "exact_overlap_probability_mass": "exact_overlap_mass",
    "estimated_edge": "estimated_edge",
    "log_odds": "log_odds",
    # allow short aliases
    "covered_mass": "covered_mass",
    "non_exact_mass": "non_exact_mass",
    "exact_overlap_mass": "exact_overlap_mass",
}


def default_config_path() -> Path:
    return Path(__file__).resolve().parent / "default_config.json"


def ensure_default_config_file() -> Path:
    path = default_config_path()
    if not path.is_file():
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    return path


def validate_top_n(top_n: int) -> int:
    n = int(top_n)
    if n not in ALLOWED_TOP_N:
        raise ValueError(f"top_n_scores must be one of {sorted(ALLOWED_TOP_N)}, got {n}")
    return n


def scoring_weights_from_config(cfg: dict[str, Any] | None) -> ScoringWeights:
    raw = dict(DEFAULT_CONFIG)
    if cfg:
        raw.update(cfg)
    cw = dict(DEFAULT_CONFIG["coverage_weights"])
    cw.update(dict(raw.get("coverage_weights") or {}))
    pen = dict(DEFAULT_CONFIG["penalties"])
    pen.update(dict(raw.get("penalties") or {}))

    kwargs: dict[str, float] = {}
    for src, dest in _WEIGHT_KEY_MAP.items():
        if src in cw:
            kwargs[dest] = float(cw[src])
    return ScoringWeights(
        covered_mass=float(kwargs.get("covered_mass", 0.35)),
        non_exact_mass=float(kwargs.get("non_exact_mass", 0.20)),
        exact_overlap_mass=float(kwargs.get("exact_overlap_mass", 0.15)),
        estimated_edge=float(kwargs.get("estimated_edge", 0.20)),
        log_odds=float(kwargs.get("log_odds", 0.10)),
        min_odds=float(raw.get("min_odds", pen.get("min_odds", 1.55))),
        stale_penalty=float(pen.get("stale_penalty", 1.0)),
        redundant_penalty=float(pen.get("redundant_penalty", 0.35)),
        narrow_mass_penalty=float(pen.get("narrow_mass_penalty", 0.25)),
        narrow_mass_threshold=float(pen.get("narrow_mass_threshold", 0.05)),
    )


def load_optimizer_config(path: str | Path | None = None) -> dict[str, Any]:
    """
    Load research optimizer config from JSON (YAML optional if PyYAML installed).
    Missing file → defaults. No code changes required to retune weights.
    """
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep-ish copy
    ensure_default_config_file()
    target = Path(path) if path else default_config_path()
    if not target.is_file():
        return cfg

    text = target.read_text(encoding="utf-8")
    loaded: dict[str, Any]
    if target.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyYAML required to load .yaml config; use default_config.json") from exc
        loaded = yaml.safe_load(text) or {}
    else:
        loaded = json.loads(text)

    if not isinstance(loaded, dict):
        raise ValueError("config root must be a JSON/YAML object")

    # shallow merge + nested weight/penalty/coupon merges
    for key, value in loaded.items():
        if key in {"coverage_weights", "penalties", "coupon_optimizer", "insurance", "insurance_weights", "budget"} and isinstance(
            value, dict
        ):
            base = dict(cfg.get(key) or {})
            base.update(value)
            cfg[key] = base
        else:
            cfg[key] = value

    if "top_n_scores" in cfg:
        cfg["top_n_scores"] = validate_top_n(int(cfg["top_n_scores"]))
    return cfg
