import React from "react";
import { Sparkles, MapPin, Cloud } from "lucide-react";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import { formatKickoff, fixtureStatusTone } from "@/lib/matchCenterUtils";
import { competitionEmoji, aiScoreFromPrediction, fixtureStatusFromPrediction } from "@/lib/predictionDetailProUtils";

function aiClass(score) {
  if (score >= 95) return "text-[#00E676] border-[#00E676]/30 bg-[#00E676]/10";
  if (score >= 87) return "text-[#7DD3FC] border-[#7DD3FC]/30 bg-[#7DD3FC]/10";
  if (score >= 73) return "text-[#FFD166] border-[#FFD166]/30 bg-[#FFD166]/10";
  return "text-[#94A3B8] border-white/10 bg-white/5";
}

export default function MatchHeaderPro({ prediction, competitionKey, matchMeta }) {
  const kickoff = prediction?.kickoff_utc || prediction?.match_date || matchMeta?.match_date;
  const { date, time } = formatKickoff(kickoff);
  const ai = aiScoreFromPrediction(prediction);
  const statusLabel = fixtureStatusFromPrediction(prediction);
  const weather = prediction?.weather_intelligence;
  const emoji = competitionEmoji(competitionKey || prediction?.competition_key);

  return (
    <section className="rounded-2xl border border-white/[0.06] bg-gradient-to-br from-[#101827] via-[#0d1524] to-[#0B1220] p-5 sm:p-8 backdrop-blur-xl">
      <div className="flex flex-wrap items-center gap-2 mb-4 text-xs text-[#94A3B8]">
        <span className="text-2xl">{emoji}</span>
        <span className="font-semibold uppercase tracking-wide">
          {prediction?.league || prediction?.competition_name || matchMeta?.competition_name || "Competition"}
        </span>
        {prediction?.country && <span>· {prediction.country}</span>}
      </div>

      <MatchTeamsRow
        homeTeam={prediction?.home_team || matchMeta?.home_team}
        awayTeam={prediction?.away_team || matchMeta?.away_team}
        homeLogo={prediction?.home_team_logo || matchMeta?.home_team_logo}
        awayLogo={prediction?.away_team_logo || matchMeta?.away_team_logo}
        homeTeamId={prediction?.home_team_id || matchMeta?.home_team_id}
        awayTeamId={prediction?.away_team_id || matchMeta?.away_team_id}
        countryHint={prediction?.country}
        size="xl"
        className="mb-5"
      />

      <div className="flex flex-wrap gap-2 mb-4">
        <span className={`text-[11px] px-2.5 py-1 rounded-full border ${fixtureStatusTone(statusLabel)}`}>{statusLabel}</span>
        {prediction?.confidence != null && (
          <span className="text-[11px] px-2.5 py-1 rounded-full border text-[#00E676] bg-[#00E676]/10 border-[#00E676]/30 inline-flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Prediction Ready
          </span>
        )}
        <span className={`text-[11px] px-2.5 py-1 rounded-full border font-bold ${aiClass(ai.score)}`}>
          AI {ai.score} · {ai.label}
        </span>
      </div>

      <div className="grid sm:grid-cols-3 gap-3 text-sm">
        <div>
          <p className="text-[10px] uppercase text-[#64748B]">Kickoff</p>
          <p className="text-[#F8FAFC] font-medium">{date}</p>
          <p className="text-[#94A3B8] font-mono">{time}</p>
        </div>
        {(prediction?.venue || matchMeta?.venue) && (
          <div>
            <p className="text-[10px] uppercase text-[#64748B] flex items-center gap-1"><MapPin className="w-3 h-3" /> Venue</p>
            <p className="text-[#F8FAFC]">{prediction?.venue || matchMeta?.venue}</p>
            {(prediction?.city || matchMeta?.city) && <p className="text-xs text-[#64748B]">{prediction?.city || matchMeta?.city}</p>}
          </div>
        )}
        {weather?.available && (
          <div>
            <p className="text-[10px] uppercase text-[#64748B] flex items-center gap-1"><Cloud className="w-3 h-3" /> Weather</p>
            <p className="text-[#F8FAFC] text-sm">{weather.weather_summary || weather.condition || "Available"}</p>
            {weather.temperature_c != null && <p className="text-xs text-[#64748B]">{Math.round(weather.temperature_c)}°C</p>}
          </div>
        )}
      </div>
    </section>
  );
}
