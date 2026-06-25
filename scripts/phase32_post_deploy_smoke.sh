#!/usr/bin/env bash
# Live API smoke test post Phase 32 deploy
set -euo pipefail
cd /opt/worldcup-predictor
OUT="${1:-/tmp/phase32_post_deploy_smoke.json}"
.venv/bin/python - <<'PY'
import json, urllib.request

def predict(fid):
    req = urllib.request.Request(f"http://127.0.0.1:8000/api/predict/{fid}", method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())

fixtures = [
    (1539007, "Netherlands vs Sweden"),
    (1489393, "Germany vs Ivory Coast"),
]
# France fixture
try:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    repo = FootballIntelligenceRepository()
    for r in repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=40):
        m = f"{r.get('home_team_name','')} vs {r.get('away_team_name','')}"
        if "France" in m:
            fixtures.append((int(r["fixture_id"]), m))
            break
except Exception:
    pass

results = []
for fid, label in fixtures:
    d = predict(fid)
    nat = {}
    # probe supplemental via internal predict if API omits it
    try:
        from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
        from worldcup_predictor.config.settings import get_settings
        get_settings.cache_clear()
        pipe = PredictPipeline(settings=get_settings())
        internal = pipe.run(fixture_id=fid)
        pred = internal.prediction
        rep = internal.report
        nat_block = (getattr(rep, "supplemental_sources", None) or {}).get("national_team_intelligence") or {}
        nat = {
            "national_form_score": nat_block.get("national_form_score"),
            "national_h2h_score": nat_block.get("national_h2h_score"),
            "injury_impact_score": nat_block.get("injury_impact_score"),
            "consensus_strength_score": nat_block.get("consensus_strength_score"),
            "version": nat_block.get("version"),
            "data_coverage": nat_block.get("data_coverage"),
        }
        internal_conf = getattr(pred, "confidence_score", None)
    except Exception as e:
        internal_conf = None
        nat = {"internal_error": str(e)}

    results.append({
        "fixture_id": fid,
        "label": label,
        "api_confidence": d.get("confidence"),
        "internal_confidence": internal_conf,
        "no_bet": d.get("no_bet"),
        "safe_pick": d.get("safe_pick"),
        "value_pick": d.get("value_pick"),
        "aggressive_pick": d.get("aggressive_pick"),
        "prediction": d.get("prediction"),
        "data_quality": d.get("data_quality"),
        "national_team_intelligence": nat,
        "status": d.get("status"),
    })

# find no_bet=false
try:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    repo = FootballIntelligenceRepository()
    for r in repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=30):
        fid = int(r["fixture_id"])
        if fid in {x[0] for x in fixtures}:
            continue
        d = predict(fid)
        if not d.get("no_bet", True):
            results.append({"fixture_id": fid, "label": "no_bet=false", "api_confidence": d.get("confidence"), "no_bet": False})
            break
except Exception:
    pass

print(json.dumps(results, indent=2))
PY
> "$OUT"
echo "Wrote $OUT"
