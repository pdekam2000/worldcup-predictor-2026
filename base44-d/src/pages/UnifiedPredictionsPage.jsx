import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, GitCompare, RefreshCw, Sparkles } from "lucide-react";
import { fetchUnifiedEngineStatus, fetchUnifiedPrediction } from "@/api/saasApi";
import { formatPercent } from "@/lib/formatPercent";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { SectionHeader, TerminalCard } from "@/components/terminal";

const TIER_COLORS = {
  A: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  B: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  C: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  D: "bg-red-500/10 text-red-400 border-red-500/30",
};

function TierBadge({ tier }) {
  if (!tier) return null;
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${TIER_COLORS[tier] || TIER_COLORS.C}`}>
      Tier {tier}
    </span>
  );
}

export default function UnifiedPredictionsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  const [status, setStatus] = useState(null);
  const [fixtureId, setFixtureId] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchUnifiedEngineStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  const load = useCallback(async () => {
    const fid = parseInt(fixtureId, 10);
    if (!fid) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchUnifiedPrediction(fid, { compare: true });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load unified prediction");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [fixtureId]);

  const previewAllowed = status?.admin_access || status?.unified_engine_public;
  const markets = result?.markets ? Object.values(result.markets) : [];

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-24">
      <SectionHeader
        eyebrow="Hybrid engine"
        title="Unified Predictions"
        subtitle="One orchestrated view across Classic, EGIE, odds, xG, and lineups. Production output unchanged until owner enables public rollout."
      />

      <TerminalCard className="border-amber-500/25 bg-amber-500/5">
        <p className="text-sm text-amber-200/90 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Probability = chance of outcome. Confidence = model trust. Tier = recommendation strength (A–D).
            {!status?.unified_engine_public && " Public users still receive production Classic output."}
          </span>
        </p>
      </TerminalCard>

      {status && (
        <TerminalCard className="text-xs text-slate-400 grid sm:grid-cols-2 gap-2">
          <div>Engine enabled: <strong className="text-slate-200">{String(status.unified_engine_enabled)}</strong></div>
          <div>Admin preview: <strong className="text-slate-200">{String(status.unified_engine_admin_preview)}</strong></div>
          <div>Public rollout: <strong className="text-slate-200">{String(status.unified_engine_public)}</strong></div>
          <div>Compare mode: <strong className="text-slate-200">{String(status.unified_engine_compare_mode)}</strong></div>
        </TerminalCard>
      )}

      {!previewAllowed && !isAdmin && (
        <TerminalCard className="text-center py-12 text-slate-400">
          Unified engine preview is admin-only. Your account uses production Classic predictions.
        </TerminalCard>
      )}

      {(previewAllowed || isAdmin) && (
        <>
          <div className="flex flex-wrap gap-2 items-end">
            <label className="text-sm text-slate-400">
              Fixture ID
              <input
                type="number"
                value={fixtureId}
                onChange={(e) => setFixtureId(e.target.value)}
                className="block mt-1 rounded-lg border border-white/10 bg-[#0c1222] px-3 py-2 text-slate-100 w-40"
                placeholder="e.g. 12345"
              />
            </label>
            <Button onClick={load} disabled={loading || !fixtureId}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Load unified
            </Button>
          </div>

          {error && <TerminalCard className="text-red-400 border-red-500/30">{error}</TerminalCard>}

          {result?.compare_mode && (
            <TerminalCard>
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2 mb-3">
                <GitCompare className="w-4 h-4 text-emerald-400" /> Engine compare
              </h3>
              <div className="grid sm:grid-cols-3 gap-3 text-xs">
                <div className="rounded-lg border border-white/10 p-3">
                  <p className="text-slate-500 mb-1">Classic</p>
                  <p className="text-slate-200">{result.compare_mode.classic_best?.selection || "—"}</p>
                </div>
                <div className="rounded-lg border border-white/10 p-3">
                  <p className="text-slate-500 mb-1">EGIE</p>
                  <p className="text-slate-200">{result.compare_mode.egie_best?.selection || "—"}</p>
                </div>
                <div className="rounded-lg border border-emerald-500/30 p-3 bg-emerald-500/5">
                  <p className="text-emerald-400 mb-1">Unified best</p>
                  <p className="text-slate-100">{result.best_tip?.selection || "—"}</p>
                </div>
              </div>
            </TerminalCard>
          )}

          {result?.best_tip && (
            <TerminalCard className="border-emerald-500/25 glow-green">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-emerald-400 mb-1">Best overall tip</p>
                  <h2 className="text-xl font-bold text-slate-100">
                    {result.home_team} vs {result.away_team}
                  </h2>
                  <p className="text-lg text-amber-300 mt-2">{result.best_tip.selection}</p>
                  <p className="text-sm text-slate-400 mt-1">{result.best_tip.market_label}</p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <TierBadge tier={result.best_tip.tier} />
                  <span className="text-xs text-slate-400">
                    Confidence {formatPercent(result.best_tip.confidence, { digits: 0 })}
                  </span>
                </div>
              </div>
              {result.best_tip.explanation && (
                <p className="text-sm text-slate-400 mt-3">{result.best_tip.explanation}</p>
              )}
              {result.fixture_id && (
                <Link to={`/matches/${result.fixture_id}`} className="text-sm text-emerald-400 hover:underline mt-3 inline-block">
                  Open in Match Center →
                </Link>
              )}
            </TerminalCard>
          )}

          {markets.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {markets.filter((m) => m.selection).map((m) => (
                <TerminalCard key={m.market_id} className="p-4">
                  <div className="flex justify-between items-start gap-2 mb-2">
                    <p className="text-xs font-semibold uppercase text-slate-500">{m.market_label}</p>
                    <TierBadge tier={m.tier} />
                  </div>
                  <p className="text-base font-semibold text-slate-100">{m.selection}</p>
                  <div className="flex flex-wrap gap-2 mt-2 text-[10px]">
                    <span className="text-slate-500">Conf {formatPercent(m.confidence, { digits: 0 })}</span>
                    <span className="text-slate-500">Risk {m.risk_level || "—"}</span>
                    <span className="text-slate-500 flex items-center gap-1">
                      <Sparkles className="w-3 h-3" /> {m.source_engine}
                    </span>
                    {m.engine_agreement === "disagree" && (
                      <span className="text-amber-400">Engines disagree</span>
                    )}
                  </div>
                </TerminalCard>
              ))}
            </div>
          )}

          {result?.missing_data_warnings?.length > 0 && (
            <TerminalCard className="text-xs text-amber-300/80">
              Missing data: {result.missing_data_warnings.join(", ")}
            </TerminalCard>
          )}
        </>
      )}
    </div>
  );
}
