#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
sys.path.insert(0, str(ROOT))

from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService

svc = EliteShadowPreviewService()
summary = svc.preview_summary()
preds = svc.list_predictions(limit=5)
evals = svc.list_evaluations(limit=5)
rc = svc.list_root_cause(limit=5)

print("SUMMARY", json.dumps(summary, indent=2))
print("PREDICTIONS_TOTAL", preds.get("total"))
print("EVALUATIONS_TOTAL", evals.get("total"))
print("ROOT_CAUSE_TOTAL", rc.get("total"))
print("DATA_AVAILABLE", summary.get("data_available"))
print("EMPTY_REASON", summary.get("empty_reason"))
