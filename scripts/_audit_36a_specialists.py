"""Phase 36A specialist + WDE factor dump."""
import json
import os
import sys

ROOT = os.environ.get("AUDIT_ROOT", "/opt/worldcup-predictor")
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

get_settings.cache_clear()
fid = 1489393
result = PredictPipeline(get_settings()).run(fid, record_history=False)
p = result.prediction
intel = result.intelligence_report
spec = result.specialist_report
trace = p.audit_report.trace if p.audit_report else None
md = p.metadata or {}

out = {
    "mode": "with_env" if get_settings().api_football_configured else "no_env",
    "is_placeholder": p.is_placeholder,
    "confidence": p.confidence_score,
    "intel_placeholder": intel.is_placeholder if intel else None,
    "intel_source": intel.source if intel else None,
    "missing_data": intel.missing_data if intel else [],
    "wde": {
        "baseline": trace.baseline_confidence if trace else None,
        "final": trace.final_confidence if trace else None,
        "reductions": list(trace.confidence_reductions or []) if trace else [],
        "no_bet": list(trace.no_bet_reasons or []) if trace else [],
        "caps": list(trace.confidence_caps_applied or []) if trace else [],
    },
    "adaptive": getattr(p, "adaptive_confidence", None) and {
        "base": p.adaptive_confidence.base_confidence,
        "final": p.adaptive_confidence.final_confidence,
        "bonus": p.adaptive_confidence.total_bonus,
    },
    "fusion": {
        "band": md.get("fusion_quality_band"),
        "consensus": md.get("fusion_consensus"),
    },
}

if p.audit_report:
    def _fc(f):
        return {"factor_name": f.factor_name, "weight_pct": f.weight_pct, "score": f.score, "contribution": f.contribution, "direction": f.direction}
    out["wde_factors"] = {
        "supported": [_fc(f) for f in p.audit_report.supported_factors[:10]],
        "opposed": [_fc(f) for f in p.audit_report.opposed_factors[:10]],
        "conflicts": [{"description": getattr(c, "description", None), "severity": getattr(c, "severity", None)} for c in (p.audit_report.conflicts or [])[:8]],
        "limitations": [{"field": getattr(l, "field", None), "impact": getattr(l, "impact", None)} for l in (p.audit_report.limitations or [])[:8]],
    }

if spec:
    agents = {}
    for key in sorted(spec.signals.keys()):
        sig = spec.signal(key)
        if sig:
            agents[key] = {
                "status": sig.status,
                "status_reason": sig.status_reason,
                "impact_score": sig.impact_score,
                "missing": sig.missing_data,
                "warnings": (sig.warnings or [])[:3],
            }
    out["specialists"] = agents

raw_fusion = md.get("fusion_report_v2")
if raw_fusion:
    fr = json.loads(raw_fusion) if isinstance(raw_fusion, str) else raw_fusion
    out["fusion_detail"] = {
        "decision_quality_band": fr.get("decision_quality_band"),
        "consensus_strength": fr.get("consensus_strength"),
        "confidence_adjustment": fr.get("confidence_adjustment"),
        "risk_flags": fr.get("risk_flags"),
        "fusion_diversity_score": fr.get("fusion_diversity_score"),
    }

print(json.dumps(out, indent=2, default=str))
