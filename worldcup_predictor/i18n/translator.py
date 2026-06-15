from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

Locale = Literal["en", "de", "fa", "sr", "bs", "hr"]
SUPPORTED_LOCALES: tuple[Locale, ...] = ("en", "de", "fa", "sr", "bs", "hr")

_LOCALES_DIR = Path(__file__).parent / "locales"


class Translator:
    """Lightweight JSON-based i18n for CLI and agent output."""

    def __init__(self, locale: Locale = "en") -> None:
        self._locale = locale
        self._catalogs = {loc: self._load_catalog(loc) for loc in SUPPORTED_LOCALES}

    @staticmethod
    def _load_catalog(locale: Locale) -> dict[str, str]:
        en_path = _LOCALES_DIR / "en.json"
        with en_path.open(encoding="utf-8") as handle:
            en_catalog: dict[str, str] = json.load(handle)
        if locale == "en":
            return en_catalog
        path = _LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            return dict(en_catalog)
        with path.open(encoding="utf-8") as handle:
            overlay: dict[str, str] = json.load(handle)
        return {**en_catalog, **overlay}

    @property
    def locale(self) -> Locale:
        return self._locale

    def t(self, key: str, locale: Locale | None = None) -> str:
        loc = locale or self._locale
        catalog = self._catalogs.get(loc, self._catalogs["en"])
        if key in catalog:
            return catalog[key]
        return self._catalogs["en"].get(key, key)


@lru_cache
def get_translator(locale: Locale = "en") -> Translator:
    return Translator(locale=locale)
