"""National team names → flag visuals (images + small initials fallback)."""

from __future__ import annotations

import html
import re
import unicodedata

# flagcdn.com codes (ISO 3166-1 alpha-2 or supported subnational codes)
FLAG_CODE_BY_CANONICAL: dict[str, str] = {
    "australia": "au",
    "bosnia": "ba",
    "brazil": "br",
    "canada": "ca",
    "czechia": "cz",
    "ecuador": "ec",
    "germany": "de",
    "haiti": "ht",
    "japan": "jp",
    "mexico": "mx",
    "morocco": "ma",
    "paraguay": "py",
    "qatar": "qa",
    "scotland": "gb-sct",
    "south_africa": "za",
    "south_korea": "kr",
    "switzerland": "ch",
    "turkey": "tr",
    "united_states": "us",
    "curacao": "cw",
    "netherlands": "nl",
    "spain": "es",
    "france": "fr",
    "england": "gb-eng",
    "wales": "gb-wls",
    "ivory_coast": "ci",
    "tunisia": "tn",
    "sweden": "se",
    "egypt": "eg",
    "belgium": "be",
    "portugal": "pt",
    "croatia": "hr",
    "serbia": "rs",
    "poland": "pl",
    "ukraine": "ua",
    "iran": "ir",
    "saudi_arabia": "sa",
    "argentina": "ar",
    "colombia": "co",
    "uruguay": "uy",
    "chile": "cl",
    "peru": "pe",
    "costa_rica": "cr",
    "panama": "pa",
    "jamaica": "jm",
    "honduras": "hn",
    "cape_verde": "cv",
    "new_zealand": "nz",
    "north_macedonia": "mk",
    "northern_ireland": "gb-nir",
    "uae": "ae",
}

# Aliases → canonical key (exact normalized names only)
ALIAS_TO_CANONICAL: dict[str, str] = {
    "turkiye": "turkey",
    "turkey": "turkey",
    "tuerkiye": "turkey",
    "usa": "united_states",
    "united states": "united_states",
    "united states of america": "united_states",
    "u s a": "united_states",
    "korea republic": "south_korea",
    "south korea": "south_korea",
    "republic of korea": "south_korea",
    "korea": "south_korea",
    "czech republic": "czechia",
    "czechia": "czechia",
    "bosnia and herzegovina": "bosnia",
    "bosnia & herzegovina": "bosnia",
    "bosnia": "bosnia",
    "scotland": "scotland",
    "haiti": "haiti",
    "australia": "australia",
    "türkiye": "turkey",
    "curaçao": "curacao",
    "curacao": "curacao",
    "cape verde": "cape_verde",
    "cape verde islands": "cape_verde",
    "ivory coast": "ivory_coast",
    "cote d'ivoire": "ivory_coast",
    "côte d'ivoire": "ivory_coast",
    "south africa": "south_africa",
    "saudi arabia": "saudi_arabia",
    "new zealand": "new_zealand",
    "north macedonia": "north_macedonia",
    "northern ireland": "northern_ireland",
    "united arab emirates": "uae",
}

# Small initials when no flag code (never show raw 2-letter ISO as large text)
INITIALS_BY_CANONICAL: dict[str, str] = {
    "scotland": "SCO",
    "england": "ENG",
    "wales": "WAL",
    "northern_ireland": "NIR",
    "united_states": "USA",
    "south_korea": "KOR",
    "czechia": "CZE",
    "bosnia": "BIH",
    "ivory_coast": "CIV",
    "curacao": "CUW",
    "cape_verde": "CPV",
    "new_zealand": "NZL",
    "north_macedonia": "MKD",
    "uae": "UAE",
    "turkey": "TUR",
    "haiti": "HAI",
    "australia": "AUS",
}


def normalize_team_name(name: str) -> str:
    """Normalize team name for lookup (lowercase, no accents, collapsed spaces)."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s&'-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _canonical_key(team_name: str) -> str | None:
    key = normalize_team_name(team_name)
    if not key:
        return None
    if key in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[key]
    underscored = key.replace(" ", "_").replace("&", "and").replace("-", "_")
    underscored = re.sub(r"_+", "_", underscored).strip("_")
    if underscored in FLAG_CODE_BY_CANONICAL:
        return underscored
    return ALIAS_TO_CANONICAL.get(key)


def flag_code_for_team(team_name: str, *, country_hint: str | None = None) -> str | None:
    canonical = _canonical_key(team_name)
    if canonical and canonical in FLAG_CODE_BY_CANONICAL:
        return FLAG_CODE_BY_CANONICAL[canonical]
    if country_hint:
        hint_canonical = _canonical_key(country_hint)
        if hint_canonical and hint_canonical in FLAG_CODE_BY_CANONICAL:
            return FLAG_CODE_BY_CANONICAL[hint_canonical]
    return None


def initials_for_team(team_name: str) -> str:
    canonical = _canonical_key(team_name)
    if canonical and canonical in INITIALS_BY_CANONICAL:
        return INITIALS_BY_CANONICAL[canonical]
    if canonical and canonical in FLAG_CODE_BY_CANONICAL:
        return FLAG_CODE_BY_CANONICAL[canonical].upper().replace("-", "")[:3]
    parts = [p for p in re.split(r"\s+", team_name.strip()) if p]
    if len(parts) >= 2:
        return "".join(p[0].upper() for p in parts[:3])[:3]
    return (team_name[:3] or "?").upper()


def flag_image_url(code: str, *, width: int = 160) -> str:
    return f"https://flagcdn.com/w{width}/{code}.png"


def flag_html_for_team(team_name: str, *, country_hint: str | None = None) -> str:
    """Return HTML for flag image or small initials badge — never large ISO letters."""
    safe_name = html.escape(team_name)
    code = flag_code_for_team(team_name, country_hint=country_hint)
    if code:
        url = flag_image_url(code)
        return (
            f'<img src="{url}" alt="{safe_name} flag" class="imc-flag-img" '
            f'loading="lazy" title="{safe_name}" />'
        )
    initials = html.escape(initials_for_team(team_name))
    return f'<span class="imc-flag-initials" title="{safe_name}">{initials}</span>'


def team_flag(team_name: str, *, country_hint: str | None = None) -> str:
    """Legacy string API — returns initials only (prefer flag_html_for_team in cards)."""
    return initials_for_team(team_name)


def iso_for_team(team_name: str, *, country_hint: str | None = None) -> str | None:
    code = flag_code_for_team(team_name, country_hint=country_hint)
    if not code:
        return None
    return code.split("-")[0].upper()
