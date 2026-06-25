import React from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

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
      <p className="text-[10px] text-[#475569] italic">Research only — not betting advice.</p>
    </div>
  );
}

function fmtSel(v) {
  if (!v) return null;
  const map = {
    home: "Home Win", away: "Away Win", draw: "Draw",
    home_win: "Home Win", away_win: "Away Win",
    over_2_5: "Over 2.5", under_2_5: "Under 2.5",
    yes: "Yes", no: "No",
  };
  return map[String(v).toLowerCase()] || String(v).replace(/_/g, " ");
}

export default function PredictionExpandPanel({ prediction, match, onAddLeg }) {
  const dm = prediction.detailed_markets || {};
  const probs = prediction.probabilities || {};
  const risk = prediction.risk_level || "medium";
  const fixtureId = match.fixture_id || match.id;

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
      <p className="text-xs text-[#94A3B8]">All available markets from cached prediction</p>
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
      {Array.isArray(prediction.recommended_bets) && prediction.recommended_bets.length > 0 && (
        <div className="rounded-lg border border-[#FFD166]/20 bg-[#FFD166]/5 p-3">
          <p className="text-[10px] uppercase text-[#FFD166] mb-2">Recommended bets</p>
          {prediction.recommended_bets.slice(0, 5).map((b, i) => (
            <p key={i} className="text-xs text-[#94A3B8]">
              {b.market}: {b.pick} ({b.status})
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
