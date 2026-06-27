import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, RefreshCw, AlertCircle } from "lucide-react";
import { fetchPredictionForFixture, fetchMatchMeta, fetchMatchEvaluation, normalizePredictionPayload } from "@/api/worldcupApi";
import { fetchPredictionHistoryEntry } from "@/api/saasApi";
import { Button } from "@/components/ui/button";
import PredictionCacheBanner from "@/components/match/PredictionCacheBanner";
import BetSlipDrawer from "@/components/match-center/BetSlipDrawer";
import { useBetSlip } from "@/context/BetSlipContext";
import { buildCombos } from "@/lib/comboGenerator";
import { deriveMatchDetailView } from "@/lib/matchDetailSafeView";
import MatchHeaderPro from "@/components/prediction-detail-pro/MatchHeaderPro";
import PredictionSummaryCards from "@/components/prediction-detail-pro/PredictionSummaryCards";
import PredictionMarketsPro from "@/components/prediction-detail-pro/PredictionMarketsPro";
import AIMatchIntelligence from "@/components/prediction-detail-pro/AIMatchIntelligence";
import TeamComparison from "@/components/prediction-detail-pro/TeamComparison";
import OddsCenter from "@/components/prediction-detail-pro/OddsCenter";
import ExpectedGoalsSection from "@/components/prediction-detail-pro/ExpectedGoalsSection";
import PressureSection from "@/components/prediction-detail-pro/PressureSection";
import LineupsSection from "@/components/prediction-detail-pro/LineupsSection";
import AgentContributionPanel from "@/components/prediction-detail-pro/AgentContributionPanel";
import ConfidenceExplanation from "@/components/prediction-detail-pro/ConfidenceExplanation";
import BetSlipActions from "@/components/prediction-detail-pro/BetSlipActions";
import PredictionHistorySection from "@/components/prediction-detail-pro/PredictionHistorySection";
import { DetailSectionSkeleton } from "@/components/prediction-detail-pro/DetailSectionSkeleton";
import { useAuth } from "@/lib/AuthContext";
import ShareButton from "@/components/social/ShareButton";
import ErrorBoundary from "@/components/ui/ErrorBoundary";

const SECTION_TABS = [
  { id: "summary", label: "Summary" },
  { id: "markets", label: "Markets" },
  { id: "intelligence", label: "AI Intel" },
  { id: "data", label: "Data" },
  { id: "history", label: "History" },
];

export default function MatchDetailPage() {
  const { fixtureId } = useParams();
  const [searchParams] = useSearchParams();
  const competitionParam = searchParams.get("competition") || undefined;

  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      let payload;
      const compForFetch = competitionParam && competitionParam !== "all" ? competitionParam : undefined;
      if (force) {
        const { runPrediction } = await import("@/api/worldcupApi");
        payload = await runPrediction(fixtureId, { competition: compForFetch, forceRefresh: force });
      } else {
        const res = await fetchPredictionForFixture(fixtureId, { competition: compForFetch, allowRun: true });
        if (res.data) payload = res.data;
        else throw new Error("No prediction has been generated yet.");
      }
      setData(normalizePredictionPayload(payload));
    } catch (err) {
      console.error("[MatchDetailPage] load failed", err);
      setError(err instanceof Error ? err.message : "Failed to load match");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fixtureId, competitionParam]);

  const [tab, setTab] = useState("summary");
  const [data, setData] = useState(null);
  const [matchMeta, setMatchMeta] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [matchEvaluation, setMatchEvaluation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { addLeg, clearSlip } = useBetSlip();
  const { isAuthenticated, user } = useAuth();
  const isOwner = ["owner", "admin", "super_admin"].includes(String(user?.role || "").toLowerCase());

  const competition = matchMeta?.competition_key || competitionParam;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meta = await fetchMatchMeta(fixtureId, { competition: competitionParam || "all" });
        if (!cancelled) setMatchMeta(meta);
      } catch {
        if (!cancelled) setMatchMeta(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fixtureId, competitionParam]);

  useEffect(() => {
    load(false);
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const evalRes = await fetchMatchEvaluation(fixtureId);
        if (!cancelled && evalRes?.evaluation) {
          setMatchEvaluation(evalRes.evaluation);
        } else if (!cancelled) {
          setMatchEvaluation(null);
        }
      } catch {
        if (!cancelled) setMatchEvaluation(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fixtureId]);

  useEffect(() => {
    if (!isAuthenticated) {
      setHistoryDetail(null);
      return;
    }
    (async () => {
      try {
        const detail = await fetchPredictionHistoryEntry(`global-${fixtureId}`);
        setHistoryDetail(detail);
      } catch {
        setHistoryDetail(null);
      }
    })();
  }, [fixtureId, isAuthenticated]);

  const displayData = useMemo(() => {
    if (!data && !matchMeta) return null;
    const base = data ? { ...data } : {};
    if (matchMeta) {
      base.home_team = base.home_team || matchMeta.home_team;
      base.away_team = base.away_team || matchMeta.away_team;
      base.home_team_logo = base.home_team_logo || matchMeta.home_team_logo;
      base.away_team_logo = base.away_team_logo || matchMeta.away_team_logo;
      base.home_team_id = base.home_team_id || matchMeta.home_team_id;
      base.away_team_id = base.away_team_id || matchMeta.away_team_id;
      base.competition_key = base.competition_key || matchMeta.competition_key;
      base.competition_name = base.competition_name || matchMeta.competition_name || matchMeta.league;
      base.league = base.league || matchMeta.league;
      base.match_date = base.match_date || matchMeta.match_date;
      base.venue = base.venue || matchMeta.venue;
      base.city = base.city || matchMeta.city;
    }
    if (matchEvaluation) {
      base.match_evaluation = matchEvaluation;
      base.result_status = matchEvaluation.result_status || base.result_status;
      base.final_score = matchEvaluation.final_score || base.final_score;
      base.actual_result = matchEvaluation.actual_result || base.actual_result;
    }
    return Object.keys(base).length ? base : null;
  }, [data, matchMeta, matchEvaluation]);

  const derived = useMemo(() => deriveMatchDetailView(displayData, { isOwner }), [displayData, isOwner]);
  const {
    summary,
    insights,
    marketGroups,
    teamMetrics,
    odds,
    xg,
    pressure,
    lineups,
    confidenceExpl,
    agents,
    deriveError,
  } = derived;

  const matchCtx = {
    fixture_id: Number(fixtureId),
    competition_key: competition || displayData?.competition_key,
    home_team: displayData?.home_team,
    away_team: displayData?.away_team,
  };

  const handleAddBestPick = () => {
    if (!summary?.bestPick) return;
    addLeg({
      ...matchCtx,
      market: "best_pick",
      selection: summary.bestPick,
      label: summary.bestPick,
      confidence: summary.confidence,
    });
  };

  const handleAddCombo = () => {
    const fakeMatch = {
      ...matchCtx,
      prediction_summary: {
        best_pick: summary?.bestPick,
        confidence: summary?.confidence,
        stars: 4,
        bet_quality_score: summary?.betQualityScore,
        publication_overlay: data?.publication_overlay,
        caution_label: summary?.cautionLabel,
      },
      ai_match_score: { score: summary?.confidence || 70 },
    };
    const combos = buildCombos([fakeMatch]);
    const best = combos[0];
    if (!best?.legs?.length) return;
    clearSlip();
    best.legs.forEach((leg) => addLeg(leg));
  };

  return (
    <div className="max-w-6xl mx-auto space-y-5 pb-28 px-1 sm:px-0">
      <div className="flex flex-wrap items-center gap-3">
        <Button asChild variant="ghost" size="sm" className="text-[#94A3B8]">
          <Link to="/matches"><ArrowLeft className="w-4 h-4 mr-1" /> Match Center</Link>
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {data && (
            <PredictionCacheBanner
              cachedAt={data.cached_at}
              refreshCooldownRemaining={data.refresh_cooldown_remaining_seconds}
              refreshCooldownSeconds={data.refresh_cooldown_seconds}
            />
          )}
          <Button variant="outline" size="sm" className="border-white/10" onClick={() => load(true)} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          {summary?.bestPick && (
            <ShareButton
              type="pick"
              label="Share pick"
              payload={{
                fixture_id: Number(fixtureId),
                home_team: displayData?.home_team,
                away_team: displayData?.away_team,
                league: displayData?.league || displayData?.competition_name,
                market: "best_pick",
                market_label: "Best pick",
                prediction: summary.bestPick,
                bet_quality_score: summary.betQualityScore,
                confidence: summary.confidence,
              }}
            />
          )}
        </div>
      </div>

      <div className="overflow-x-auto -mx-1 px-1">
        <div className="flex gap-2 min-w-max pb-1">
          {SECTION_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 rounded-lg text-sm border transition-colors ${
                tab === t.id ? "bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30" : "bg-white/[0.03] text-[#94A3B8] border-white/[0.06]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <DetailSectionSkeleton />}

      {error && !loading && (
        <div className="rounded-xl border border-red-500/30 p-6 text-center">
          <AlertCircle className="w-10 h-10 mx-auto text-red-400 mb-2" />
          <p className="text-red-300 text-sm">{error}</p>
          <Button className="mt-4" variant="outline" onClick={() => load(false)}>Retry</Button>
        </div>
      )}

      {deriveError && !loading && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          Some prediction sections could not be rendered. Core match data is still available.
        </div>
      )}

      {displayData && !loading && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
          <ErrorBoundary label="match-header">
            <MatchHeaderPro prediction={displayData} competitionKey={competition} />
          </ErrorBoundary>

          {(tab === "summary" || tab === "markets") && (
            <ErrorBoundary label="summary">
              <PredictionSummaryCards summary={summary} />
              <BetSlipActions summary={summary} match={matchCtx} onAddBestPick={handleAddBestPick} onAddCombo={handleAddCombo} />
            </ErrorBoundary>
          )}

          {tab === "markets" && (
            <ErrorBoundary label="markets">
              <div id="markets">
                <PredictionMarketsPro groups={marketGroups} match={matchCtx} onAddLeg={addLeg} />
              </div>
            </ErrorBoundary>
          )}

          {tab === "intelligence" && (
            <ErrorBoundary label="intelligence">
              <AIMatchIntelligence insights={insights} />
              <ConfidenceExplanation explanation={confidenceExpl} />
              <AgentContributionPanel agents={agents} />
            </ErrorBoundary>
          )}

          {tab === "data" && (
            <ErrorBoundary label="data">
              <div className="grid lg:grid-cols-2 gap-4">
                <TeamComparison metrics={teamMetrics} homeTeam={displayData.home_team} awayTeam={displayData.away_team} />
                <OddsCenter odds={odds} />
                <ExpectedGoalsSection xg={xg} homeTeam={displayData.home_team} awayTeam={displayData.away_team} />
                <PressureSection pressure={pressure} />
                <div className="lg:col-span-2">
                  <LineupsSection lineups={lineups} homeTeam={displayData.home_team} awayTeam={displayData.away_team} />
                </div>
              </div>
            </ErrorBoundary>
          )}

          {tab === "summary" && (
            <ErrorBoundary label="summary-intel">
              <div className="grid lg:grid-cols-2 gap-4">
                <AIMatchIntelligence insights={insights.slice(0, 6)} />
                <ConfidenceExplanation explanation={confidenceExpl} />
              </div>
            </ErrorBoundary>
          )}

          {tab === "history" && (
            <ErrorBoundary label="history">
              <PredictionHistorySection
                history={historyDetail ? [historyDetail] : []}
                fixtureId={fixtureId}
                accuracy={matchEvaluation || displayData?.accuracy_tracking}
              />
            </ErrorBoundary>
          )}

          <p className="text-center text-[10px] text-[#64748B] italic pt-4">
            Research only — not betting advice. UI reads cached prediction payload only; engines unchanged.
          </p>
        </motion.div>
      )}

      <BetSlipDrawer />
    </div>
  );
}
