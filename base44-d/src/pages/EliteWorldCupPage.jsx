import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, FlaskConical, GitCompare, RefreshCw, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchEliteWorldCupPredictions } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";

function Panel({ children, className = "", glow = false }) {
  return (
    <div
      className={`rounded-xl border border-white/10 bg-card/50 p-4 sm:p-5 ${
        glow ? "shadow-lg shadow-primary/10 border-primary/20" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

const TIER_COLORS = {
  A: "text-terminal-green border-terminal-green/40 bg-terminal-green/10",
  B: "text-blue-400 border-blue-400/40 bg-blue-400/10",
  C: "text-yellow-400 border-yellow-400/40 bg-yellow-400/10",
  D: "text-muted-foreground border-white/10 bg-white/5",
};

const MARKET_OPTIONS = [
  { value: "all", label: "All markets" },
  { value: "1x2", label: "1X2" },
  { value: "first_goal_team", label: "First goal team" },
  { value: "team_to_score_first", label: "Team to score first" },
  { value: "goal_timing", label: "Goal timing" },
];

function formatPick(pred) {
  if (pred == null) return "—";
  if (typeof pred === "object" && !Array.isArray(pred)) {
    const top = Object.entries(pred).sort((a, b) => (b[1] || 0) - (a[1] || 0))[0];
    return top ? `${top[0]}` : JSON.stringify(pred);
  }
  if (Array.isArray(pred)) return pred.length ? pred.join(", ") : "—";
  return String(pred);
}

function formatConfidence(value) {
  if (value == null) return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  const pct = n <= 1 ? n * 100 : n;
  return `${pct.toFixed(1)}%`;
}

function ErrorBanner({ error }) {
  if (!error) return null;
  const info = classifyApiError({ message: error });
  const tone =
    info.type === "auth_required"
      ? "border-yellow-500/40 text-yellow-200 bg-yellow-500/10"
      : info.type === "forbidden"
        ? "border-orange-500/40 text-orange-200 bg-orange-500/10"
        : info.type === "not_found"
          ? "border-slate-500/40 text-slate-200 bg-slate-500/10"
          : "border-red-500/40 text-red-200 bg-red-500/10";
  return (
    <div className={`rounded-lg border p-4 text-sm ${tone}`}>
      {info.message}
    </div>
  );
}

export default function EliteWorldCupPage() {
  const [fixtures, setFixtures] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [marketFilter, setMarketFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEliteWorldCupPredictions({
        market: marketFilter,
        tier: tierFilter,
        status: statusFilter,
        limit: 100,
      });
      setFixtures(data.fixtures || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "Failed to load elite predictions");
      setFixtures([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [marketFilter, tierFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-terminal-green text-sm uppercase tracking-widest mb-1">
            <FlaskConical className="h-4 w-4" />
            Experimental
          </div>
          <h1 className="text-2xl font-bold terminal-gradient-text flex items-center gap-2">
            <Trophy className="h-6 w-6 text-terminal-green" />
            Elite World Cup Predictions
          </h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
            Elite Experimental / Shadow-based research output. Research statistics and experimental
            predictions. Not betting advice. Does not replace production picks.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <Panel className="border-yellow-500/30 bg-yellow-500/5">
        <div className="flex gap-3 text-sm text-yellow-200/90">
          <AlertTriangle className="h-5 w-5 shrink-0 text-yellow-400" />
          <span>
            Research statistics and experimental predictions. Not betting advice. Production World Cup
            picks remain on the main dashboard and match center.
          </span>
        </div>
      </Panel>

      <div className="flex flex-wrap gap-2">
        <select
          className="bg-background border border-border rounded-md px-3 py-1.5 text-sm"
          value={marketFilter}
          onChange={(e) => setMarketFilter(e.target.value)}
        >
          {MARKET_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          className="bg-background border border-border rounded-md px-3 py-1.5 text-sm"
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
        >
          <option value="all">All tiers</option>
          {["A", "B", "C", "D"].map((t) => (
            <option key={t} value={t}>
              Tier {t}
            </option>
          ))}
        </select>
        <select
          className="bg-background border border-border rounded-md px-3 py-1.5 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>
          <option value="evaluated">Evaluated</option>
        </select>
      </div>

      <ErrorBanner error={error} />

      {loading && !fixtures.length ? (
        <Panel className="text-center text-muted-foreground">Loading elite World Cup fixtures…</Panel>
      ) : null}

      {!loading && !error && fixtures.length === 0 ? (
        <Panel className="text-center text-muted-foreground">
          No elite World Cup predictions available yet.
        </Panel>
      ) : null}

      <div className="grid gap-4">
        {fixtures.map((fx) => {
          const home = fx.fixture?.home_team || "Home";
          const away = fx.fixture?.away_team || "Away";
          const kickoff = fx.fixture?.kickoff_utc || fx.generated_at || "—";
          return (
            <Panel key={fx.fixture_id} glow>
              <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                <div>
                  <div className="text-lg font-semibold">
                    {home} vs {away}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">{kickoff}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="terminal-chip text-xs border border-yellow-500/40 text-yellow-300">
                    Experimental
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full border capitalize ${
                      TIER_COLORS[fx.confidence_tier] || TIER_COLORS.D
                    }`}
                  >
                    Tier {fx.confidence_tier || "—"}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full border border-white/10 capitalize">
                    {fx.fixture_status || fx.status || "pending"}
                  </span>
                </div>
              </div>

              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {(fx.markets || []).map((m) => (
                  <div key={m.market_id} className="rounded-lg border border-border/60 p-3 bg-background/40">
                    <div className="text-xs uppercase text-muted-foreground">{m.market_id}</div>
                    <div className="font-semibold mt-1">{formatPick(m.prediction)}</div>
                    <div className="text-xs text-muted-foreground mt-1">
                      Conf {formatConfidence(m.confidence)} · {m.status || "pending"}
                    </div>
                  </div>
                ))}
              </div>

              {fx.comparison?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-border/50">
                  <div className="flex items-center gap-2 text-sm font-medium mb-2">
                    <GitCompare className="h-4 w-4 text-terminal-green" />
                    Shadow vs Production
                  </div>
                  <div className="space-y-2">
                    {fx.comparison.map((c) => (
                      <div
                        key={`${c.fixture_id}-${c.market_id}`}
                        className="text-xs grid sm:grid-cols-4 gap-2 rounded border border-border/40 p-2"
                      >
                        <span className="font-mono">{c.market_id}</span>
                        <span>Elite: {formatPick(c.elite_pick)}</span>
                        <span>Prod: {formatPick(c.production_pick) || "—"}</span>
                        <span className={c.disagrees ? "text-yellow-400" : "text-terminal-green"}>
                          {c.same_pick ? "Same pick" : c.disagrees ? "Disagrees" : "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Panel>
          );
        })}
      </div>

      {!loading && fixtures.length > 0 && (
        <p className="text-xs text-muted-foreground text-center">
          Showing {fixtures.length} of {total} World Cup elite fixtures
        </p>
      )}
    </div>
  );
}
