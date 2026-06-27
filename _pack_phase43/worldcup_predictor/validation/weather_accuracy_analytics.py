"""Weather-conditioned accuracy tracking structures — Phase 43 (no retraining)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

WeatherBucket = Literal["rain", "wind", "extreme_heat", "extreme_cold", "normal"]

DEFAULT_WEATHER_ACCURACY_PATH = Path("data/validation/weather_accuracy_buckets.jsonl")


@dataclass
class WeatherConditionBucket:
    condition: WeatherBucket
    total_predictions: int = 0
    correct: int = 0
    wrong: int = 0
    pending: int = 0

    @property
    def settled(self) -> int:
        return self.correct + self.wrong

    @property
    def accuracy(self) -> float | None:
        if self.settled <= 0:
            return None
        return round(self.correct / self.settled, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "total_predictions": self.total_predictions,
            "correct": self.correct,
            "wrong": self.wrong,
            "pending": self.pending,
            "accuracy": self.accuracy,
        }


@dataclass
class WeatherAccuracyRecord:
    fixture_id: int
    prediction_id: str | None
    recorded_at: str
    weather_risk_level: str | None
    rain_probability: float | None
    wind_speed_kmh: float | None
    temperature_c: float | None
    buckets: list[WeatherBucket] = field(default_factory=list)
    result_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_weather_buckets(
    *,
    rain_probability: float | None,
    wind_speed_kmh: float | None,
    temperature_c: float | None,
    wind_gust_kmh: float | None = None,
) -> list[WeatherBucket]:
    buckets: list[WeatherBucket] = []
    rain = float(rain_probability or 0.0)
    wind = max(float(wind_speed_kmh or 0.0), float(wind_gust_kmh or 0.0))
    temp = temperature_c if temperature_c is not None else 22.0

    if rain >= 0.4:
        buckets.append("rain")
    if wind >= 25:
        buckets.append("wind")
    if temp >= 30:
        buckets.append("extreme_heat")
    if temp <= 5:
        buckets.append("extreme_cold")
    if not buckets:
        buckets.append("normal")
    return buckets


class WeatherAccuracyTracker:
    """Append-only JSONL tracker for future weather-conditioned learning."""

    def __init__(self, path: Path | str = DEFAULT_WEATHER_ACCURACY_PATH) -> None:
        self._path = Path(path)

    def record_prediction(
        self,
        *,
        fixture_id: int,
        prediction_id: str | None,
        weather: dict[str, Any] | None,
        result_status: str | None = None,
    ) -> WeatherAccuracyRecord:
        wx = weather or {}
        buckets = classify_weather_buckets(
            rain_probability=_float(wx.get("rain_probability")),
            wind_speed_kmh=_float(wx.get("wind_speed_kmh")),
            wind_gust_kmh=_float(wx.get("wind_gust_kmh")),
            temperature_c=_float(wx.get("temperature_c")),
        )
        record = WeatherAccuracyRecord(
            fixture_id=int(fixture_id),
            prediction_id=prediction_id,
            recorded_at=_utc_now(),
            weather_risk_level=str(wx.get("weather_risk_level") or "") or None,
            rain_probability=_float(wx.get("rain_probability")),
            wind_speed_kmh=_float(wx.get("wind_speed_kmh")),
            temperature_c=_float(wx.get("temperature_c")),
            buckets=buckets,
            result_status=result_status,
        )
        self._append(record)
        return record

    def aggregate_buckets(self) -> list[WeatherConditionBucket]:
        totals: dict[WeatherBucket, WeatherConditionBucket] = {
            "rain": WeatherConditionBucket("rain"),
            "wind": WeatherConditionBucket("wind"),
            "extreme_heat": WeatherConditionBucket("extreme_heat"),
            "extreme_cold": WeatherConditionBucket("extreme_cold"),
            "normal": WeatherConditionBucket("normal"),
        }
        for row in self.load_all():
            status = str(row.get("result_status") or "pending").lower()
            for bucket in row.get("buckets") or []:
                key = bucket if bucket in totals else "normal"
                block = totals[key]
                block.total_predictions += 1
                if status == "correct":
                    block.correct += 1
                elif status == "wrong":
                    block.wrong += 1
                else:
                    block.pending += 1
        return list(totals.values())

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return rows

    def summary(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "records": len(self.load_all()),
            "buckets": [b.to_dict() for b in self.aggregate_buckets()],
            "updated_at": _utc_now(),
            "learning_ready": False,
            "note": "Structure-only tracker — no model retraining in Phase 43.",
        }

    def _append(self, record: WeatherAccuracyRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
