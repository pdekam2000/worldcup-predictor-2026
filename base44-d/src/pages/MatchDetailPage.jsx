import React, { useState, useEffect, useCallback } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { ArrowLeft, Cloud, Users, BarChart3, Trophy, Brain, LineChart, Activity } from "lucide-react";
import { fetchCachedPrediction, runPrediction, normalizePredictionPayload } from "@/api/worldcupApi";
import { Button } from "@/components/ui/button";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import PredictionExpandPanel from "@/components/match-center/PredictionExpandPanel";
import DataQualityBadge from "@/components/match/DataQualityBadge";
import PredictionCacheBanner from "@/components/match/PredictionCacheBanner";
import { formatKickoff } from "@/lib/matchCenterUtils";
import { formatStars } from "@/lib/comboGenerator";
import { useBetSlip } from "@/context/BetSlipContext";
import BetSlipDrawer from "@/components/match-center/BetSlipDrawer";

const TABS = [
  { id: "overview", label: "Overview", icon: Trophy },
  { id: "predictions", label: "Predictions", icon: Brain },
  { id: "full", label: "Full Analysis", icon: Activity },
];

/**
 * Premium match detail shell — reuses existing PredictionDetail for full engine output.
 * Does not modify prediction engine; only routes competition context and tab layout.
 */
export default function MatchDetailPage() {
  const { fixtureId } = useParams();
  const [searchParams] = useSearchParams();
  const competition = searchParams.get("competition") || undefined;
  const [tab, setTab] = useState("overview");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { addLeg } = useBetSlip();

  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      let payload;
      if (force) {
        payload = await runPrediction(fixtureId, { competition, forceRefresh: force });
      } else {
        const cached = await fetchCachedPrediction(fixtureId, { competition });
        if (cached.cached) payload = cached.data;
        else payload = await runPrediction(fixtureId, { competition });
      }
      setData(normalizePredictionPayload(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load match");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fixtureId, competition]);

  useEffect(() => {
    load(false);
  }, [load]);

  if (tab === "full") {
    const qs = competition ? `?competition=${encodeURIComponent(competition)}` : "";
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link to={`/matches/${fixtureId}${qs}`}>
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to overview
          </Link>
        </Button>
        <p className="text-sm text-[#94A3B8]">
          Opening legacy full analysis view…{" "}
          <Link to={`/prediction/${fixtureId}${qs}`} className="text-[#00E676] underline">
            View full prediction page
          </Link>
        </p>
      </div>
    );
  }

  const summary = data?.prediction_summary;
  const kickoff = data?.kickoff_utc || data?.match_date;
  const { date, time } = formatKickoff(kickoff);

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-24">
      <div className="flex flex-wrap items-center gap-3">
        <Button asChild variant="ghost" size="sm" className="text-[#94A3B8]">
          <Link to="/matches"><ArrowLeft className="w-4 h-4 mr-1" /> Match Center</Link>
        </Button>
        <div className="flex gap-2 ml-auto">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                  tab === t.id
                    ? "bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30"
                    : "bg-white/[0.03] text-[#94A3B8] border-white/[0.06]"
                }`}
              >
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-gradient-to-br from-[#101827] to-[#0B1220] p-6 backdrop-blur-xl">
        {loading && <p className="text-[#94A3B8]">Loading match intelligence…</p>}
        {error && <p className="text-red-300">{error}</p>}
        {data && (
          <>
            <MatchTeamsRow
              homeTeam={data.home_team}
              awayTeam={data.away_team}
              homeLogo={data.home_team_logo}
              awayLogo={data.away_team_logo}
              size="lg"
              className="mb-4"
            />
            <p className="text-sm text-[#94A3B8]">{date} · {time}</p>
            {data.venue && <p className="text-xs text-[#64748B] mt-1">{data.venue}</p>}
          </>
        )}
      </div>

      {data && tab === "overview" && (
        <div className="grid md:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Trophy className="w-4 h-4 text-[#FFD166]" /> Best Pick</h2>
            <p className="text-xl font-bold text-white">{data.best_available_pick?.pick || data.prediction || "—"}</p>
            <p className="text-[#FFD166] mt-2">{formatStars(data.pick_tier === "elite" ? 5 : 4)}</p>
            {data.confidence != null && <p className="text-sm text-[#94A3B8] mt-2">Confidence {Math.round(data.confidence)}%</p>}
            <DataQualityBadge quality={data.data_quality} className="mt-3" />
          </div>
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-3">
            <h2 className="font-semibold flex items-center gap-2"><BarChart3 className="w-4 h-4" /> Intelligence signals</h2>
            {data.weather_intelligence?.available && (
              <p className="text-xs text-[#94A3B8] flex items-center gap-2"><Cloud className="w-3.5 h-3.5" /> Weather data available</p>
            )}
            {data.sportmonks_xg && (
              <p className="text-xs text-[#94A3B8] flex items-center gap-2"><LineChart className="w-3.5 h-3.5" /> xG intelligence attached</p>
            )}
            {data.specialist_summary?.agents && (
              <p className="text-xs text-[#94A3B8] flex items-center gap-2"><Users className="w-3.5 h-3.5" /> {Object.keys(data.specialist_summary.agents).length} specialist agents</p>
            )}
            <PredictionCacheBanner
              cooldownRemaining={data.refresh_cooldown_remaining_seconds}
              cooldownTotal={data.refresh_cooldown_seconds}
            />
            <Button size="sm" variant="outline" className="border-white/10" onClick={() => load(true)} disabled={loading}>
              Refresh prediction
            </Button>
          </div>
        </div>
      )}

      {data && tab === "predictions" && (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
          <h2 className="font-semibold mb-4">All markets</h2>
          <PredictionExpandPanel
            prediction={data}
            match={{
              fixture_id: fixtureId,
              competition_key: competition,
              home_team: data.home_team,
              away_team: data.away_team,
            }}
            onAddLeg={addLeg}
          />
          <p className="text-[10px] text-[#64748B] mt-4 italic">Research only — not betting advice.</p>
        </div>
      )}

      <BetSlipDrawer />
    </div>
  );
}
