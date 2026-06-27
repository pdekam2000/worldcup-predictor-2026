/**
 * Central image URL resolver — team logos, competition crests, country flags.
 * Accepts all known provider field variants; never returns broken/empty URLs.
 */

import { flagCodeForTeam, flagImageUrl, initialsForTeam } from "@/lib/teamFlags";

const COMPETITION_LOGOS = {
  world_cup_2026: "https://media.api-sports.io/football/leagues/1.png",
  champions_league: "https://media.api-sports.io/football/leagues/2.png",
  premier_league: "https://media.api-sports.io/football/leagues/39.png",
  la_liga: "https://media.api-sports.io/football/leagues/140.png",
  serie_a: "https://media.api-sports.io/football/leagues/135.png",
  bundesliga: "https://media.api-sports.io/football/leagues/78.png",
  ligue_1: "https://media.api-sports.io/football/leagues/61.png",
  europa_league: "https://media.api-sports.io/football/leagues/3.png",
};

const LOGO_FIELD_KEYS = [
  "logo",
  "logo_url",
  "image_path",
  "image_url",
  "crest",
  "crest_url",
  "team_logo",
  "participant_image",
];

function pickFirstUrl(source) {
  if (!source) return null;
  if (typeof source === "string") return resolveSafeImageUrl(source);
  if (typeof source !== "object") return null;
  for (const key of LOGO_FIELD_KEYS) {
    const v = source[key];
    const url = resolveSafeImageUrl(v);
    if (url) return url;
  }
  if (source.image_path) return resolveSafeImageUrl(source.image_path);
  if (Array.isArray(source.participants)) {
    for (const p of source.participants) {
      const url = pickFirstUrl(p);
      if (url) return url;
    }
  }
  return null;
}

/** Normalize relative / protocol-relative / Sportmonks / API-Football paths. */
export function resolveSafeImageUrl(value) {
  if (value == null) return null;
  const s = String(value).trim();
  if (!s || s === "null" || s === "undefined" || s === "None") return null;
  if (s.startsWith("//")) return `https:${s}`;
  if (s.startsWith("http://") || s.startsWith("https://")) return s;
  if (s.startsWith("/")) return null;
  if (s.startsWith("images/") || s.includes("sportmonks.com/images")) {
    const path = s.includes("sportmonks.com") ? s.replace(/^https?:\/\//, "") : `cdn.sportmonks.com/${s.replace(/^\/+/, "")}`;
    return `https://${path.replace(/^\/+/, "")}`;
  }
  if (s.includes("cdn.sportmonks.com") || s.includes("api-sports.io")) {
    return s.startsWith("http") ? s : `https://${s.replace(/^\/+/, "")}`;
  }
  return null;
}

export function getTeamInitialsFallback(teamName) {
  return initialsForTeam(teamName || "?");
}

export function resolveCountryFlag(countryOrTeam, countryHint = null) {
  const code = flagCodeForTeam(countryOrTeam, countryHint);
  return code ? flagImageUrl(code, 96) : null;
}

export function apiFootballTeamLogoUrl(teamId) {
  const id = Number(teamId);
  if (!id || Number.isNaN(id) || id <= 0) return null;
  return `https://media.api-sports.io/football/teams/${id}.png`;
}

export function resolveTeamLogo(teamOrRow, { side = null } = {}) {
  if (!teamOrRow) return null;
  if (typeof teamOrRow === "string") return resolveSafeImageUrl(teamOrRow);
  if (side === "home") {
    return (
      resolveSafeImageUrl(teamOrRow.home_team_logo) ||
      apiFootballTeamLogoUrl(teamOrRow.home_team_id) ||
      pickFirstUrl(teamOrRow.home) ||
      pickFirstUrl(teamOrRow.participants?.find?.((p) => p.meta?.location === "home"))
    );
  }
  if (side === "away") {
    return (
      resolveSafeImageUrl(teamOrRow.away_team_logo) ||
      apiFootballTeamLogoUrl(teamOrRow.away_team_id) ||
      pickFirstUrl(teamOrRow.away) ||
      pickFirstUrl(teamOrRow.participants?.find?.((p) => p.meta?.location === "away"))
    );
  }
  return (
    pickFirstUrl(teamOrRow) ||
    resolveSafeImageUrl(teamOrRow.logo_url) ||
    resolveSafeImageUrl(teamOrRow.logo) ||
    resolveSafeImageUrl(teamOrRow.image_path) ||
    resolveSafeImageUrl(teamOrRow.crest_url)
  );
}

export function resolveCompetitionLogo(competition) {
  if (!competition) return null;
  const key = typeof competition === "string" ? competition : competition.key || competition.competition_key;
  const fromRow =
    pickFirstUrl(competition) ||
    resolveSafeImageUrl(competition.logo_url) ||
    resolveSafeImageUrl(competition.logo) ||
    resolveSafeImageUrl(competition.competition_logo) ||
    resolveSafeImageUrl(competition.league?.logo);
  if (fromRow) return fromRow;
  if (key && COMPETITION_LOGOS[key]) return COMPETITION_LOGOS[key];
  return null;
}

export function resolveTeamVisual(teamName, { logoUrl = null, countryHint = null, flagWidth = 96, teamId = null } = {}) {
  const safeLogo =
    resolveSafeImageUrl(logoUrl) ||
    apiFootballTeamLogoUrl(teamId) ||
    resolveTeamLogo({ logo_url: logoUrl, home_team_id: teamId });
  const flagCode = flagCodeForTeam(teamName, countryHint);
  return {
    logoUrl: safeLogo,
    flagCode,
    flagUrl: flagCode ? flagImageUrl(flagCode, flagWidth) : null,
    initials: getTeamInitialsFallback(teamName),
  };
}

export function competitionBadgeLabel(competition) {
  if (!competition) return "⚽";
  const key = competition.key || competition.competition_key;
  const map = {
    world_cup_2026: "WC",
    premier_league: "PL",
    la_liga: "LL",
    serie_a: "SA",
    bundesliga: "BL",
    ligue_1: "L1",
    champions_league: "UCL",
  };
  if (key && map[key]) return map[key];
  const name = competition.name || competition.competition_name || "";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .join("")
    .slice(0, 3)
    .toUpperCase() || "⚽";
}
