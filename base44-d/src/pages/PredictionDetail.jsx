import React, { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCachedPrediction, runPrediction, normalizePredictionPayload } from "@/api/worldcupApi";
import { motion } from "framer-motion";
import {
  ArrowLeft, Trophy, Activity, Brain, Stethoscope,
  Users, Cloud, Flame, LineChart, Swords, Scale, Building, Star,
  AlertCircle, RefreshCw, Play, ChevronDown, ChevronUp, Target, ShieldAlert, ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import TeamBadge from "@/components/match/TeamBadge";
import DataQualityBadge from "@/components/match/DataQualityBadge";
import PredictionCacheBanner from "@/components/match/PredictionCacheBanner";
import { labelForStatusReason } from "@/lib/specialistReasons";

const specialistIcons = {
  form: Activity, injury: Stethoscope, lineup: Users, weather: Cloud,
  motivation: Flame, odds: LineChart, tactics: Swords, referee: Scale,
  venue: Building, player_quality: Star,
};

const specialistLabels = {
  form: "Form Specialist", injury: "Injury Specialist", lineup: "Lineup Specialist",
  weather: "Weather Specialist", motivation: "Motivation Specialist", odds: "Odds Specialist",
  tactics: "Tactics Specialist", referee: "Referee Specialist", venue: "Venue Specialist",
  player_quality: "Player Quality Specialist",
  expected_lineup_agent: "Expected Lineup Specialist",
  tournament_context_agent: "Tournament Context Specialist",
  xg_intelligence_agent: "Sportmonks xG Specialist",
  sportmonks_prediction_agent: "Sportmonks Prediction Specialist",
};

function getStatusColor(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized.includes("ok") || normalized.includes("success") || normalized.includes("active")) {
    return "text-green-400 bg-green-500/10";
  }
  if (normalized.includes("warn") || normalized.includes("degraded") || normalized.includes("partial")) {
    return "text-yellow-400 bg-yellow-500/10";
  }
  if (normalized.includes("error") || normalized.includes("fail") || normalized.includes("missing")) {
    return "text-red-400 bg-red-500/10";
  }
  return "text-muted-foreground bg-white/5";
}

function formatAgentLabel(name) {
  return specialistLabels[name] || name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function predictionLabel(prediction) {
  if (prediction === "home") return "Home Win";
  if (prediction === "draw") return "Draw";
  if (prediction === "away") return "Away Win";
  return prediction || "—";
}

function formatMarketSelection(selection) {
  if (!selection) return "—";
  const map = {
    home_win: "Home Win",
    away_win: "Away Win",
    draw: "Draw",
    over_2_5: "Over 2.5",
    under_2_5: "Under 2.5",
    yes: "BTTS Yes",
    no: "BTTS No",
  };
  return map[selection] || String(selection).replace(/_/g, " ");
}

function recommendedHeadline(recommendedBets) {
  if (!Array.isArray(recommendedBets) || recommendedBets.length === 0) {
    return null;
  }
  const primary = recommendedBets[0];
  if (primary?.status === "no_bet") {
    return { type: "no_bet", text: primary.display_text || "No Bet — confidence too low" };
  }
  const labels = recommendedBets
    .filter((b) => b.status === "recommended")
    .map((b) => b.pick)
    .filter(Boolean);
  if (labels.length === 0) return null;
  if (labels.length === 1) {
    return { type: "single", text: `Recommended Bet: ${labels[0]}` };
  }
  return { type: "multi", text: `Recommended Bets: ${labels.join(" + ")}` };
}

function MarketDetailSection({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-white/10 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold hover:bg-white/5 transition-colors"
      >
        <span>{title}</span>
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>
      {open && <div className="px-4 pb-4 pt-1 border-t border-white/5">{children}</div>}
    </div>
  );
}

function ProbBar({ label, value }) {
  const pct = value != null && !Number.isNaN(Number(value)) ? Number(value) : null;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{pct != null ? `${pct}%` : "—"}</span>
      </div>
      <Progress value={pct ?? 0} className="h-2 bg-white/5" />
    </div>
  );
}

function roundPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return null;
  return Math.round(Number(value) * 10) / 10;
}

function pctFromProb(value) {
  if (value == null || Number.isNaN(Number(value))) return null;
  const n = Number(value);
  return roundPercent(n <= 1 ? n * 100 : n);
}

function RankingPickCard({ title, pick, accentClass, icon: Icon }) {
  if (!pick) {
    return (
      <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-muted-foreground">
        <div className="font-semibold text-foreground/80 mb-1">{title}</div>
        <span>Not available for this fixture</span>
      </div>
    );
  }
  const prob = pctFromProb(pick.probability ?? pick.confidence);
  const score = pick.market_rank_score != null ? Math.round(Number(pick.market_rank_score) * 1000) / 10 : null;
  return (
    <div className={`rounded-xl border p-4 ${accentClass}`}>
      <div className="flex items-start gap-3">
        {Icon && <Icon className="w-5 h-5 shrink-0 mt-0.5 opacity-80" />}
        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">{title}</div>
          <div className="font-display font-bold text-lg leading-tight">{pick.pick}</div>
          <div className="text-xs text-muted-foreground mt-1">{pick.market}</div>
          <div className="flex flex-wrap gap-3 mt-2 text-sm">
            {prob != null && (
              <span>Probability: <strong className="text-foreground">{prob}%</strong></span>
            )}
            {score != null && (
              <span>Rank score: <strong className="text-foreground">{score}%</strong></span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PredictionDetail() {
  const { id } = useParams();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [notCached, setNotCached] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [cacheSource, setCacheSource] = useState(null);
  const [cooldownRemaining, setCooldownRemaining] = useState(null);

  const loadCached = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setApiError(null);
    setNotCached(false);
    try {
      const cached = await fetchCachedPrediction(id);
      if (cached.cached && cached.data) {
        setResult(normalizePredictionPayload(cached.data));
        setCacheSource(cached.data.cache_source || "cache");
        setCooldownRemaining(cached.data.refresh_cooldown_remaining_seconds ?? null);
      } else {
        setResult(null);
        setNotCached(true);
        setCacheSource(null);
      }
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to load prediction.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  const executePrediction = useCallback(async (forceRefresh = false) => {
    if (!id) return;
    setRunning(true);
    setApiError(null);
    try {
      const data = await runPrediction(id, { forceRefresh });
      setResult(normalizePredictionPayload(data));
      setNotCached(false);
      setCacheSource(data.cache_source || (forceRefresh ? "live" : "live"));
      setCooldownRemaining(data.refresh_cooldown_remaining_seconds ?? null);
    } catch (err) {
      if (err?.code === "refresh_cooldown" || err?.cooldownSeconds) {
        setCooldownRemaining(err.cooldownSeconds ?? cooldownRemaining);
      }
      setApiError(err instanceof Error ? err.message : "Failed to run prediction.");
    } finally {
      setRunning(false);
    }
  }, [id]);

  useEffect(() => {
    loadCached();
  }, [loadCached]);

  if (loading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <span className="inline-flex items-center gap-2 text-sm text-muted-foreground pointer-events-none opacity-50">
          <ArrowLeft className="w-4 h-4" /> Back to Match Center
        </span>
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">Loading prediction...</p>
        </div>
      </div>
    );
  }

  if (notCached && !result) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <Link to="/matches" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Match Center
        </Link>
        <div className="glass rounded-2xl p-8 text-center border border-white/10">
          <Brain className="w-10 h-10 mx-auto mb-3 text-primary" />
          <p className="text-sm font-medium mb-1">No cached prediction yet</p>
          <p className="text-xs text-muted-foreground mb-4 max-w-md mx-auto">
            Fixture #{id} — run a full analysis only when you need it. Browsing Match Center does not consume prediction quota.
          </p>
          {apiError && <p className="text-xs text-red-300 mb-4">{apiError}</p>}
          <Button type="button" size="sm" onClick={() => executePrediction(false)} disabled={running}>
            {running ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                Run Prediction
              </>
            )}
          </Button>
        </div>
      </div>
    );
  }

  if (apiError && !result) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <Link to="/matches" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Match Center
        </Link>
        <div className="glass rounded-2xl p-8 text-center border border-red-500/20">
          <AlertCircle className="w-10 h-10 mx-auto mb-3 text-red-400" />
          <p className="text-sm font-medium text-red-300 mb-1">Prediction request failed</p>
          <p className="text-xs text-muted-foreground mb-4 max-w-md mx-auto">{apiError}</p>
          <Button type="button" variant="outline" size="sm" className="border-white/10" onClick={() => executePrediction(false)} disabled={running}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const homeTeam = result?.home_team ?? "—";
  const awayTeam = result?.away_team ?? "—";
  const confidence = roundPercent(result?.confidence) ?? 0;
  const dataQuality = roundPercent(result?.data_quality);
  const dataSignals = result?.data_signals;
  const pred = result?.prediction;
  const predLabel = predictionLabel(pred);
  const recommendedBets = result?.recommended_bets ?? [];
  const headline = recommendedHeadline(recommendedBets);
  const primaryRec = result?.primary_recommendation ?? recommendedBets[0];
  const safePick = result?.safe_pick ?? null;
  const valuePick = result?.value_pick ?? null;
  const aggressivePick = result?.aggressive_pick ?? null;
  const markets = result?.detailed_markets ?? {};
  const riskLevel = result?.risk_level ?? "medium";

  const homeWinProb = roundPercent(result?.probabilities?.home_win ?? markets.match_winner?.probabilities?.home_win);
  const drawProb = roundPercent(result?.probabilities?.draw ?? markets.match_winner?.probabilities?.draw);
  const awayWinProb = roundPercent(result?.probabilities?.away_win ?? markets.match_winner?.probabilities?.away_win);

  const overUnder = result?.probabilities?.over_under_2_5 ?? markets.over_under_25;
  const overSelection = overUnder?.selection ?? markets.over_under_25?.selection;
  const overProb = pctFromProb(overUnder?.probability ?? markets.over_under_25?.probability);
  const ouProbs = overUnder?.probabilities ?? markets.over_under_25?.probabilities ?? {};

  const btts = result?.probabilities?.btts ?? markets.btts ?? {};
  const bttsProb = pctFromProb(btts.probability);
  const ht = markets.halftime ?? {};
  const firstGoal = markets.first_goal ?? {};
  const goalscorer = markets.goalscorer ?? {};
  const doubleChance = markets.double_chance ?? {};

  const specialists = Object.entries(result?.specialist_summary?.agents ?? {}).map(([name, agent]) => ({
    name,
    domain: agent?.domain ?? "—",
    status: agent?.status ?? "—",
    status_reason: agent?.status_reason ?? null,
    impact_score: agent?.impact_score,
  }));

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link to="/matches" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Match Center
        </Link>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <PredictionCacheBanner
            cacheSource={cacheSource}
            cachedAt={result?.cached_at}
            refreshCooldownRemaining={cooldownRemaining}
            refreshCooldownSeconds={result?.refresh_cooldown_seconds}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="border-white/10"
            onClick={() => executePrediction(true)}
            disabled={running || (cooldownRemaining != null && cooldownRemaining > 0)}
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${running ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {apiError && (
        <div className="glass rounded-xl p-3 text-sm text-red-300 border border-red-500/20">{apiError}</div>
      )}

      {/* Match header */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-6 sm:p-8">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4 flex-wrap">
          <Trophy className="w-3.5 h-3.5" /> Fixture #{result?.fixture_id ?? id}
        </div>
        <DataQualityBadge dataSignals={dataSignals} dataQualityPct={dataQuality} />
        <div className="flex items-center justify-between">
          <div className="flex-1 text-center">
            <TeamBadge
              teamName={homeTeam}
              logoUrl={result?.home_team_logo}
              countryHint={result?.country}
              size="lg"
            />
            <div className="font-display font-bold text-lg">{homeTeam}</div>
            <div className="text-xs text-muted-foreground mt-1">Home</div>
          </div>
          <div className="px-6 text-center">
            <div className="text-2xl font-display font-bold text-muted-foreground mb-2">VS</div>
            <div className="text-xs text-muted-foreground uppercase tracking-wide">{pred || "—"}</div>
          </div>
          <div className="flex-1 text-center">
            <TeamBadge
              teamName={awayTeam}
              logoUrl={result?.away_team_logo}
              countryHint={result?.country}
              size="lg"
              className="text-accent"
            />
            <div className="font-display font-bold text-lg">{awayTeam}</div>
            <div className="text-xs text-muted-foreground mt-1">Away</div>
          </div>
        </div>
      </motion.div>

      {/* Phase 30C — ranked pick buckets */}
      {!result?.no_bet && (safePick || valuePick || aggressivePick) && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.04 }}
          className="space-y-3"
        >
          <h2 className="font-display font-semibold text-lg">Ranked Picks</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <RankingPickCard
              title="Safe Pick"
              pick={safePick}
              accentClass="border-emerald-500/25 bg-emerald-500/5"
              icon={ShieldCheck}
            />
            <RankingPickCard
              title="Value Pick"
              pick={valuePick}
              accentClass="border-primary/25 bg-primary/5"
              icon={Target}
            />
            <RankingPickCard
              title="Aggressive Pick"
              pick={aggressivePick}
              accentClass="border-orange-500/25 bg-orange-500/5"
              icon={Flame}
            />
          </div>
        </motion.div>
      )}

      {/* Recommended bet — primary UX */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className={`glass rounded-2xl p-6 border ${
          headline?.type === "no_bet" ? "border-yellow-500/30 bg-yellow-500/5" : "border-primary/30 bg-primary/5"
        }`}
      >
        <div className="flex items-start gap-3">
          {headline?.type === "no_bet" ? (
            <ShieldAlert className="w-8 h-8 text-yellow-400 shrink-0" />
          ) : (
            <Target className="w-8 h-8 text-primary shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <h2 className="font-display font-bold text-xl sm:text-2xl mb-2">
              {headline?.text || `Recommended Bet: ${predLabel}`}
            </h2>
            <div className="flex flex-wrap gap-3 text-sm text-muted-foreground mb-3">
              <span>Confidence: <strong className="text-foreground">{confidence}%</strong></span>
              <span>Risk: <strong className="text-foreground capitalize">{riskLevel}</strong></span>
              {dataQuality != null && (
                <span>Data quality: <strong className="text-foreground">{dataQuality}%</strong></span>
              )}
            </div>
            {primaryRec?.reasoning && (
              <p className="text-sm text-muted-foreground leading-relaxed">{primaryRec.reasoning}</p>
            )}
            {Array.isArray(primaryRec?.source_agents) && primaryRec.source_agents.length > 0 && (
              <p className="text-xs text-muted-foreground mt-2">
                Sources: {primaryRec.source_agents.join(" · ")}
              </p>
            )}
          </div>
        </div>
        {recommendedBets.filter((b) => b.status === "recommended").length > 1 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {recommendedBets
              .filter((b) => b.status === "recommended")
              .map((bet) => (
                <span
                  key={`${bet.market}-${bet.pick}`}
                  className="px-3 py-1 rounded-full text-xs font-semibold bg-primary/15 text-primary border border-primary/20"
                >
                  {bet.market}: {bet.pick}
                </span>
              ))}
          </div>
        )}
      </motion.div>

      {/* Collapsible detailed markets */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.12 }}
        className="space-y-3"
      >
        <h2 className="font-display font-semibold text-lg flex items-center gap-2">
          <LineChart className="w-5 h-5 text-primary" /> Detailed Probabilities
        </h2>
        <p className="text-xs text-muted-foreground -mt-1 mb-2">
          Raw model outputs for transparency — recommendations above use only the strongest signals.
        </p>

        <MarketDetailSection title="Match Winner (1X2)" defaultOpen>
          <div className="space-y-3 pt-2">
            <ProbBar label="Home Win" value={homeWinProb} />
            <ProbBar label="Draw" value={drawProb} />
            <ProbBar label="Away Win" value={awayWinProb} />
          </div>
        </MarketDetailSection>

        <MarketDetailSection title="Over / Under 2.5">
          <div className="space-y-3 pt-2">
            {overSelection != null ? (
              <>
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold text-primary">{formatMarketSelection(overSelection)}</span>
                  <span>{overProb != null ? `${overProb}%` : "—"}</span>
                </div>
                <ProbBar label="Over 2.5" value={ouProbs.over_2_5 ?? ouProbs.over} />
                <ProbBar label="Under 2.5" value={ouProbs.under_2_5 ?? ouProbs.under} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Over/Under data unavailable.</p>
            )}
          </div>
        </MarketDetailSection>

        <MarketDetailSection title="Both Teams To Score (BTTS)">
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-semibold">{formatMarketSelection(btts.selection)}</span>
              <span>{bttsProb != null ? `${bttsProb}%` : "—"}</span>
            </div>
            <ProbBar label="Yes" value={btts.probabilities?.yes} />
            <ProbBar label="No" value={btts.probabilities?.no} />
          </div>
        </MarketDetailSection>

        <MarketDetailSection title="Half Time Result">
          <div className="space-y-3 pt-2">
            <ProbBar label="Home HT" value={ht.probabilities?.home_win} />
            <ProbBar label="Draw HT" value={ht.probabilities?.draw} />
            <ProbBar label="Away HT" value={ht.probabilities?.away_win} />
          </div>
        </MarketDetailSection>

        <MarketDetailSection title="First Goal & Timing">
          <div className="space-y-2 pt-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">First team to score</span>
              <span className="font-medium">{firstGoal.team || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Minute range</span>
              <span className="font-medium">{firstGoal.minute_range || "—"}</span>
            </div>
            {firstGoal.expected_minute != null && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Expected minute</span>
                <span className="font-medium">{firstGoal.expected_minute}&apos;</span>
              </div>
            )}
          </div>
        </MarketDetailSection>

        {goalscorer?.available !== false && (goalscorer?.player || goalscorer?.available) && (
          <MarketDetailSection title="Likely Goalscorer">
            <div className="space-y-2 pt-2 text-sm">
              {goalscorer?.player ? (
                <>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Player</span>
                    <span className="font-medium">{goalscorer.player}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Team</span>
                    <span className="font-medium">{goalscorer.team || "—"}</span>
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground">Lineup/player data not available for goalscorer pick.</p>
              )}
            </div>
          </MarketDetailSection>
        )}

        {(doubleChance.home_or_draw != null || doubleChance.draw_or_away != null) && (
          <MarketDetailSection title="Double Chance">
            <div className="space-y-3 pt-2">
              <ProbBar label="Home or Draw" value={doubleChance.home_or_draw} />
              <ProbBar label="Home or Away" value={doubleChance.home_or_away} />
              <ProbBar label="Draw or Away" value={doubleChance.draw_or_away} />
            </div>
          </MarketDetailSection>
        )}
      </motion.div>

      {result?.specialist_summary?.aggregated_score != null && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }} className="glass rounded-2xl p-6">
          <h2 className="font-display font-semibold mb-4">Specialist Agreement</h2>
          <div className="flex items-center justify-between mb-3">
            <span className="text-lg font-bold text-primary">Aggregated score</span>
            <span className="text-2xl font-display font-bold">
              {roundPercent(result.specialist_summary.aggregated_score)}%
            </span>
          </div>
          <Progress value={roundPercent(result.specialist_summary.aggregated_score) ?? 0} className="h-3 bg-white/5" />
        </motion.div>
      )}

      {specialists.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <h2 className="font-display font-semibold text-lg mb-4 flex items-center gap-2">
            <Brain className="w-5 h-5 text-primary" /> Specialist Analysis
          </h2>
          <div className="grid sm:grid-cols-2 gap-4">
            {specialists.map((s, i) => {
              const Icon = specialistIcons[s.name] || Brain;
              return (
                <div key={s.name || i} className="glass rounded-xl p-4 hover:bg-white/10 transition-all">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                        <Icon className="w-5 h-5 text-primary" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold">{formatAgentLabel(s.name)}</div>
                        <div className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium mt-1 ${getStatusColor(s.status)}`}>
                          {s.status}
                        </div>
                        {s.status_reason && (
                          <div className="text-[10px] text-muted-foreground mt-1">
                            {labelForStatusReason(s.status_reason)}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-display font-bold">
                        {s.impact_score != null ? roundPercent(s.impact_score) : "—"}
                      </div>
                      <div className="text-xs text-muted-foreground">impact</div>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Domain: {s.domain}
                  </p>
                </div>
              );
            })}
          </div>
        </motion.div>
      )}

      {result?.audit_trace && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="glass rounded-2xl p-6">
          <h2 className="font-display font-semibold mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" /> Promotion Trace
          </h2>
          <p className="text-xs text-muted-foreground mb-4">
            Shadow-mode promotion signals — trace only, no WDE weight changes.
          </p>
          <div className="grid sm:grid-cols-2 gap-3 text-xs">
            {[
              { key: "expected_lineup", label: "Expected Lineup" },
              { key: "tournament_context", label: "Tournament Context" },
              { key: "xg_intelligence", label: "Sportmonks xG" },
              { key: "sportmonks_prediction", label: "Sportmonks Prediction" },
            ].map(({ key, label }) => {
              const block = result.audit_trace[key] || {};
              return (
                <div key={key} className="rounded-lg bg-white/5 p-3 border border-white/5">
                  <div className="font-semibold mb-1">{label}</div>
                  <div className="text-muted-foreground space-y-0.5">
                    <div>Agent: {block.status ?? "—"} · mode: {block.mode ?? result.audit_trace.promotion_modes?.[key === "xg_intelligence" ? "xg" : key === "sportmonks_prediction" ? "sportmonks_prediction" : key] ?? "—"}</div>
                    <div>Delta: {block.delta_score != null ? roundPercent(block.delta_score) : "—"} · applied: {block.promotion_applied ? "yes" : "no"}</div>
                    {block.reason ? <div className="truncate" title={block.reason}>Reason: {block.reason}</div> : null}
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>
      )}
    </div>
  );
}
