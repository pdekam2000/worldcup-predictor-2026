#!/usr/bin/env python3
import json, sys
from pathlib import Path
p = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/historical_odds_pattern_175_390_440.json")
r = json.loads(p.read_text(encoding="utf-8"))
print("PHASE3", json.dumps(r["phase3_close"]["stats"], indent=2))
print("TOP15", json.dumps(r["phase8_final"]["top15_normalized_close"], indent=2))
print("PHASE4", json.dumps({k: r["phase4_nearest_neighbors"][k]["comparison_row"] for k in r["phase4_nearest_neighbors"]}, indent=2))
print("PHASE6", json.dumps(r["phase6_time_segments"], indent=2))
print("PHASE7", json.dumps(r["phase7_competition_segments"], indent=2))
print("PHASE8", json.dumps(r["phase8_final"], indent=2))
