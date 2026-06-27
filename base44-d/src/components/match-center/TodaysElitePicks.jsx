import React from "react";
import { motion } from "framer-motion";
import { Plus, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import { formatKickoff } from "@/lib/matchCenterUtils";
import { formatStars } from "@/lib/comboGenerator";
import { useBetSlip } from "@/context/BetSlipContext";
import { Button } from "@/components/ui/button";
import { TerminalCard } from "@/components/terminal";

function aiScoreColor(score) {
  if (score >= 95) return "text-[#00E676]";
  if (score >= 87) return "text-[#7DD3FC]";
  if (score >= 73) return "text-[#FFD166]";
  return "text-[#94A3B8]";
}

export default function TodaysElitePicks({ picks = [] }) {
  const { addLeg } = useBetSlip();

  if (!picks.length) return null;

  const handleAdd = (m) => {
    const s = m.prediction_summary;
    if (!s?.best_pick) return;
    addLeg({
      fixture_id: m.fixture_id || m.id,
      competition_key: m.competition_key,
      home_team: m.home_team,
      away_team: m.away_team,
      market: "best_pick",
      selection: s.best_pick,
      label: s.best_pick,
      confidence: s.confidence,
    });
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-[#00E676]" />
        <h2 className="text-lg font-semibold text-[#F8FAFC]">Today&apos;s Elite Picks</h2>
        <span className="text-xs text-[#64748B]">Top {picks.length}</span>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory -mx-1 px-1">
        {picks.map((m, i) => {
          const s = m.prediction_summary || {};
          const ai = m.ai_match_score || {};
          const { date, time } = formatKickoff(m.match_date);
          const fixtureId = m.fixture_id || m.id;
          return (
            <motion.div
              key={`elite-${fixtureId}`}
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className="snap-start shrink-0 w-[min(100%,320px)]"
            >
              <TerminalCard className="p-4 border-[#00E676]/20 bg-gradient-to-br from-[#00E676]/5 to-transparent h-full">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="text-[10px] uppercase tracking-wide text-[#94A3B8] truncate">
                    {m.competition_emoji} {m.competition_name || m.league}
                  </span>
                  <span className={`text-xs font-bold ${aiScoreColor(ai.score)}`}>
                    {ai.score ?? "—"} {ai.label}
                  </span>
                </div>
                <MatchTeamsRow
                  homeTeam={m.home_team}
                  awayTeam={m.away_team}
                  homeLogo={m.home_team_logo}
                  awayLogo={m.away_team_logo}
                  size="sm"
                  className="mb-2"
                />
                <p className="text-[11px] text-[#94A3B8] mb-1">{date} · {time}</p>
                <p className="text-sm font-semibold text-white truncate mb-1">{s.best_pick || "—"}</p>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-[#94A3B8] mb-3">
                  {s.confidence != null && <span>Conf {s.confidence}%</span>}
                  {s.value_rating && <span>Value {s.value_rating}</span>}
                  <span>{formatStars(s.stars)}</span>
                </div>
                <div className="flex gap-2">
                  <Button type="button" size="sm" className="flex-1 bg-[#00E676]/20 text-[#00E676] hover:bg-[#00E676]/30" onClick={() => handleAdd(m)} disabled={!s.best_pick}>
                    <Plus className="w-3.5 h-3.5 mr-1" /> Add
                  </Button>
                  <Button asChild variant="outline" size="sm" className="border-white/10">
                    <Link to={`/matches/${fixtureId}${m.competition_key ? `?competition=${m.competition_key}` : ""}`}>View</Link>
                  </Button>
                </div>
              </TerminalCard>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
