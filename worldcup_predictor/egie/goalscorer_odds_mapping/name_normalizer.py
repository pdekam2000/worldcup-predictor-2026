"""Player name normalization for goalscorer odds mapping."""

from __future__ import annotations

import re
import unicodedata

_ALIASES = {
    "jr": "junior",
    "sr": "senior",
    "mohamed": "mohammed",
    "mohammad": "mohammed",
    "alexandre": "alexander",
    "gabriel jesus": "gabriel jesus",
}

_SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv)\.?$", re.I)


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    text = strip_accents(str(name or "").strip().lower())
    text = _SUFFIX_RE.sub("", text)
    text = re.sub(r"[^a-z0-9\s\-']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split()
    if not tokens:
        return ""
    if len(tokens) >= 2:
        # "lastname firstname" -> also store last token emphasis
        pass
    alias_key = " ".join(tokens)
    return _ALIASES.get(alias_key, alias_key)


def name_tokens(name: str) -> set[str]:
    norm = normalize_name(name)
    return {t for t in norm.split() if len(t) > 1}


def last_name(name: str) -> str:
    tokens = normalize_name(name).split()
    return tokens[-1] if tokens else ""


def first_initial_last(name: str) -> str:
    tokens = normalize_name(name).split()
    if len(tokens) < 2:
        return normalize_name(name)
    return f"{tokens[0][0]} {tokens[-1]}"


def compact_key(name: str) -> str:
    return normalize_name(name).replace(" ", "")
