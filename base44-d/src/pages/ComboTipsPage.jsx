import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Layers, Plus, RefreshCw, Sparkles } from "lucide-react";
import { fetchMatches } from "@/api/worldcupApi";
import { buildCombos, formatStars, comboReadiness, comboEmptyReason } from "@/lib/comboGenerator";
import { isComboEligible, COMBO_QUALITY_THRESHOLDS } from "@/lib/betQualityOverlay";
import { useBetSlip } from "@/context/BetSlipContext";
import { Button } from "@/components/ui/button";
import SaasPageHeader, { SaasCard } from "@/components/saas/SaasPageHeader";
import BetSlipDrawer from "@/components/match-center/BetSlipDrawer";
import AddToPaperBetButton from "@/components/paper-betting/AddToPaperBetButton";
import ShareButton from "@/components/social/ShareButton";

const RISK_COLORS = {
  Low: "border-emerald-200 bg-emerald-50",
  Medium: "border-amber-200 bg-amber-50",
  High: "border-red-200 bg-red-50",
};

export default function ComboTipsPage() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { addLeg, clearSlip } = useBetSlip();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMatches({
        competition: "all",
        status: "upcoming",
        page: 1,
        page_size: 200,
        has_prediction: true,
        include_summary: true,
      });
      setMatches(res.matches || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load predictions");
      setMatches([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const combos = useMemo(() => buildCombos(matches), [matches]);
  const candidateCount = useMemo(
    () => matches.filter((m) => isComboEligible(m.prediction_summary, COMBO_QUALITY_THRESHOLDS.high_odds)).length,
    [matches]
  );
  const emptyReason = useMemo(() => comboEmptyReason(matches), [matches]);

  const addComboToSlip = (combo) => {
    clearSlip();
    combo.legs.forEach((leg) => addLeg(leg));
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-24">
      <SaasPageHeader
        eyebrow="Accumulator builder"
        title="Combo Builder"
        subtitle="Suggested 2–6 leg combos from strong individual picks. Combined bets are higher risk — research only, not betting advice."
      />

      <SaasCard className="p-4 border-amber-200 bg-amber-50/80">
        <p className="text-sm text-amber-900">
          We do not guarantee profit. Combined probability is an estimate only. Higher leg counts increase risk.
        </p>
      </SaasCard>

      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={load} disabled={loading} className="border-slate-200">
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {error && <SaasCard className="p-4 text-red-600 border-red-200">{error}</SaasCard>}

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-amber-200 border-t-amber-500 rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-4">
          {combos.length === 0 && (
            <SaasCard className="text-center py-12 p-6 text-slate-500">
              <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-40" />
              {emptyReason || (matches.length === 0
                ? "No upcoming fixtures with cached predictions."
                : `Not enough qualifying legs from ${candidateCount} quality-eligible predictions.`)}
            </SaasCard>
          )}
          {combos.map((combo) => (
            <div
              key={combo.id}
              className={`rounded-2xl border p-5 bg-white shadow-sm ${RISK_COLORS[combo.risk] || RISK_COLORS.Medium}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                <div>
                  <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                    <Layers className="w-5 h-5 text-amber-600" /> {combo.label}
                  </h2>
                  <p className="text-sm text-slate-500 mt-1">
                    {combo.leg_count} matches · Risk {combo.risk}
                    {combo.combined_quality != null ? ` · Avg quality ${combo.combined_quality}` : ""}
                  </p>
                  {combo.caution_warning && (
                    <p className="text-xs text-[#FF9F43] mt-1">{combo.caution_warning}</p>
                  )}
                </div>
                <div className="text-right">
                  <p className="text-2xl font-bold text-[#FFD166]">
                    {combo.combined_odds ? combo.combined_odds.toFixed(2) : "—"}
                  </p>
                  <p className="text-xs text-[#94A3B8]">
                    Combined odds{combo.legs.some((l) => l.odds_estimated) ? " (est.)" : ""}
                  </p>
                  {combo.combined_confidence != null && (
                    <p className="text-sm text-[#00E676] mt-1">Confidence {combo.combined_confidence}%</p>
                  )}
                </div>
              </div>

              <div className="space-y-2 mb-4">
                {combo.legs.map((leg, i) => (
                  <div key={i} className="rounded-xl bg-black/25 border border-white/[0.05] px-3 py-2 text-sm">
                    <p className="text-[#64748B] text-xs">{leg.home_team} vs {leg.away_team}</p>
                    <p className="text-[#F8FAFC] font-medium">{leg.label}</p>
                    <p className="text-[11px] text-[#94A3B8] mt-0.5">
                      {formatStars(leg.stars)} {leg.confidence ? `· ${Math.round(leg.confidence)}%` : ""}
                      {" · "}
                      <span className={
                        leg.readiness?.status === "ready"
                          ? "text-[#00E676]"
                          : leg.readiness?.status === "caution"
                            ? "text-[#FF9F43]"
                            : "text-[#64748B]"
                      }>
                        {leg.readiness?.label || "—"}
                      </span>
                    </p>
                  </div>
                ))}
              </div>

              <Button
                type="button"
                className="bg-[#00E676] text-[#0B1220] hover:bg-[#00E676]/90"
                onClick={() => addComboToSlip(combo)}
              >
                <Plus className="w-4 h-4 mr-1" /> Add combo to bet slip
              </Button>
              <AddToPaperBetButton
                label="Track This Combo"
                combo={{
                  legs: combo.legs,
                  combo_type: combo.id,
                  source_page: "combo-tips",
                }}
              />
              <ShareButton
                type="combo"
                label="Share combo"
                payload={{
                  combo_type: combo.id,
                  label: combo.label,
                  combined_odds: combo.combinedOdds,
                  legs: (combo.legs || []).map((leg) => ({
                    fixture_id: leg.fixture_id,
                    home_team: leg.home,
                    away_team: leg.away,
                    market: leg.marketKey,
                    market_label: leg.marketLabel,
                    prediction: leg.pick,
                    bet_quality_score: leg.betQualityScore,
                    odds_decimal: leg.odds,
                  })),
                }}
              />
            </div>
          ))}
        </div>
      )}

      <p className="text-center text-sm text-[#64748B]">
        Prefer single-match analysis? <Link to="/matches" className="text-[#00E676] hover:underline">Open Match Center</Link>
      </p>

      <BetSlipDrawer />
    </div>
  );
}
