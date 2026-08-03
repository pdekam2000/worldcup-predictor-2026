"""Unit checks for next-5-days complete prediction packaging."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "next5",
    ROOT / "scripts" / "run_next_5_days_complete_predictions.py",
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mod)


def test_vienna_five_dates_contiguous():
    dates, meta = mod.resolve_dates()
    assert len(dates) == 5
    assert meta["timezone"] == "Europe/Vienna"
    today = datetime.now(ZoneInfo("Europe/Vienna")).date()
    assert dates[0] == today.isoformat()
    assert dates[-1] == (today + timedelta(days=4)).isoformat()


def test_direction_normalization_home_win():
    assert mod._norm_dir("home_win") == "home"
    assert mod._norm_dir("away_win") == "away"
    assert mod._norm_dir("draw") == "draw"
    assert mod._norm_dir("HOME") == "home"
