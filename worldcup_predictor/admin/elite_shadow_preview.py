"""Phase 59A — Safe JSONL loader for Elite Shadow admin preview."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PREDICTIONS_PATH = ROOT / "data" / "shadow" / "elite_orchestrator_predictions.jsonl"
EVALUATIONS_PATH = ROOT / "data" / "shadow" / "elite_orchestrator_evaluations.jsonl"
ROOT_CAUSE_PATH = ROOT / "data" / "shadow" / "root_cause_store" / "knowledge_records.jsonl"
DB_PATH = ROOT / "data" / "football_intelligence.db"

_SENSITIVE_KEYS = frozenset({"api_token", "api_key", "openai_api_key", "sportmonks_token"})


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load JSONL safely; skip invalid lines."""
    meta = {"path": str(path), "exists": path.is_file(), "lines_read": 0, "rows_parsed": 0, "invalid_lines": 0}
    if not path.is_file():
        return [], meta
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        meta["lines_read"] += 1
        try:
            rows.append(json.loads(line))
            meta["rows_parsed"] += 1
        except json.JSONDecodeError:
            meta["invalid_lines"] += 1
    return rows, meta


def sanitize_payload(value: Any) -> Any:
    """Strip sensitive keys from API responses."""
    if isinstance(value, dict):
        return {
            k: sanitize_payload(v)
            for k, v in value.items()
            if str(k).lower() not in _SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_payload(v) for v in value]
    return value


def _fixture_lookup() -> dict[int, dict[str, Any]]:
    if not DB_PATH.is_file():
        return {}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key FROM fixtures"
    ).fetchall()
    conn.close()
    return {
        int(r["fixture_id"]): {
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "kickoff_utc": r["kickoff_utc"],
            "status": r["status"],
            "competition_key": r["competition_key"],
        }
        for r in rows
    }


def _eval_key(fixture_id: int, market_id: str) -> str:
    return f"{fixture_id}:{market_id}"


def _index_evaluations(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        fid = int(row.get("fixture_id") or 0)
        market = str(row.get("market_id") or "")
        out[_eval_key(fid, market)] = row
    return out


def _index_root_cause(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        fid = int(row.get("fixture_id") or 0)
        market = str(row.get("market") or row.get("market_id") or "")
        out.setdefault(_eval_key(fid, market), []).append(row)
    return out


def _evaluation_status(eval_row: dict[str, Any] | None) -> str:
    if not eval_row:
        return "pending"
    outcome = str(eval_row.get("outcome") or "pending")
    if outcome in ("correct", "incorrect", "partial"):
        return "evaluated"
    return outcome


def _market_view(pred: dict[str, Any], eval_row: dict[str, Any] | None, root_cause: list[dict[str, Any]]) -> dict[str, Any]:
    mp = pred.get("market_predictions") or {}
    status = _evaluation_status(eval_row)
    return sanitize_payload(
        {
            "market_id": pred.get("market_id"),
            "prediction": mp.get("prediction"),
            "confidence": mp.get("confidence"),
            "tier": mp.get("tier"),
            "component_contributions": pred.get("component_contributions") or [],
            "confidence_tiers": pred.get("confidence_tiers"),
            "model_versions": pred.get("model_versions"),
            "status": status,
            "evaluation": {
                "outcome": (eval_row or {}).get("outcome"),
                "reality": (eval_row or {}).get("reality"),
                "paired_at": (eval_row or {}).get("paired_at"),
            }
            if eval_row
            else None,
            "root_cause": root_cause or None,
            "is_shadow": pred.get("is_shadow", True),
            "is_user_visible": pred.get("is_user_visible", False),
        }
    )


def _fixture_bundle(
    fixture_id: int,
    preds: list[dict[str, Any]],
    eval_index: dict[str, dict[str, Any]],
    rc_index: dict[str, list[dict[str, Any]]],
    fixtures: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    first = preds[0]
    fx = fixtures.get(fixture_id, {})
    markets = []
    for pred in preds:
        market_id = str(pred.get("market_id") or "")
        key = _eval_key(fixture_id, market_id)
        markets.append(_market_view(pred, eval_index.get(key), rc_index.get(key, [])))

    statuses = {m["status"] for m in markets}
    if statuses == {"pending"}:
        fixture_status = "pending"
    elif "pending" in statuses:
        fixture_status = "mixed"
    else:
        fixture_status = "evaluated"

    return sanitize_payload(
        {
            "fixture_id": fixture_id,
            "fixture": {
                "home_team": fx.get("home_team"),
                "away_team": fx.get("away_team"),
                "kickoff_utc": first.get("kickoff_time") or fx.get("kickoff_utc"),
                "competition_key": first.get("competition_key") or fx.get("competition_key"),
                "league_id": first.get("league_id"),
                "match_status": fx.get("status"),
            },
            "generated_at": first.get("generated_at"),
            "prediction_day": first.get("prediction_day"),
            "fixture_status": fixture_status,
            "markets": markets,
            "is_shadow": True,
            "is_user_visible": False,
        }
    )


class EliteShadowPreviewService:
    """Read-only shadow data for admin preview."""

    def __init__(
        self,
        *,
        predictions_path: Path | None = None,
        evaluations_path: Path | None = None,
        root_cause_path: Path | None = None,
    ) -> None:
        self.predictions_path = predictions_path or PREDICTIONS_PATH
        self.evaluations_path = evaluations_path or EVALUATIONS_PATH
        self.root_cause_path = root_cause_path or ROOT_CAUSE_PATH

    def _load_all(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        preds, pred_meta = load_jsonl(self.predictions_path)
        evals, eval_meta = load_jsonl(self.evaluations_path)
        rc, rc_meta = load_jsonl(self.root_cause_path)
        return preds, evals, rc, {"predictions": pred_meta, "evaluations": eval_meta, "root_cause": rc_meta}

    def list_predictions(
        self,
        *,
        market: str | None = None,
        tier: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        preds, evals, rc_rows, sources = self._load_all()
        eval_index = _index_evaluations(evals)
        rc_index = _index_root_cause(rc_rows)
        fixtures = _fixture_lookup()

        by_fixture: dict[int, list[dict[str, Any]]] = {}
        for pred in preds:
            fid = int(pred.get("fixture_id") or 0)
            by_fixture.setdefault(fid, []).append(pred)

        bundles = [_fixture_bundle(fid, rows, eval_index, rc_index, fixtures) for fid, rows in sorted(by_fixture.items())]

        if market and market != "all":
            bundles = [b for b in bundles if any(m.get("market_id") == market for m in b.get("markets") or [])]
        if tier and tier != "all":
            bundles = [
                b
                for b in bundles
                if any(str(m.get("tier") or "").upper() == tier.upper() for m in b.get("markets") or [])
            ]
        if status and status != "all":
            if status == "pending":
                bundles = [b for b in bundles if b.get("fixture_status") in ("pending", "mixed")]
            elif status == "evaluated":
                bundles = [b for b in bundles if b.get("fixture_status") == "evaluated"]

        total = len(bundles)
        page = bundles[offset : offset + limit]
        return sanitize_payload(
            {
                "status": "ok",
                "total": total,
                "limit": limit,
                "offset": offset,
                "fixtures": page,
                "sources": sources,
                "shadow_only": True,
            }
        )

    def get_fixture(self, fixture_id: int) -> dict[str, Any] | None:
        preds, evals, rc_rows, sources = self._load_all()
        fixture_preds = [p for p in preds if int(p.get("fixture_id") or 0) == int(fixture_id)]
        if not fixture_preds:
            return None
        eval_index = _index_evaluations(evals)
        rc_index = _index_root_cause(rc_rows)
        fixtures = _fixture_lookup()
        bundle = _fixture_bundle(int(fixture_id), fixture_preds, eval_index, rc_index, fixtures)
        bundle["sources"] = sources
        bundle["status"] = "ok"
        return sanitize_payload(bundle)

    def list_evaluations(
        self,
        *,
        outcome: str | None = None,
        market: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        _, evals, _, sources = self._load_all()
        rows = evals
        if outcome and outcome != "all":
            rows = [r for r in rows if str(r.get("outcome") or "") == outcome]
        if market and market != "all":
            rows = [r for r in rows if str(r.get("market_id") or "") == market]
        total = len(rows)
        page = [sanitize_payload(r) for r in rows[offset : offset + limit]]
        return {
            "status": "ok",
            "total": total,
            "limit": limit,
            "offset": offset,
            "evaluations": page,
            "sources": sources,
            "shadow_only": True,
        }

    def list_root_cause(
        self,
        *,
        fixture_id: int | None = None,
        market: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        _, _, rc_rows, sources = self._load_all()
        rows = rc_rows
        if fixture_id is not None:
            rows = [r for r in rows if int(r.get("fixture_id") or 0) == int(fixture_id)]
        if market and market != "all":
            rows = [r for r in rows if str(r.get("market") or r.get("market_id") or "") == market]
        total = len(rows)
        page = [sanitize_payload(r) for r in rows[offset : offset + limit]]
        return {
            "status": "ok",
            "total": total,
            "limit": limit,
            "offset": offset,
            "records": page,
            "sources": sources,
            "shadow_only": True,
        }

    def preview_summary(self) -> dict[str, Any]:
        preds, evals, rc, sources = self._load_all()
        pending = sum(1 for e in evals if str(e.get("outcome") or "") == "pending")
        evaluated = sum(1 for e in evals if str(e.get("outcome") or "") in ("correct", "incorrect", "partial"))
        fixtures = len({int(p.get("fixture_id") or 0) for p in preds})
        return sanitize_payload(
            {
                "status": "ok",
                "fixtures_with_predictions": fixtures,
                "prediction_rows": len(preds),
                "evaluation_rows": len(evals),
                "evaluations_pending": pending,
                "evaluations_resolved": evaluated,
                "root_cause_records": len(rc),
                "sources": sources,
                "shadow_only": True,
                "is_user_visible": False,
                "data_available": bool(sources.get("predictions", {}).get("exists")),
                "empty_reason": None
                if sources.get("predictions", {}).get("exists")
                else "shadow_jsonl_missing",
            }
        )
