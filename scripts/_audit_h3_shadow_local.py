#!/usr/bin/env python3
"""Local shadow audit helper for HOTFIX H3."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService, PREDICTIONS_PATH, EVALUATIONS_PATH, ROOT_CAUSE_PATH
from worldcup_predictor.config.settings import get_settings

s = get_settings()
print("settings.autonomous_platform_enabled", s.autonomous_platform_enabled)
print("settings.autonomous_dry_run", s.autonomous_dry_run)

for p in [PREDICTIONS_PATH, EVALUATIONS_PATH, ROOT_CAUSE_PATH]:
    n = sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()) if p.is_file() else 0
    print(f"jsonl {p.name}: exists={p.is_file()} rows={n}")

print("preview_summary:", json.dumps(EliteShadowPreviewService().preview_summary(), indent=2))

db = ROOT / "data" / "football_intelligence.db"
if db.is_file():
    conn = sqlite3.connect(db)
    for t in ("autonomous_prediction_snapshots", "autonomous_prediction_evaluations", "fixtures", "predops_snapshots"):
        try:
            c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"sqlite {t}: {c}")
        except Exception as exc:
            print(f"sqlite {t}: ERR {exc}")
    try:
        rows = conn.execute(
            "SELECT engine, COUNT(*) FROM autonomous_prediction_snapshots GROUP BY engine"
        ).fetchall()
        print("sqlite autonomous by engine:", dict(rows))
    except Exception as exc:
        print("sqlite autonomous by engine ERR", exc)
    conn.close()
