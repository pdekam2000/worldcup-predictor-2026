"""Phase 36A comprehensive production audit for fixture 1489393."""
import json
import os
import sqlite3
from pathlib import Path

DB = Path("/opt/worldcup-predictor/data/football_intelligence.db")
out = {}

# Env (masked)
for k in (
    "API_FOOTBALL_KEY", "APISPORTS_KEY", "SPORTMONKS_API_TOKEN", "SPORTMONKS_TOKEN",
    "DATABASE_URL", "SQLITE_PATH", "NATIONAL_TEAM_INTELLIGENCE_ENABLED",
    "SPORTMONKS_ENRICHMENT_ENABLED", "ENVIRONMENT",
):
    v = os.environ.get(k) or os.environ.get(k.lower())
    if v:
        out[f"env_{k}"] = "SET(len=" + str(len(v)) + ")" if "KEY" in k or "TOKEN" in k or "URL" in k else v
    else:
        # try .env
        out[f"env_{k}"] = "NOT_IN_ENV"

# Read .env keys presence only
env_path = Path("/opt/worldcup-predictor/.env")
if env_path.exists():
    keys = []
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            keys.append(line.split("=")[0].strip())
    out["dotenv_keys"] = sorted(keys)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
fid = 1489393

fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
out["fixture"] = dict(fx) if fx else None

# Pipeline run
try:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

    get_settings.cache_clear()
    settings = get_settings()
    out["settings"] = {
        "sqlite_path": settings.sqlite_path,
        "national_team_intelligence_enabled": settings.national_team_intelligence_enabled,
        "sportmonks_enrichment_enabled": getattr(settings, "sportmonks_enrichment_enabled", None),
        "api_football_key_set": bool(settings.api_football_key or getattr(settings, "apisports_key", None)),
        "sportmonks_token_set": bool(getattr(settings, "sportmonks_api_token", None) or getattr(settings, "sportmonks_token", None)),
    }
    result = PredictPipeline(settings).run(fid, record_history=False)
    p = result.prediction
    intel = result.intelligence_report
    spec = result.specialist_report
    adj = getattr(p, "adaptive_confidence", None)
    trace = p.audit_report.trace if p.audit_report else None
    md = p.metadata or {}

    out["pipeline"] = {
        "success": result.success,
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
        "adaptive_bonus": adj.total_bonus if adj else None,
        "fusion_band": md.get("fusion_quality_band"),
        "fusion_consensus": md.get("fusion_consensus"),
    }
    if intel:
        out["intelligence"] = {
            "is_placeholder": intel.is_placeholder,
            "source": intel.source,
            "missing_data": intel.missing_data,
            "data_quality_score": intel.data_quality.score if intel.data_quality else None,
            "data_quality_breakdown_total": intel.data_quality.breakdown_total if intel.data_quality else None,
            "lineups_available": bool(intel.lineups and intel.lineups.get("available")),
            "odds_available": bool(intel.odds and intel.odds.available),
            "home_injuries": bool(intel.home_team.injuries and intel.home_team.injuries.available),
            "away_injuries": bool(intel.away_team.injuries and intel.away_team.injuries.available),
            "home_source": intel.home_team.source,
            "away_source": intel.away_team.source,
            "api_inspection": [
                {"endpoint": ep.endpoint, "status": ep.status, "loaded": ep.loaded, "source": ep.source, "error": ep.error}
                for ep in (intel.api_inspection.endpoints if intel.api_inspection else [])
            ],
            "supplemental_keys": list((intel.supplemental_sources or {}).keys()),
        }
    if spec and spec.agents:
        out["specialists"] = {
            name: {
                "domain": sig.domain,
                "status": sig.status,
                "status_reason": sig.status_reason,
                "impact_score": sig.impact_score,
            }
            for name, sig in spec.agents.items()
        }
        out["specialist_aggregated"] = spec.master.aggregated_score if spec.master else None

    # Fusion report
    raw_fusion = md.get("fusion_report_v2")
    if raw_fusion:
        try:
            fr = json.loads(raw_fusion) if isinstance(raw_fusion, str) else raw_fusion
            out["fusion_report"] = {
                "decision_quality_band": fr.get("decision_quality_band"),
                "consensus_strength": fr.get("consensus_strength"),
                "confidence_adjustment": fr.get("confidence_adjustment"),
                "fusion_diversity_score": fr.get("fusion_diversity_score"),
                "risk_flags": fr.get("risk_flags"),
                "fusion_prediction": fr.get("fusion_prediction"),
                "summary": fr.get("summary"),
            }
        except Exception as e:
            out["fusion_parse_error"] = str(e)
except Exception as e:
    out["pipeline_error"] = str(e)

# API cache files for fixture
cache_dirs = [
    Path("/opt/worldcup-predictor/.cache/api_football"),
    Path("/opt/worldcup-predictor/data/cache"),
]
for d in cache_dirs:
    if d.exists():
        matches = list(d.rglob(f"*{fid}*"))[:5]
        out[f"cache_files_{d.name}"] = [str(m.relative_to(d)) for m in matches]

# Sportmonks tables
sm_tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%sportmonks%'").fetchall()]
out["sportmonks_tables"] = {}
for t in sm_tables:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
    out["sportmonks_tables"][t] = {"columns": cols}
    if "fixture_id" in cols:
        try:
            row = conn.execute(f"SELECT * FROM {t} WHERE fixture_id=? LIMIT 1", (fid,)).fetchone()
            out["sportmonks_tables"][t]["row_for_fixture"] = bool(row)
        except Exception:
            pass
    elif "api_fixture_id" in cols:
        try:
            row = conn.execute(f"SELECT * FROM {t} WHERE api_fixture_id=? LIMIT 1", (fid,)).fetchone()
            out["sportmonks_tables"][t]["row_for_fixture"] = bool(row)
        except Exception:
            pass

print(json.dumps(out, indent=2, default=str)[:25000])
