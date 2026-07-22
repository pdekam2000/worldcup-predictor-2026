"""ECSE integrity helpers — input/output hashes and duplicate-signature detection.

Research / FAS safety layer. Does not alter Poisson / Dixon–Coles formulas.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable


REQUIRED_CACHE_KEY_DIMENSIONS = (
    "fixture_id",
    "home_team_id_or_name",
    "away_team_id_or_name",
    "competition",
    "odds_feature_fingerprint",
    "model_version",
    "feature_version",
)


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_ecse_input_hash(
    *,
    fixture_id: int,
    odds_row: dict[str, Any] | None,
    lambda_features: dict[str, Any] | None,
    source: str,
    model_version: str,
    registry_fixture_id: int | None = None,
) -> str:
    odds_clean = {
        k: v
        for k, v in (odds_row or {}).items()
        if not str(k).startswith("_") and k != "registry_fixture_id"
    }
    payload = {
        "fixture_id": int(fixture_id),
        "registry_fixture_id": registry_fixture_id,
        "source": source,
        "model_version": model_version,
        "odds_features": odds_clean,
        # lambda features excluded from INPUT hash — they are derived; include odds only
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def compute_ecse_output_hash(prediction: dict[str, Any]) -> str:
    payload = {
        "lambda_home": prediction.get("lambda_home"),
        "lambda_away": prediction.get("lambda_away"),
        "top_10": prediction.get("top_10_scorelines") or prediction.get("top_10"),
        "model_version": prediction.get("model_version"),
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def stamp_ecse_integrity_fields(
    prediction: dict[str, Any] | None,
    *,
    input_hash: str | None,
    output_hash_fn: Callable[[dict[str, Any]], str] | None = None,
) -> dict[str, Any] | None:
    if not prediction:
        return prediction
    out = copy.deepcopy(prediction)
    if input_hash:
        out["ecse_input_hash"] = input_hash
        raw = out.get("raw_features")
        if isinstance(raw, dict):
            raw = dict(raw)
            raw["ecse_input_hash"] = input_hash
            out["raw_features"] = raw
    if output_hash_fn is not None:
        out["ecse_output_hash"] = output_hash_fn(out)
    return out


def lambda_signature(prediction: dict[str, Any]) -> tuple[float | None, float | None]:
    try:
        lh = float(prediction["lambda_home"]) if prediction.get("lambda_home") is not None else None
    except (TypeError, ValueError):
        lh = None
    try:
        la = float(prediction["lambda_away"]) if prediction.get("lambda_away") is not None else None
    except (TypeError, ValueError):
        la = None
    return (lh, la)


def top10_signature(prediction: dict[str, Any]) -> tuple:
    rows = prediction.get("top_10_scorelines") or prediction.get("top_10") or []
    out = []
    for r in rows[:10]:
        if not isinstance(r, dict):
            continue
        score = r.get("scoreline") or r.get("score")
        try:
            prob = round(float(r.get("probability") or 0), 9)
        except (TypeError, ValueError):
            prob = None
        out.append((score, prob))
    return tuple(out)


def detect_duplicate_output_distinct_inputs(
    fixtures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag pairs with identical ECSE output hashes but different input hashes.

    Does not invalidate predictions — research integrity warning only.
    """
    by_out: dict[str, list[dict[str, Any]]] = {}
    for row in fixtures:
        ecse = row.get("ecse") or (row.get("prediction") or {}).get("ecse") or row
        out_h = ecse.get("ecse_output_hash")
        if not out_h:
            # synthesize from lambdas / top5 if missing
            if ecse.get("lambda_home") is None:
                continue
            out_h = compute_ecse_output_hash(
                {
                    "lambda_home": ecse.get("lambda_home"),
                    "lambda_away": ecse.get("lambda_away"),
                    "top_10_scorelines": ecse.get("top_10_scorelines")
                    or [
                        {
                            "scoreline": (ecse.get(f"top{i}") or {}).get("score"),
                            "probability": (ecse.get(f"top{i}") or {}).get("probability"),
                        }
                        for i in range(1, 6)
                    ],
                    "model_version": ecse.get("model_version"),
                }
            )
        by_out.setdefault(out_h, []).append(
            {
                "fixture_id": row.get("fixture_id") or ecse.get("fixture_id"),
                "match": row.get("match")
                or f"{row.get('home_team') or ecse.get('home_team')} vs {row.get('away_team') or ecse.get('away_team')}",
                "ecse_input_hash": ecse.get("ecse_input_hash")
                or (ecse.get("raw_features") or {}).get("ecse_input_hash"),
                "ecse_output_hash": out_h,
                "model_version": ecse.get("model_version"),
                "lambda_home": ecse.get("lambda_home"),
                "lambda_away": ecse.get("lambda_away"),
            }
        )

    warnings: list[dict[str, Any]] = []
    for out_h, group in by_out.items():
        if len(group) < 2:
            continue
        input_hashes = {g.get("ecse_input_hash") for g in group}
        # If any input hash missing, still warn on identical outputs across fixture IDs
        fixture_ids = {g.get("fixture_id") for g in group}
        if len(fixture_ids) < 2:
            continue
        distinct_inputs = len(input_hashes) > 1 or (None in input_hashes and len(group) > 1)
        # Also treat identical None input hashes with identical odds-less outputs as warning
        # when fixture IDs differ — historical FAS case used odds-feature collision.
        if distinct_inputs or all(h is None for h in input_hashes):
            warnings.append(
                {
                    "code": "ECSE_DUPLICATE_OUTPUT_DISTINCT_INPUTS",
                    "ecse_output_hash": out_h,
                    "fixtures": group,
                    "input_hashes": sorted(str(h) for h in input_hashes),
                    "research_integrity_warning": True,
                }
            )
    return warnings


def assert_cache_key_dimensions(key_parts: dict[str, Any]) -> list[str]:
    missing = [d for d in REQUIRED_CACHE_KEY_DIMENSIONS if d not in key_parts or key_parts.get(d) in (None, "")]
    return missing
