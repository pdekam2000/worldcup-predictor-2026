import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Plus, ExternalLink, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import MatchStatusBadge from "@/components/terminal/MatchStatusBadge";
import { fetchPredictionForFixture } from "@/api/worldcupApi";
import { formatKickoff, fixtureStatusTone } from "@/lib/matchCenterUtils";
import { formatStars } from "@/lib/comboGenerator";
import { betQualityFromSummary, qualityColorClass, publicPickLabel } from "@/lib/betQualityOverlay";
import AddToPaperBetButton from "@/components/paper-betting/AddToPaperBetButton";
import { useBetSlip } from "@/context/BetSlipContext";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import PredictionExpandPanel from "./PredictionExpandPanel";
import OwnerInsightOverlay from "./OwnerInsightOverlay";

function aiBadgeClass(score) {
  if (score >= 95) return "bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30";
  if (score >= 87) return "bg-[#7DD3FC]/15 text-[#7DD3FC] border-[#7DD3FC]/30";
  if (score >= 73) return "bg-[#FFD166]/15 text-[#FFD166] border-[#FFD166]/30";
  if (score >= 58) return "bg-white/5 text-[#94A3B8] border-white/10";
  return "bg-white/5 text-[#64748B] border-white/10";
}

export default function EliteMatchCard({ match, variant = "dark" }) {
  const saas = variant === "saas";
  const [expanded, setExpanded] = useState(false);
  const [prediction, setPrediction] = useState(null);
  const [loadingPred, setLoadingPred] = useState(false);
  const [predError, setPredError] = useState(null);
  const { addLeg } = useBetSlip();

  const summary = match.prediction_summary;
  const quality = betQualityFromSummary(summary);
  const displayPick = publicPickLabel(summary);
  const isCaution = quality?.status === "caution_best_available" || summary?.caution_label;
  const ai = match.ai_match_score || {};
  const insights = match.match_insights || [];
  const statusText = match.fixture_status_label || (match.has_prediction ? "Prediction Ready" : "Waiting for Lineups");
  const { date, time } = formatKickoff(match.match_date);
  const fixtureId = match.fixture_id || match.id;
  const detailHref = `/matches/${fixtureId}${match.competition_key ? `?competition=${match.competition_key}` : ""}`;

  const loadExpandedPrediction = React.useCallback(async () => {
    setLoadingPred(true);
    setPredError(null);
    try {
      const res = await fetchPredictionForFixture(fixtureId, {
        competition: match.competition_key,
      });
      if (res.data) {
        setPrediction(res.data);
      } else {
        setPrediction(null);
        setPredError(match.has_prediction ? "retry" : "none");
      }
    } catch (err) {
      console.error("[EliteMatchCard] expand prediction load failed", err);
      setPrediction(null);
      setPredError("retry");
    } finally {
      setLoadingPred(false);
    }
  }, [fixtureId, match.competition_key, match.has_prediction]);

  useEffect(() => {
    if (!expanded || prediction || loadingPred) return;
    if (!match.has_prediction) return;
    loadExpandedPrediction();
  }, [expanded, match.has_prediction, prediction, loadingPred, loadExpandedPrediction]);

  const handleAddToSlip = () => {
    if (!displayPick) return;
    addLeg({
      fixture_id: fixtureId,
      competition_key: match.competition_key,
      home_team: match.home_team,
      away_team: match.away_team,
      market: "best_pick",
      selection: displayPick,
      label: displayPick,
      confidence: summary.confidence,
    });
  };

  return (
    <motion.article
      layout
      className={
        saas
          ? "saas-match-card overflow-hidden"
          : "rounded-2xl border border-white/[0.06] bg-gradient-to-br from-[#101827]/95 to-[#0B1220]/95 backdrop-blur-xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.35)] hover:border-[#00E676]/20 transition-colors"
      }
    >
      <div className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-lg">{match.competition_emoji || "⚽"}</span>
            <div className="min-w-0">
              <p className={`text-[11px] font-semibold uppercase tracking-wide truncate ${saas ? "text-slate-500" : "text-[#94A3B8]"}`}>
                {match.competition_name || match.league}
              </p>
              {match.venue && (
                <p className="text-[10px] text-[#64748B] truncate">{match.venue}{match.city ? `, ${match.city}` : ""}</p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <MatchStatusBadge status={match.status} bucket={match.bucket} />
            <span className={`text-[10px] px-2 py-0.5 rounded-full ${fixtureStatusTone(statusText)}`}>{statusText}</span>
            {ai.score != null && (
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${aiBadgeClass(ai.score)}`}>
                AI {ai.score} · {ai.label}
              </span>
            )}
          </div>
        </div>

        <MatchTeamsRow
          homeTeam={match.home_team}
          awayTeam={match.away_team}
          homeLogo={match.home_team_logo}
          awayLogo={match.away_team_logo}
          homeTeamId={match.home_team_id}
          awayTeamId={match.away_team_id}
          countryHint={match.competition_country || match.country}
          size="lg"
          className="mb-4"
        />

        <div className={`flex items-center justify-between text-xs mb-4 ${saas ? "text-slate-500" : "text-[#94A3B8]"}`}>
          <span>{date}</span>
          <span className={`font-mono text-sm ${saas ? "text-slate-900" : "text-[#F8FAFC]"}`}>{time}</span>
        </div>

        {match.bucket === "finished" && match.result_status && (
          <div
            className={`mb-3 text-xs font-semibold px-2 py-1 rounded-full inline-flex ${
              match.result_status === "correct"
                ? "bg-emerald-500/15 text-emerald-400"
                : match.result_status === "wrong"
                  ? "bg-red-500/15 text-red-400"
                  : match.result_status === "partial"
                    ? "bg-violet-500/15 text-violet-300"
                    : "bg-yellow-500/10 text-yellow-500"
            }`}
          >
            {match.result_status.toUpperCase()}
            {match.final_score ? ` · ${match.final_score}` : ""}
          </div>
        )}

        {insights.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {insights.map((tip) => (
              <span key={tip} className="text-[10px] px-2 py-0.5 rounded-full bg-[#00E676]/10 text-[#00E676] border border-[#00E676]/20">
                ✓ {tip}
              </span>
            ))}
          </div>
        )}

        <div className={`rounded-xl border p-3 mb-3 ${saas ? "border-slate-100 bg-slate-50" : "border-white/[0.05] bg-black/30"}`}>
          <div className="flex items-center justify-between gap-2 mb-2">
            <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">
              {isCaution ? "Caution — Best Available" : "Best Pick"}
            </p>
            {match.has_prediction ? (
              <span className="inline-flex items-center gap-1 text-[10px] text-[#00E676] bg-[#00E676]/10 px-2 py-0.5 rounded-full">
                <Sparkles className="w-3 h-3" /> Prediction ready
              </span>
            ) : (
              <span className="text-[10px] text-[#64748B]">No prediction yet</span>
            )}
          </div>
          {displayPick ? (
            <>
              {isCaution && (
                <p className="text-[10px] uppercase tracking-wide text-[#FF9F43] mb-1">{summary?.caution_label || "Caution — Best Available"}</p>
              )}
              <p className={`text-base font-semibold ${saas ? "text-slate-900" : "text-[#F8FAFC]"}`}>{displayPick}</p>
              {quality?.score != null && (
                <span className={`inline-block mt-2 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${qualityColorClass(quality.color)}`}>
                  Bet Quality {quality.score} · {quality.tier}
                </span>
              )}
              <div className="flex flex-wrap items-center gap-3 mt-2 text-xs">
                <span className="text-[#FFD166]">{formatStars(summary.stars)}</span>
                {summary.confidence != null && (
                  <span className="text-[#94A3B8]">Confidence <strong className="text-white">{summary.confidence}%</strong></span>
                )}
                {summary.value_rating && (
                  <span className="text-[#7DD3FC]">Value {summary.value_rating}</span>
                )}
              </div>
              {quality?.reason && isCaution && (
                <p className="text-[10px] text-[#64748B] mt-2">{quality.reason}</p>
              )}
              {summary.confidence != null && (
                <Progress value={summary.confidence} className="h-1.5 mt-2 bg-white/10" />
              )}
            </>
          ) : match.has_prediction && quality?.status === "unavailable" ? (
            <p className="text-sm text-[#64748B]">Prediction unavailable{quality.reason ? ` — ${quality.reason}` : ""}</p>
          ) : match.has_prediction ? (
            <p className="text-sm text-[#64748B]">Prediction not generated yet</p>
          ) : (
            <p className="text-sm text-[#64748B]">Run analysis from match detail</p>
          )}
        </div>

        <OwnerInsightOverlay ownerMeta={match.owner_meta} />

        <div className="flex flex-wrap gap-2 mt-3">
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
          <Button type="button" variant="outline" size="sm" className="border-white/10" onClick={handleAddToSlip} disabled={!displayPick}>
            <Plus className="w-4 h-4" />
          </Button>
          <Button asChild variant="outline" size="sm" className="border-[#00E676]/30 text-[#00E676]">
            <Link to={detailHref}>
              <ExternalLink className="w-4 h-4 mr-1" /> Detail
            </Link>
          </Button>
          {displayPick && (
            <AddToPaperBetButton
              size="sm"
              variant="ghost"
              bet={{
                fixture_id: fixtureId,
                market: quality?.source_market || "1x2",
                prediction: displayPick.includes(":") ? displayPick.split(":").slice(1).join(":").trim() : displayPick,
                bet_quality_score: quality?.score,
                competition_key: match.competition_key,
                home_team: match.home_team,
                away_team: match.away_team,
                source_page: "matches",
              }}
            />
          )}
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
                <div className="text-sm text-[#94A3B8] space-y-2">
                  {predError === "retry" ? (
                    <>
                      <p>Could not load prediction data.</p>
                      <Button type="button" size="sm" variant="outline" className="border-white/10" onClick={loadExpandedPrediction}>
                        Retry
                      </Button>
                    </>
                  ) : match.has_prediction ? (
                    <p>No prediction has been generated yet.</p>
                  ) : (
                    <p>No cached prediction — open match detail to generate.</p>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}
