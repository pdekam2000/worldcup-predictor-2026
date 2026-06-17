import React, { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { runPrediction } from "@/api/worldcupApi";
import { motion } from "framer-motion";
import {
  ArrowLeft, Trophy, Activity, Brain, Stethoscope,
  Users, Cloud, Flame, LineChart, Swords, Scale, Building, Star,
  AlertCircle, RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

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

function roundPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return null;
  return Math.round(Number(value) * 10) / 10;
}

export default function PredictionDetail() {
  const { id } = useParams();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(null);

  const loadPrediction = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setApiError(null);
    setResult(null);
    try {
      const data = await runPrediction(id);
      setResult(data);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to run prediction.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadPrediction();
  }, [loadPrediction]);

  if (loading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <span className="inline-flex items-center gap-2 text-sm text-muted-foreground pointer-events-none opacity-50">
          <ArrowLeft className="w-4 h-4" /> Back to Match Center
        </span>
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">Running prediction...</p>
        </div>
      </div>
    );
  }

  if (apiError) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <Link to="/matches" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Match Center
        </Link>
        <div className="glass rounded-2xl p-8 text-center border border-red-500/20">
          <AlertCircle className="w-10 h-10 mx-auto mb-3 text-red-400" />
          <p className="text-sm font-medium text-red-300 mb-1">Prediction request failed</p>
          <p className="text-xs text-muted-foreground mb-4 max-w-md mx-auto">{apiError}</p>
          <Button type="button" variant="outline" size="sm" className="border-white/10" onClick={loadPrediction}>
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
  const pred = result?.prediction;
  const predLabel = predictionLabel(pred);

  const homeWinProb = roundPercent(result?.probabilities?.home_win);
  const drawProb = roundPercent(result?.probabilities?.draw);
  const awayWinProb = roundPercent(result?.probabilities?.away_win);

  const overUnder = result?.probabilities?.over_under_2_5;
  const overSelection = overUnder?.selection;
  const overProb = roundPercent(
    overUnder?.probability != null ? overUnder.probability * (overUnder.probability <= 1 ? 100 : 1) : null,
  );

  const specialists = Object.entries(result?.specialist_summary?.agents ?? {}).map(([name, agent]) => ({
    name,
    domain: agent?.domain ?? "—",
    status: agent?.status ?? "—",
    impact_score: agent?.impact_score,
  }));

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <Link to="/matches" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft className="w-4 h-4" /> Back to Match Center
      </Link>

      {/* Match header */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-6 sm:p-8">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-6 flex-wrap">
          <Trophy className="w-3.5 h-3.5" /> Fixture #{result?.fixture_id ?? id}
          {dataQuality != null && (
            <>
              <span className="mx-2">•</span>
              <span>Data quality: {dataQuality}%</span>
            </>
          )}
        </div>
        <div className="flex items-center justify-between">
          <div className="flex-1 text-center">
            <div className="w-16 h-16 sm:w-20 sm:h-20 mx-auto rounded-2xl bg-white/5 flex items-center justify-center mb-3 text-2xl font-bold text-primary">
              {homeTeam.slice(0, 3).toUpperCase()}
            </div>
            <div className="font-display font-bold text-lg">{homeTeam}</div>
            <div className="text-xs text-muted-foreground mt-1">Home</div>
          </div>
          <div className="px-6 text-center">
            <div className="text-2xl font-display font-bold text-muted-foreground mb-2">VS</div>
            <div className="text-xs text-muted-foreground uppercase tracking-wide">{pred || "—"}</div>
          </div>
          <div className="flex-1 text-center">
            <div className="w-16 h-16 sm:w-20 sm:h-20 mx-auto rounded-2xl bg-white/5 flex items-center justify-center mb-3 text-2xl font-bold text-accent">
              {awayTeam.slice(0, 3).toUpperCase()}
            </div>
            <div className="font-display font-bold text-lg">{awayTeam}</div>
            <div className="text-xs text-muted-foreground mt-1">Away</div>
          </div>
        </div>
      </motion.div>

      {/* Main prediction */}
      <div className="grid sm:grid-cols-2 gap-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-2xl p-6">
          <h2 className="font-display font-semibold mb-4 flex items-center gap-2">
            <Brain className="w-5 h-5 text-primary" /> Match Prediction
          </h2>
          <div className="text-center mb-6">
            <div className="text-4xl font-display font-bold text-gradient-blue mb-1">{predLabel}</div>
            <div className="text-sm text-muted-foreground">AI Prediction</div>
          </div>
          {/* Confidence gauge */}
          <div className="relative w-40 h-40 mx-auto mb-6">
            <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
              <circle cx="60" cy="60" r="54" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="10" />
              <circle cx="60" cy="60" r="54" fill="none" stroke="hsl(217, 91%, 60%)" strokeWidth="10"
                strokeDasharray={`${(confidence / 100) * 339} 339`} strokeLinecap="round" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-display font-bold">{confidence}%</span>
              <span className="text-xs text-muted-foreground">Confidence</span>
            </div>
          </div>
          {/* Probabilities */}
          <div className="space-y-3">
            {[
              { label: "Home Win", value: homeWinProb },
              { label: "Draw", value: drawProb },
              { label: "Away Win", value: awayWinProb },
            ].map((p, i) => (
              <div key={i}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">{p.label}</span>
                  <span className="font-medium">{p.value != null ? `${p.value}%` : "—"}</span>
                </div>
                <Progress value={p.value ?? 0} className="h-2 bg-white/5" />
              </div>
            ))}
          </div>
        </motion.div>

        {/* Over/Under — only when API provides extended market data */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="space-y-6">
          <div className="glass rounded-2xl p-6">
            <h2 className="font-display font-semibold mb-4">Over / Under 2.5</h2>
            {overSelection != null ? (
              <>
                <div className="flex items-center justify-between mb-3">
                  <span className={`text-lg font-bold ${String(overSelection).toLowerCase().includes("over") ? "text-green-400" : "text-red-400"}`}>
                    {String(overSelection).replace(/_/g, " ")}
                  </span>
                  <span className="text-2xl font-display font-bold">{overProb ?? "—"}%</span>
                </div>
                <Progress value={overProb ?? 0} className="h-3 bg-white/5" />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Extended market data not returned for this fixture.</p>
            )}
          </div>
          {result?.specialist_summary?.aggregated_score != null && (
            <div className="glass rounded-2xl p-6">
              <h2 className="font-display font-semibold mb-4">Specialist Score</h2>
              <div className="flex items-center justify-between mb-3">
                <span className="text-lg font-bold text-primary">Aggregated</span>
                <span className="text-2xl font-display font-bold">
                  {roundPercent(result.specialist_summary.aggregated_score)}%
                </span>
              </div>
              <Progress value={roundPercent(result.specialist_summary.aggregated_score) ?? 0} className="h-3 bg-white/5" />
            </div>
          )}
        </motion.div>
      </div>

      {/* Specialist Analysis */}
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
    </div>
  );
}
