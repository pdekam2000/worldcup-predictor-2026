#!/usr/bin/env python3
import os
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
os.chdir(ROOT)
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("ENV_FILE", str(ROOT / ".env.production"))

print("full_day", (ROOT / "scripts/run_owner_full_day_predictions.py").is_file())
print("drain", (ROOT / "worldcup_predictor/owner_daily/pipeline/drain_runner.py").is_file())
from worldcup_predictor.config.settings import get_settings

s = get_settings()
print("api", bool(s.api_football_configured))
print("db", s.sqlite_path)
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime

bootstrap_gpt_actions_runtime()
print("canonical", mcp_runtime.model_status().get("canonical_pipeline_ready"))
