"""Daily picks API endpoint."""
from __future__ import annotations

import json
from datetime import date as date_cls
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["daily-picks"])


@router.get("/daily-picks")
def get_daily_picks(date: str | None = None):
    target = date or str(date_cls.today())
    path = Path(f"artifacts/daily_picks_{target}.json")
    if not path.exists():
        return {"picks": [], "date": target, "error": "No picks file found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        return {"picks": [], "date": target, "error": str(e)}
