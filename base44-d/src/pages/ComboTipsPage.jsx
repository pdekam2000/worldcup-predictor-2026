import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Layers, Plus, RefreshCw, Sparkles } from "lucide-react";
import { fetchMatches } from "@/api/worldcupApi";
import { buildCombos, formatStars } from "@/lib/comboGenerator";
import { useBetSlip } from "@/context/BetSlipContext";
import { Button } from "@/components/ui/button";
import { SectionHeader, TerminalCard } from "@/components/terminal";
import BetSlipDrawer from "@/components/match-center/BetSlipDrawer";

const RISK_COLORS = {
  Low: "border-[#00E676]/30 bg-[#00E676]/5",
  Medium: "border-[#FFD166]/30 bg-[#FFD166]/5",
  High: "border-[#FF6B6B]/30 bg-[#FF6B6B]/5",
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
        page_size: 100,
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

  const addComboToSlip = (combo) => {
    clearSlip();
    combo.legs.forEach((leg) => addLeg(leg));
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-24">
      <SectionHeader
        eyebrow="🎯 Accumulators"
        title="Combo Tips"
        subtitle="Auto-built combos from high-quality cached predictions. Research only — not betting advice."
      />

      <TerminalCard className="border-[#FFD166]/20">
        <p className="text-sm text-[#FFD166]">Research only — not betting advice. Uses existing cached predictions only.</p>
      </TerminalCard>

      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={load} disabled={loading} className="border-white/10">
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {error && <TerminalCard className="text-red-300 border-red-500/30">{error}</TerminalCard>}

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-[#00E676]/20 border-t-[#00E676] rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-4">
          {combos.length === 0 && (
            <TerminalCard className="text-center py-12 text-[#94A3B8]">
              <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-40" />
              Not enough predicted fixtures to build combos yet.
            </TerminalCard>
          )}
          {combos.map((combo) => (
            <div
              key={combo.id}
              className={`rounded-2xl border p-5 backdrop-blur-md ${RISK_COLORS[combo.risk] || RISK_COLORS.Medium}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                <div>
                  <h2 className="text-xl font-bold text-[#F8FAFC] flex items-center gap-2">
                    <Layers className="w-5 h-5 text-[#FFD166]" /> {combo.label}
                  </h2>
                  <p className="text-sm text-[#94A3B8] mt-1">{combo.leg_count} matches · Risk {combo.risk}</p>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-bold text-[#FFD166]">
                    {combo.combined_odds ? combo.combined_odds.toFixed(2) : "—"}
                  </p>
                  <p className="text-xs text-[#94A3B8]">Combined odds</p>
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
