"""Local Phase 36A pipeline audit for fixture 1489393."""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "football_intelligence.db"
os.chdir(ROOT)

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

get_settings.cache_clear()
settings = get_settings()
fid = 1489393

out = {
    "settings": {
        "api_football_key_set": settings.api_football_configured,
        "sportmonks_token_set": settings.sportmonks_configured,
        "national_team_intelligence_enabled": settings.national_team_intelligence_enabled,
    }
}

result = PredictPipeline(settings).run(fid, record_history=False)
p = result.prediction
intel = result.intelligence_report
spec = result.specialist_report
adj = getattr(p, "adaptive_confidence", None)
trace = p.audit_report.trace if p.audit_report else None
md = p.metadata or {}

out["pipeline"] = {
    "prediction_is_placeholder": p.is_placeholder,
    "confidence_score": p.confidence_score,
    "no_bet": p.no_bet_flag,
    "data_quality_pct": md.get("data_quality_pct"),
    "wde_baseline": trace.baseline_confidence if trace else None,
    "wde_final": trace.final_confidence if trace else None,
    "wde_reductions": list(trace.confidence_reductions or []) if trace else [],
    "wde_no_bet": list(trace.no_bet_reasons or []) if trace else [],
    "adaptive_base": adj.base_confidence if adj else None,
    "adaptive_final": adj.final_confidence if adj else None,
    "fusion_band": md.get("fusion_quality_band"),
    "fusion_consensus": md.get("fusion_consensus"),
}
if intel:
    out["intelligence"] = {
        "is_placeholder": intel.is_placeholder,
        "source": intel.source,
        "missing_data": intel.missing_data,
        "data_quality_score": intel.data_quality.score if intel.data_quality else None,
        "supplemental_keys": list((intel.supplemental_sources or {}).keys()),
    }

# specialists via domain model
if spec:
    agent_names = [
        "form_intelligence_agent", "lineup_intelligence_agent", "injury_intelligence_agent",
        "motivation_agent", "odds_agent", "odds_movement_agent", "weather_agent", "referee_agent",
        "venue_travel_agent", "team_strength_agent", "historical_h2h_agent", "data_quality_agent",
        "national_team_intelligence_agent", "tournament_context_agent", "xg_intelligence_agent",
        "sportmonks_prediction_agent", "expected_lineup_agent",
    ]
    out["specialists"] = {}
    for name in agent_names:
        sig = spec.signal(name)
        if sig:
            out["specialists"][name] = {
                "domain": sig.domain,
                "status": sig.status,
                "status_reason": sig.status_reason,
                "impact_score": sig.impact_score,
            }

print(json.dumps(out, indent=2, default=str))
