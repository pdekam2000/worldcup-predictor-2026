"""Multilingual team alias + fuzzy matching for manual fixture resolution."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from worldcup_predictor.intelligence.national_team._shared import normalize_team_name

ALIAS_JSON = Path("artifacts/manual_owner_team_aliases.json")

_BUILTIN_ALIASES: dict[str, str] = {
    "dr kongo": "Congo DR",
    "dr congo": "Congo DR",
    "congo dr": "Congo DR",
    "democratic republic of the congo": "Congo DR",
    "drc": "Congo DR",
    "belgien": "Belgium",
    "bosnien herzegowina": "Bosnia & Herzegovina",
    "bosnienherzegowina": "Bosnia & Herzegovina",
    "bosnia herz": "Bosnia & Herzegovina",
    "bosnia and herzegovina": "Bosnia & Herzegovina",
    "spanien": "Spain",
    "osterreich": "Austria",
    "österreich": "Austria",
    "kroatien": "Croatia",
    "schweiz": "Switzerland",
    "algerien": "Algeria",
    "australien": "Australia",
    "agypten": "Egypt",
    "ägypten": "Egypt",
    "argentinien": "Argentina",
    "kap verde": "Cape Verde Islands",
    "cape verde": "Cape Verde Islands",
    "kolumbien": "Colombia",
    "kanada": "Canada",
    "marokko": "Morocco",
    "frankreich": "France",
    "brasilien": "Brazil",
    "norwegen": "Norway",
    "england": "England",
    "senegal": "Senegal",
    "usa": "USA",
    "united states": "USA",
    "ghana": "Ghana",
    "paraguay": "Paraguay",
    "portugal": "Portugal",
}


def load_alias_config() -> dict[str, Any]:
    if ALIAS_JSON.exists():
        try:
            return json.loads(ALIAS_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"aliases": _BUILTIN_ALIASES, "known_knockout_fixture_ids": {}}


def _alias_map() -> dict[str, str]:
    cfg = load_alias_config()
    merged = dict(_BUILTIN_ALIASES)
    merged.update({str(k).lower(): str(v) for k, v in (cfg.get("aliases") or {}).items()})
    return merged


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _alias_key(name: str) -> str:
    key = _strip_accents((name or "").strip().lower())
    key = re.sub(r"[^a-z0-9\s&]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def canonical_team_name(name: str) -> str:
    raw = (name or "").strip()
    amap = _alias_map()
    key = _alias_key(raw)
    key_compact = key.replace(" ", "").replace("&", "")
    if key in amap:
        return amap[key]
    if key_compact in amap:
        return amap[key_compact]
    for alias, canonical in amap.items():
        ak = alias.replace(" ", "")
        if ak == key_compact or alias in key or key in alias:
            return canonical
    return raw


def normalize_for_match(name: str) -> str:
    return normalize_team_name(canonical_team_name(name))


def fixture_pair_key(home: str, away: str) -> str:
    return f"{normalize_for_match(home)}|{normalize_for_match(away)}"


def known_fixture_id(home: str, away: str) -> int | None:
    cfg = load_alias_config()
    mapping = cfg.get("known_knockout_fixture_ids") or {}
    key = fixture_pair_key(home, away)
    val = mapping.get(key)
    if val is not None:
        return int(val)
    # try swapped compact keys
    for k, v in mapping.items():
        if normalize_for_match(k.split("|")[0]) == normalize_for_match(home) and normalize_for_match(
            k.split("|")[1]
        ) == normalize_for_match(away):
            return int(v)
    return None


def teams_match(a: str, b: str) -> bool:
    ca = normalize_for_match(a)
    cb = normalize_for_match(b)
    if ca == cb:
        return True
    if ca in cb or cb in ca:
        return True
    if "cape verde" in ca and "cape verde" in cb:
        return True
    if "bosnia" in ca and "bosnia" in cb:
        return True
    if "congo" in ca and "congo" in cb and "republic" not in ca and "republic" not in cb:
        return True
    return fuzzy_ratio(ca, cb) >= 0.88


def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def score_fixture_pair(
    home_input: str,
    away_input: str,
    db_home: str,
    db_away: str,
) -> float:
    """0-1 confidence that DB row matches requested pair."""
    h_score = fuzzy_ratio(normalize_for_match(home_input), normalize_for_match(db_home))
    a_score = fuzzy_ratio(normalize_for_match(away_input), normalize_for_match(db_away))
    if teams_match(home_input, db_home) and teams_match(away_input, db_away):
        return max(0.92, (h_score + a_score) / 2)
    return (h_score + a_score) / 2
