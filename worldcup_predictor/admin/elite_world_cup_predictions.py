"""Phase 60D — Safe Elite World Cup predictions for website (experimental)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.admin.elite_shadow_comparison import EliteShadowComparisonService
from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService, sanitize_payload

WC_COMPETITIONS = frozenset({"world_cup_2026", "world_cup"})
_PUBLIC_STRIP_KEYS = frozenset(
    {
        "root_cause",
        "component_contributions",
        "model_versions",
        "confidence_tiers",
        "fusion",
        "sources",
        "meta",
        "internal",
    }
)


def _is_world_cup_fixture(bundle: dict[str, Any]) -> bool:
    comp = str((bundle.get("fixture") or {}).get("competition_key") or bundle.get("competition_key") or "")
    return comp in WC_COMPETITIONS or comp.startswith("world_cup")


def _safe_market(market: dict[str, Any]) -> dict[str, Any]:
    mp = market.get("market_predictions") or {}
    return {
        "market_id": market.get("market_id"),
        "prediction": market.get("prediction") or mp.get("prediction"),
        "confidence": market.get("confidence") or mp.get("confidence"),
        "tier": market.get("tier") or mp.get("tier"),
        "status": market.get("status"),
        "evaluation": market.get("evaluation"),
    }


def _safe_fixture(bundle: dict[str, Any]) -> dict[str, Any]:
    markets = [_safe_market(m) for m in bundle.get("markets") or []]
    primary = markets[0] if markets else {}
    return {
        "fixture_id": bundle.get("fixture_id"),
        "fixture": bundle.get("fixture") or {},
        "fixture_status": bundle.get("fixture_status"),
        "generated_at": bundle.get("generated_at"),
        "prediction_day": bundle.get("prediction_day"),
        "markets": markets,
        "elite_pick": primary.get("prediction"),
        "confidence_tier": primary.get("tier"),
        "market_id": primary.get("market_id"),
        "status": primary.get("status"),
        "is_elite": True,
        "is_experimental": True,
        "is_shadow": True,
        "is_user_visible": False,
        "label": "Elite Experimental / Shadow-based research output",
    }


def _safe_comparison_row(row: dict[str, Any]) -> dict[str, Any]:
    shadow = row.get("shadow") or {}
    production = row.get("production") or {}
    disagrees = bool(row.get("disagreement"))
    return sanitize_payload(
        {
            "fixture_id": row.get("fixture_id"),
            "market_id": row.get("market_id"),
            "same_pick": not disagrees if row.get("comparable") else None,
            "disagrees": disagrees,
            "elite_pick": shadow.get("normalized_pick") or shadow.get("prediction"),
            "production_pick": production.get("normalized_pick") or production.get("prediction"),
            "elite_confidence": shadow.get("confidence"),
            "production_confidence": production.get("confidence"),
            "elite_tier": shadow.get("tier"),
            "has_production": row.get("has_production"),
        }
    )


class EliteWorldCupPredictionsService:
    """World Cup elite shadow predictions — safe fields only."""

    def __init__(self) -> None:
        self.preview = EliteShadowPreviewService()
        self.comparison = EliteShadowComparisonService(preview=self.preview)

    def list_predictions(
        self,
        *,
        market: str = "all",
        tier: str = "all",
        status: str = "all",
        limit: int = 50,
        offset: int = 0,
        include_comparison: bool = False,
        public_mode: bool = False,
    ) -> dict[str, Any]:
        raw = self.preview.list_predictions(
            market=market,
            tier=tier,
            status=status,
            limit=500,
            offset=0,
        )
        wc_fixtures = [_safe_fixture(b) for b in raw.get("fixtures") or [] if _is_world_cup_fixture(b)]
        total = len(wc_fixtures)
        page = wc_fixtures[offset : offset + limit]

        comparison_map: dict[str, dict[str, Any]] = {}
        if include_comparison and not public_mode:
            comp = self.comparison.build_comparison(
                market=market,
                tier=tier,
                status=status,
                limit=500,
                offset=0,
            )
            for row in comp.get("items") or comp.get("rows") or []:
                fid = int(row.get("fixture_id") or 0)
                mid = str(row.get("market_id") or "")
                comparison_map[f"{fid}:{mid}"] = _safe_comparison_row(row)

        if include_comparison and not public_mode:
            for fx in page:
                fid = int(fx.get("fixture_id") or 0)
                fx["comparison"] = [
                    comparison_map[f"{fid}:{m.get('market_id')}"]
                    for m in fx.get("markets") or []
                    if f"{fid}:{m.get('market_id')}" in comparison_map
                ]

        return sanitize_payload(
            {
                "status": "ok",
                "total": total,
                "limit": limit,
                "offset": offset,
                "fixtures": page,
                "is_elite": True,
                "is_experimental": True,
                "is_user_visible": public_mode,
                "disclaimer": "Research statistics and experimental predictions. Not betting advice.",
                "access_mode": "public" if public_mode else "super_admin",
            }
        )
