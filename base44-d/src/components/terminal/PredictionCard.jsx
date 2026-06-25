import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import MatchStatusBadge from "./MatchStatusBadge";
import TierBadge from "./TierBadge";

function formatMatchTime(dateStr) {
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

function pick1x2Label(v) {
  const s = String(v || "").toLowerCase();
  if (s === "home" || s === "1") return "Home Win";
  if (s === "draw" || s === "x") return "Draw";
  if (s === "away" || s === "2") return "Away Win";
  return v || "—";
}

function firstGoalLabel(pick) {
  if (!pick) return null;
  if (pick.first_goal_team === "home") return `${pick.home_team || "Home"} scores first`;
  if (pick.first_goal_team === "away") return `${pick.away_team || "Away"} scores first`;
  if (pick.first_goal_team === "none") return "No clear first scorer";
  return null;
}

/**
 * Unified prediction card — uses real API fields only.
 */
export default function PredictionCard({
  match,
  pick,
  variant = "match",
  href,
  featured = false,
  className,
}) {
  const data = { ...match, ...pick };
  const fixtureId = data.id || data.fixture_id;
  const linkTo = href || (fixtureId ? `/prediction/${fixtureId}` : null);
  const { date, time } = formatMatchTime(data.match_date || data.kickoff_utc);
  const hybrid = data.hybrid_confidence;
  const teamTier = hybrid?.team?.tier;
  const mainPrediction =
    variant === "goal_timing"
      ? firstGoalLabel(data) || data.first_goal_time_range
      : pick1x2Label(data.prediction_1x2 || data.prediction || data.predicted_1x2);
  const trustLabel = hybrid?.team?.label || data.trust_label || "Model edge";
  const winrateHint =
    data.win_rate != null
      ? `${Math.round(data.win_rate)}% market winrate`
      : data.result
        ? String(data.result).charAt(0).toUpperCase() + String(data.result).slice(1)
        : null;

  const inner = (
    <div
      className={cn(
        "terminal-card p-4 sm:p-5 transition-all duration-200 group",
        featured && "terminal-card-glow border-[#00E676]/20",
        linkTo && "hover:border-[#00E676]/25 hover:shadow-[0_12px_48px_rgba(0,230,118,0.08)] cursor-pointer",
        className
      )}
    >
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[#94A3B8] truncate">
            {data.league || data.competition_key?.replace(/_/g, " ") || "Match"}
          </span>
        </div>
        <MatchStatusBadge status={data.status} bucket={data.bucket} />
      </div>

      <MatchTeamsRow
        homeTeam={data.home_team || "Home"}
        awayTeam={data.away_team || "Away"}
        homeLogo={data.home_team_logo}
        awayLogo={data.away_team_logo}
        countryHint={data.country || data.league}
        size="md"
        className="mb-4"
      />

      <div className="flex items-center gap-3 text-xs text-[#94A3B8] mb-4">
        <span>{date}</span>
        <span className="text-white/20">·</span>
        <span className="font-mono text-[#F8FAFC]">{time}</span>
      </div>

      <div className="rounded-xl bg-black/25 border border-white/[0.05] p-3 mb-4">
        <p className="text-[10px] uppercase tracking-wider text-[#94A3B8] mb-1">Main pick</p>
        <p className="text-base font-semibold text-[#F8FAFC] leading-snug">{mainPrediction || "—"}</p>
        {variant === "goal_timing" && data.first_goal_time_range && (
          <p className="text-xs text-[#94A3B8] mt-1">
            Window: {data.first_goal_time_range}
            {data.display_estimated_first_goal_minute != null &&
              ` · ~${Math.round(data.display_estimated_first_goal_minute)}'`}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        {teamTier && <TierBadge tier={teamTier} label="Trust" />}
        {hybrid?.range?.tier && <TierBadge tier={hybrid.range.tier} label="Range" compact />}
        <span className="text-xs text-[#94A3B8]">{trustLabel}</span>
      </div>

      {winrateHint && (
        <div className="flex items-center gap-1.5 text-xs text-[#00E676]/90 mb-4">
          <TrendingUp className="w-3.5 h-3.5" />
          {winrateHint}
        </div>
      )}

      {linkTo && (
        <div className="flex items-center justify-between pt-3 border-t border-white/[0.06]">
          <span className="text-sm font-medium text-[#00E676] group-hover:text-[#00E676]/90">
            View Analysis
          </span>
          <ArrowRight className="w-4 h-4 text-[#00E676] opacity-70 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
        </div>
      )}
    </div>
  );

  if (linkTo) {
    return <Link to={linkTo} className="block">{inner}</Link>;
  }
  return inner;
}
