import React from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/AuthContext";
import { qualityColorClass } from "@/lib/betQualityOverlay";
import { fmtMarketSel, safeMarketSelection } from "@/lib/predictionDetailProUtils";
import { TRUST_RESEARCH_ONLY } from "@/lib/trustCopy";
import EcseExactScorePanel from "./EcseExactScorePanel";

function MarketRow({ title, selection, probability, confidence, risk, reason, onAdd }) {
  if (!selection) return null;
  const probPct = probability != null ? (probability <= 1 ? Math.round(probability * 100) : Math.round(probability)) : null;
  const confPct = confidence != null ? (confidence <= 1 ? Math.round(confidence * 100) : Math.round(confidence)) : probPct;
  return (
    <div className="rounded-lg border border-white/[0.05] bg-white/[0.02] p-3 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-[#64748B]">{title}</p>
          <p className="text-sm font-semibold text-[#F8FAFC]">{selection}</p>
        </div>
        <Button type="button" size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={onAdd}>
          <Plus className="w-4 h-4" />
        </Button>
      </div>
      <div className="flex flex-wrap gap-3 text-[11px] text-[#94A3B8]">
        {confPct != null && <span>Confidence {confPct}%</span>}
        {probPct != null && <span>Probability {probPct}%</span>}
        {risk && <span>Risk {risk}</span>}
      </div>
      {reason && <p className="text-[11px] text-[#64748B]">{reason}</p>}
      <p className="text-[10px] text-[#475569] italic">{TRUST_RESEARCH_ONLY}</p>
    </div>
  );
}

function fmtSel(v) {
  return fmtMarketSel(v) || safeMarketSelection(v);
}

export default function PredictionExpandPanel({ prediction, match, onAddLeg }) {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "super_admin";
  const dm = prediction?.detailed_markets || {};
  const probs = prediction?.probabilities || {};
  const risk = prediction?.risk_level || "medium";
  const fixtureId = match.fixture_id || match.id;
  const overlay = prediction?.publication_overlay || {};
  const bqs = overlay.bet_quality_score ?? prediction?.bet_quality_score;
  const bqt = overlay.bet_quality_tier ?? prediction?.bet_quality_tier;
  const bqc = overlay.bet_quality_color ?? prediction?.bet_quality_color;
  const sourceModel =
    prediction?.source_model ||
    prediction?.model_source ||
    overlay.source_model ||
    (prediction?.no_bet ? (isSuperAdmin ? "Internal (no bet)" : "No program best bet") : "Classic model");

  const markets = [
    {
      title: "1X2",
      selection: fmtSel(prediction.prediction || dm.match_winner?.selection),
      probability: prediction.confidence,
      confidence: prediction.confidence,
      market: "1x2",
      raw: prediction.prediction,
    },
    {
      title: "Double Chance",
      selection: dm.double_chance?.selection ? fmtSel(dm.double_chance.selection) : null,
      probability: dm.double_chance?.probability,
      confidence: dm.double_chance?.confidence,
      market: "double_chance",
      raw: dm.double_chance?.selection,
    },
    {
      title: "BTTS",
      selection: fmtSel(probs.btts?.selection || dm.btts?.selection),
      probability: probs.btts?.probability || dm.btts?.probability,
      confidence: probs.btts?.confidence,
      market: "btts",
      raw: probs.btts?.selection,
    },
    {
      title: "Over/Under 2.5",
      selection: fmtSel(probs.over_under_2_5?.selection || dm.over_under_25?.selection),
      probability: probs.over_under_2_5?.probability || dm.over_under_25?.probability,
      confidence: probs.over_under_2_5?.confidence,
      market: "over_under_2_5",
      raw: probs.over_under_2_5?.selection,
    },
    {
      title: "Half Time",
      selection: fmtSel(dm.halftime?.selection),
      probability: dm.halftime?.probability,
      confidence: dm.halftime?.confidence,
      market: "halftime",
      raw: dm.halftime?.selection,
    },
    {
      title: "First Goal Team",
      selection: dm.first_goal?.team ? `${dm.first_goal.team} first` : null,
      probability: dm.first_goal?.probability,
      confidence: dm.first_goal?.confidence,
      market: "first_goal_team",
      raw: dm.first_goal?.team,
      reason: dm.first_goal?.minute_range ? `Window: ${dm.first_goal.minute_range}` : null,
    },
    {
      title: "Goalscorer",
      selection: dm.goalscorer?.player || null,
      probability: dm.goalscorer?.probability,
      confidence: dm.goalscorer?.confidence,
      market: "goalscorer",
      raw: dm.goalscorer?.player,
    },
  ];

  const scores = Array.isArray(dm.correct_scores) ? dm.correct_scores.slice(0, 3) : [];

  return (
    <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-[#94A3B8]">All available markets from cached prediction</span>
        {bqs != null && (
          <span className={`px-2 py-0.5 rounded-full border font-semibold ${qualityColorClass(bqc)}`}>
            Bet Quality {bqs}{bqt ? ` · ${bqt}` : ""}
          </span>
        )}
        <span className="text-[#64748B]">Source: {sourceModel}</span>
      </div>
      {markets.map((m) => (
        <MarketRow
          key={m.title}
          title={m.title}
          selection={m.selection}
          probability={m.probability}
          confidence={m.confidence}
          risk={risk}
          reason={m.reason}
          onAdd={() =>
            onAddLeg({
              fixture_id: fixtureId,
              competition_key: match.competition_key,
              home_team: match.home_team,
              away_team: match.away_team,
              market: m.market,
              selection: m.raw || m.selection,
              label: `${m.title}: ${m.selection}`,
              confidence: m.confidence || m.probability,
            })
          }
        />
      ))}
      {scores.length > 0 && (
        <div className="rounded-lg border border-white/[0.05] p-3">
          <p className="text-[10px] uppercase text-[#64748B] mb-2">Correct Score (top 3)</p>
          <div className="space-y-1">
            {scores.map((s) => (
              <p key={s.label} className="text-sm text-[#F8FAFC]">
                {s.label} — {s.probability != null ? `${Math.round((s.probability <= 1 ? s.probability * 100 : s.probability))}%` : "—"}
              </p>
            ))}
          </div>
        </div>
      )}
      <EcseExactScorePanel fixtureId={fixtureId} compact />
      {Array.isArray(prediction.recommended_bets) && prediction.recommended_bets.length > 0 && (
        <div className="rounded-lg border border-[#FFD166]/20 bg-[#FFD166]/5 p-3">
          <p className="text-[10px] uppercase text-[#FFD166] mb-2">Recommended bets</p>
          {prediction.recommended_bets.slice(0, 5).map((b, i) => (
            <p key={i} className="text-xs text-[#94A3B8]">
              {b.market}: {fmtSel(b.pick) || safeMarketSelection(b.pick) || "—"} ({b.status || "—"})
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
