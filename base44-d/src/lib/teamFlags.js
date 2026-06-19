/**
 * National team name → flag CDN code (mirrors worldcup_predictor/ui/country_flags.py).
 * No API calls — static mapping + flagcdn.com images.
 */

const FLAG_CODE_BY_CANONICAL = {
  australia: "au",
  bosnia: "ba",
  brazil: "br",
  canada: "ca",
  czechia: "cz",
  ecuador: "ec",
  germany: "de",
  haiti: "ht",
  japan: "jp",
  mexico: "mx",
  morocco: "ma",
  paraguay: "py",
  qatar: "qa",
  scotland: "gb-sct",
  south_africa: "za",
  south_korea: "kr",
  switzerland: "ch",
  turkey: "tr",
  united_states: "us",
  curacao: "cw",
  netherlands: "nl",
  spain: "es",
  senegal: "sn",
  cameroon: "cm",
  ghana: "gh",
  nigeria: "ng",
  algeria: "dz",
  france: "fr",
  england: "gb-eng",
  wales: "gb-wls",
  ivory_coast: "ci",
  tunisia: "tn",
  sweden: "se",
  egypt: "eg",
  belgium: "be",
  portugal: "pt",
  croatia: "hr",
  serbia: "rs",
  poland: "pl",
  ukraine: "ua",
  iran: "ir",
  saudi_arabia: "sa",
  argentina: "ar",
  colombia: "co",
  uruguay: "uy",
  chile: "cl",
  peru: "pe",
  costa_rica: "cr",
  panama: "pa",
  jamaica: "jm",
  honduras: "hn",
  cape_verde: "cv",
  new_zealand: "nz",
  north_macedonia: "mk",
  northern_ireland: "gb-nir",
  uae: "ae",
};

const ALIAS_TO_CANONICAL = {
  turkiye: "turkey",
  turkey: "turkey",
  tuerkiye: "turkey",
  türkiye: "turkey",
  usa: "united_states",
  "united states": "united_states",
  "united states of america": "united_states",
  "u s a": "united_states",
  "korea republic": "south_korea",
  "south korea": "south_korea",
  "republic of korea": "south_korea",
  korea: "south_korea",
  "czech republic": "czechia",
  czechia: "czechia",
  "bosnia and herzegovina": "bosnia",
  "bosnia & herzegovina": "bosnia",
  bosnia: "bosnia",
  scotland: "scotland",
  haiti: "haiti",
  australia: "australia",
  curaçao: "curacao",
  curacao: "curacao",
  "cape verde": "cape_verde",
  "cape verde islands": "cape_verde",
  "ivory coast": "ivory_coast",
  "cote d'ivoire": "ivory_coast",
  "côte d'ivoire": "ivory_coast",
  "south africa": "south_africa",
  "saudi arabia": "saudi_arabia",
  "new zealand": "new_zealand",
  "north macedonia": "north_macedonia",
  senegal: "senegal",
  "senegal republic": "senegal",
  "republic of senegal": "senegal",
  "united arab emirates": "uae",
};

const INITIALS_BY_CANONICAL = {
  scotland: "SCO",
  england: "ENG",
  wales: "WAL",
  northern_ireland: "NIR",
  united_states: "USA",
  south_korea: "KOR",
  czechia: "CZE",
  bosnia: "BIH",
  ivory_coast: "CIV",
  curacao: "CUW",
  cape_verde: "CPV",
  new_zealand: "NZL",
  north_macedonia: "MKD",
  uae: "UAE",
  turkey: "TUR",
  senegal: "SEN",
  cameroon: "CMR",
  ghana: "GHA",
  nigeria: "NGA",
  algeria: "ALG",
};

function normalizeTeamName(name) {
  if (!name) return "";
  return name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/[^\w\s&'-]/g, " ")
    .replace(/\s+/g, " ");
}

function canonicalKey(teamName) {
  const key = normalizeTeamName(teamName);
  if (!key) return null;
  if (ALIAS_TO_CANONICAL[key]) return ALIAS_TO_CANONICAL[key];
  const underscored = key.replace(/ /g, "_").replace(/&/g, "and").replace(/-/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
  if (FLAG_CODE_BY_CANONICAL[underscored]) return underscored;
  return ALIAS_TO_CANONICAL[key] || null;
}

export function flagCodeForTeam(teamName, countryHint = null) {
  const canonical = canonicalKey(teamName);
  if (canonical && FLAG_CODE_BY_CANONICAL[canonical]) {
    return FLAG_CODE_BY_CANONICAL[canonical];
  }
  if (countryHint) {
    const hintCanonical = canonicalKey(countryHint);
    if (hintCanonical && FLAG_CODE_BY_CANONICAL[hintCanonical]) {
      return FLAG_CODE_BY_CANONICAL[hintCanonical];
    }
  }
  return null;
}

export function initialsForTeam(teamName) {
  const canonical = canonicalKey(teamName);
  if (canonical && INITIALS_BY_CANONICAL[canonical]) {
    return INITIALS_BY_CANONICAL[canonical];
  }
  if (canonical && FLAG_CODE_BY_CANONICAL[canonical]) {
    return FLAG_CODE_BY_CANONICAL[canonical].toUpperCase().replace(/-/g, "").slice(0, 3);
  }
  const parts = teamName.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return parts
      .slice(0, 3)
      .map((p) => p[0].toUpperCase())
      .join("")
      .slice(0, 3);
  }
  return (teamName.slice(0, 3) || "?").toUpperCase();
}

export function flagImageUrl(code, width = 80) {
  return `https://flagcdn.com/w${width}/${code}.png`;
}

export function resolveTeamVisual(teamName, { logoUrl = null, countryHint = null } = {}) {
  const safeLogo = logoUrl && String(logoUrl).startsWith("http") ? logoUrl : null;
  const flagCode = flagCodeForTeam(teamName, countryHint);
  return {
    logoUrl: safeLogo,
    flagCode,
    flagUrl: flagCode ? flagImageUrl(flagCode, 80) : null,
    initials: initialsForTeam(teamName),
  };
}
