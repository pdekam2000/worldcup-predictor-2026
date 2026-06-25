import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Plus, ExternalLink, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import MatchStatusBadge from "@/components/terminal/MatchStatusBadge";
import { fetchCachedPrediction } from "@/api/worldcupApi";
import { formatKickoff, statusLabel } from "@/lib/matchCenterUtils";
import { formatStars } from "@/lib/comboGenerator";
import { useBetSlip } from "@/context/BetSlipContext";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import PredictionExpandPanel from "./PredictionExpandPanel";

export default function EliteMatchCard({ match }) {
  const [expanded, setExpanded] = useState(false);
  const [prediction, setPrediction] = useState(null);
  const [loadingPred, setLoadingPred] = useState(false);
  const { addLeg } = useBetSlip();

  const summary = match.prediction_summary;
  const { date, time } = formatKickoff(match.match_date);
  const fixtureId = match.fixture_id || match.id;
  const detailHref = `/matches/${fixtureId}${match.competition_key ? `?competition=${match.competition_key}` : ""}`;

  useEffect(() => {
    if (!expanded || !match.has_prediction || prediction) return;
    let cancelled = false;
    (async () => {
      setLoadingPred(true);
      try {
        const res = await fetchCachedPrediction(fixtureId, {
          competition: match.competition_key,
        });
        if (!cancelled && res.cached) setPrediction(res.data);
      } catch {
        if (!cancelled) setPrediction(null);
      } finally {
        if (!cancelled) setLoadingPred(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [expanded, match.has_prediction, fixtureId, match.competition_key, prediction]);

  const handleAddToSlip = () => {
    if (!summary?.best_pick) return;
    addLeg({
      fixture_id: fixtureId,
      competition_key: match.competition_key,
      home_team: match.home_team,
      away_team: match.away_team,
      market: "best_pick",
      selection: summary.best_pick,
      label: summary.best_pick,
      confidence: summary.confidence,
    });
  };

  return (
    <motion.article
      layout
      className="rounded-2xl border border-white/[0.06] bg-gradient-to-br from-[#101827]/95 to-[#0B1220]/95 backdrop-blur-xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.35)] hover:border-[#00E676]/20 transition-colors"
    >
      <div className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-lg">{match.competition_emoji || "⚽"}</span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[#94A3B8] truncate">
                {match.competition_name || match.league}
              </p>
              {match.venue && (
                <p className="text-[10px] text-[#64748B] truncate">{match.venue}{match.city ? `, ${match.city}` : ""}</p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <MatchStatusBadge status={match.status} bucket={match.bucket} />
            <span className="text-[10px] text-[#64748B]">{statusLabel(match.bucket, match.status)}</span>
          </div>
        </div>

        <MatchTeamsRow
          homeTeam={match.home_team}
          awayTeam={match.away_team}
          homeLogo={match.home_team_logo}
          awayLogo={match.away_team_logo}
          countryHint={match.competition_country || match.country}
          size="lg"
          className="mb-4"
        />

        <div className="flex items-center justify-between text-xs text-[#94A3B8] mb-4">
          <span>{date}</span>
          <span className="font-mono text-[#F8FAFC] text-sm">{time}</span>
        </div>

        <div className="rounded-xl border border-white/[0.05] bg-black/30 p-3 mb-3">
          <div className="flex items-center justify-between gap-2 mb-2">
            <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Best Pick</p>
            {match.has_prediction ? (
              <span className="inline-flex items-center gap-1 text-[10px] text-[#00E676] bg-[#00E676]/10 px-2 py-0.5 rounded-full">
                <Sparkles className="w-3 h-3" /> Prediction ready
              </span>
            ) : (
              <span className="text-[10px] text-[#64748B]">No prediction yet</span>
            )}
          </div>
          {summary ? (
            <>
              <p className="text-base font-semibold text-[#F8FAFC]">{summary.best_pick || "—"}</p>
              <div className="flex flex-wrap items-center gap-3 mt-2 text-xs">
                <span className="text-[#FFD166]">{formatStars(summary.stars)}</span>
                {summary.confidence != null && (
                  <span className="text-[#94A3B8]">Confidence <strong className="text-white">{summary.confidence}%</strong></span>
                )}
                {summary.value_rating && (
                  <span className="text-[#7DD3FC]">Value {summary.value_rating}</span>
                )}
              </div>
              {summary.confidence != null && (
                <Progress value={summary.confidence} className="h-1.5 mt-2 bg-white/10" />
              )}
            </>
          ) : (
            <p className="text-sm text-[#64748B]">Run analysis from match detail</p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-1 border-white/10 bg-white/[0.03]"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? <ChevronUp className="w-4 h-4 mr-1" /> : <ChevronDown className="w-4 h-4 mr-1" />}
            {expanded ? "Hide markets" : "Expand predictions"}
          </Button>
          <Button type="button" variant="outline" size="sm" className="border-white/10" onClick={handleAddToSlip} disabled={!summary?.best_pick}>
            <Plus className="w-4 h-4" />
          </Button>
          <Button asChild variant="outline" size="sm" className="border-[#00E676]/30 text-[#00E676]">
            <Link to={detailHref}>
              <ExternalLink className="w-4 h-4 mr-1" /> Detail
            </Link>
          </Button>
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-white/[0.06] bg-black/20"
          >
            <div className="p-4">
              {loadingPred && <p className="text-sm text-[#94A3B8]">Loading markets…</p>}
              {!loadingPred && prediction && <PredictionExpandPanel prediction={prediction} match={match} onAddLeg={addLeg} />}
              {!loadingPred && !prediction && (
                <p className="text-sm text-[#94A3B8]">
                  {match.has_prediction ? "Could not load cached prediction." : "No cached prediction — open match detail to generate."}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}
