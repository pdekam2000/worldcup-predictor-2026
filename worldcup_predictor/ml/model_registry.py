"""Persist and load trained ML models."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

DEFAULT_ML_DIR = Path("data/ml")


class ModelRegistry:
    def __init__(self, root: Path | str = DEFAULT_ML_DIR) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, market: str, competition_key: str | None) -> Path:
        suffix = competition_key or "global"
        safe = suffix.replace("/", "_")
        return self._root / f"{safe}_{market}.pkl"

    def save(self, market: str, model_type: str, model: Any, *, competition_key: str | None = None) -> Path:
        path = self._path(market, competition_key)
        payload = {"model_type": model_type, "model": model, "competition_key": competition_key}
        path.write_bytes(pickle.dumps(payload))
        meta = {
            "market": market,
            "model_type": model_type,
            "competition_key": competition_key,
            "path": str(path),
        }
        (self._root / f"{path.stem}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def load(self, market: str, *, competition_key: str | None = None) -> tuple[Any, str] | None:
        path = self._path(market, competition_key)
        if not path.exists():
            path = self._path(market, None)
        if not path.exists():
            return None
        payload = pickle.loads(path.read_bytes())
        return payload["model"], payload["model_type"]

    def list_models(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for meta_path in self._root.glob("*.meta.json"):
            try:
                models.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return models
