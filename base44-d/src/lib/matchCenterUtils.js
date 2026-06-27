/** Match Center date / filter helpers */

export function isToday(dateStr) {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const now = new Date();
  return d.toDateString() === now.toDateString();
}

export function isTomorrow(dateStr) {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const t = new Date();
  t.setDate(t.getDate() + 1);
  return d.toDateString() === t.toDateString();
}

export function isWeekend(dateStr) {
  if (!dateStr) return false;
  const day = new Date(dateStr).getDay();
  return day === 0 || day === 6;
}

export function formatKickoff(dateStr) {
  if (!dateStr) return { date: "—", time: "—" };
  try {
    const d = new Date(dateStr);
    return {
      date: d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }),
      time: d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
  } catch {
    return { date: "—", time: "—" };
  }
}

export function statusLabel(bucket, status) {
  const b = String(bucket || status || "").toLowerCase();
  if (b === "live" || ["1h", "ht", "2h", "et", "live"].includes(b)) return "Live";
  if (b === "finished" || b === "ft") return "Finished";
  return "Upcoming";
}

export function applyClientFilters(matches, filters) {
  let rows = [...matches];
  const q = (filters.search || "").trim().toLowerCase();
  if (q) {
    rows = rows.filter(
      (m) =>
        String(m.home_team || "").toLowerCase().includes(q) ||
        String(m.away_team || "").toLowerCase().includes(q) ||
        String(m.league || "").toLowerCase().includes(q) ||
        String(m.competition_name || "").toLowerCase().includes(q)
    );
  }
  if (filters.competitionKey && filters.competitionKey !== "all") {
    rows = rows.filter((m) => m.competition_key === filters.competitionKey);
  }
  if (filters.datePreset === "today") rows = rows.filter((m) => isToday(m.match_date));
  if (filters.datePreset === "tomorrow") rows = rows.filter((m) => isTomorrow(m.match_date));
  if (filters.datePreset === "weekend") rows = rows.filter((m) => isWeekend(m.match_date));
  if (filters.highConfidence) {
    rows = rows.filter((m) => (m.prediction_summary?.confidence || 0) >= 70);
  }
  if (filters.bestValue) {
    rows = rows.filter((m) => {
      const v = String(m.prediction_summary?.value_rating || "").toUpperCase();
      return ["A", "B", "ELITE", "STRONG"].includes(v);
    });
  }
  if (filters.eliteOnly) {
    rows = rows.filter((m) => m.prediction_summary?.is_elite_pick);
  }
  if (filters.liveOnly) rows = rows.filter((m) => m.bucket === "live");
  if (filters.upcomingOnly) rows = rows.filter((m) => m.bucket === "upcoming");
  if (filters.liveSoon) {
    const now = Date.now();
    const twoHours = 2 * 60 * 60 * 1000;
    rows = rows.filter((m) => {
      if (!m.match_date || m.bucket !== "upcoming") return false;
      const t = new Date(m.match_date).getTime();
      return t >= now && t <= now + twoHours;
    });
  }
  if (filters.favoriteTeams?.length) {
    const fav = new Set(filters.favoriteTeams.map((t) => String(t).toLowerCase()));
    rows = rows.filter(
      (m) => fav.has(String(m.home_team || "").toLowerCase()) || fav.has(String(m.away_team || "").toLowerCase())
    );
  }
  if (filters.minAiScore) {
    rows = rows.filter((m) => (m.ai_match_score?.score || 0) >= filters.minAiScore);
  }
  return rows;
}

export function fixtureStatusTone(label) {
  const l = String(label || "").toLowerCase();
  if (l === "live") return "text-red-400 bg-red-500/10";
  if (l === "prediction ready") return "text-[#00E676] bg-[#00E676]/10";
  if (l === "prediction updating") return "text-[#FFD166] bg-[#FFD166]/10";
  if (l === "waiting for lineups") return "text-[#94A3B8] bg-white/5";
  if (l === "evaluated") return "text-[#7DD3FC] bg-[#7DD3FC]/10";
  if (l === "finished") return "text-[#64748B] bg-white/5";
  return "text-[#94A3B8] bg-white/5";
}
