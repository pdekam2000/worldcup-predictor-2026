import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import LandingNav from "@/components/landing/LandingNav";
import FooterSection from "@/components/landing/FooterSection";

function TerminalCard({ children, className = "", glow = false }) {
  return (
    <div className={`${glow ? "terminal-card-glow" : "terminal-card"} p-4 sm:p-5 ${className}`}>
      {children}
    </div>
  );
}
import { buildApiUrl } from "@/lib/config";

function pct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value}%`;
}

function StatChip({ label, value, tone = "neutral" }) {
  const toneClass =
    tone === "green"
      ? "text-terminal-green border-terminal-green/30"
      : tone === "red"
        ? "text-red-400 border-red-400/30"
        : tone === "yellow"
          ? "text-yellow-400 border-yellow-400/30"
          : "text-foreground border-border";
  return (
    <div className={`terminal-chip border ${toneClass}`}>
      <div className="text-xs uppercase tracking-wide opacity-70">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}

function BucketBar({ label, value }) {
  const width = typeof value === "number" ? Math.min(100, Math.max(0, value)) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-terminal-green">{pct(value)}</span>
      </div>
      <div className="h-2 rounded bg-muted overflow-hidden">
        <div className="h-full bg-terminal-green/70" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export default function ResearchHighlights() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(buildApiUrl("/api/research/highlights"), {
          headers: { Accept: "application/json" },
        });
        if (!res.ok) throw new Error(`Failed to load research highlights (${res.status})`);
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setError(err.message || "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const fg = data?.first_goal_distribution || {};
  const buckets = data?.bucket_distribution?.pct_of_reliable || {};
  const odds = data?.odds_bucket_stats || {};
  const quality = data?.data_quality || {};

  const oddsRows = Object.entries(odds).filter(([, v]) => v?.match_count > 0);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <LandingNav />
      <main className="max-w-6xl mx-auto px-4 py-10 space-y-8">
        <div className="space-y-2">
          <p className="text-sm text-terminal-green uppercase tracking-widest">Research Lab</p>
          <h1 className="text-3xl sm:text-4xl font-bold terminal-gradient-text">Research Highlights</h1>
          <p className="text-muted-foreground max-w-2xl">
            Aggregated football research from completed matches. {data?.disclaimer || "Research stats, not betting advice."}
          </p>
          {data?.generated_at && (
            <p className="text-xs text-muted-foreground">Last updated: {data.generated_at}</p>
          )}
        </div>

        {loading && (
          <TerminalCard className="text-center text-muted-foreground">Loading research highlights…</TerminalCard>
        )}
        {error && (
          <TerminalCard className="border-red-500/40 text-red-300">
            {error}. Run Phase 60C locally to generate artifacts, or check API availability.
          </TerminalCard>
        )}

        {data && (
          <>
            <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatChip label="First goal 1–30" value={pct(fg.first_goal_1_30_pct)} tone="green" />
              <StatChip label="First goal 31+" value={pct(fg.first_goal_31_plus_pct)} tone="yellow" />
              <StatChip label="No goal (0-0)" value={pct(fg.no_goal_pct)} tone="neutral" />
              <StatChip
                label="Sample (with goal)"
                value={fg.sample_size_with_goal ?? "—"}
                tone="neutral"
              />
            </section>

            <TerminalCard glow>
              <h2 className="terminal-section-title mb-4">First Goal Minute Buckets</h2>
              <div className="grid md:grid-cols-2 gap-4">
                {["1-15", "16-30", "31-45+", "46-60", "61-75", "76-90+", "no_goal"].map((key) => (
                  <BucketBar key={key} label={key} value={buckets[key]} />
                ))}
              </div>
            </TerminalCard>

            <TerminalCard>
              <h2 className="terminal-section-title mb-4">Favorite Odds Buckets</h2>
              {oddsRows.length === 0 ? (
                <p className="text-muted-foreground text-sm">No odds bucket data available yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground border-b border-border">
                        <th className="py-2 pr-3">Bucket</th>
                        <th className="py-2 pr-3">N</th>
                        <th className="py-2 pr-3">Fav win%</th>
                        <th className="py-2 pr-3">O2.5%</th>
                        <th className="py-2 pr-3">BTTS%</th>
                        <th className="py-2">FG 1–30%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {oddsRows.map(([label, row]) => (
                        <tr key={label} className="border-b border-border/50">
                          <td className="py-2 pr-3 font-medium">{label}</td>
                          <td className="py-2 pr-3">{row.match_count}</td>
                          <td className="py-2 pr-3 text-terminal-green">{pct(row.favorite_win_pct)}</td>
                          <td className="py-2 pr-3">{pct(row.over_25_pct)}</td>
                          <td className="py-2 pr-3">{pct(row.btts_yes_pct)}</td>
                          <td className="py-2">{pct(row.first_goal_1_30_pct)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </TerminalCard>

            <TerminalCard>
              <h2 className="terminal-section-title mb-4">Data Quality</h2>
              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Reliable fixtures</div>
                  <div className="text-xl font-semibold text-terminal-green">{quality.reliable_fixtures ?? "—"}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Excluded (missing events)</div>
                  <div className="text-xl font-semibold text-yellow-400">{quality.excluded_fixtures ?? "—"}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">API calls (backfill)</div>
                  <div className="text-xl font-semibold">{quality.api_calls_used ?? 0}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Fixtures backfilled</div>
                  <div className="text-xl font-semibold">{quality.fixtures_backfilled ?? 0}</div>
                </div>
              </div>
              {quality.coverage_warning && (
                <p className="mt-4 text-sm text-yellow-400/90 border border-yellow-500/20 rounded-md p-3 bg-yellow-500/5">
                  {quality.coverage_warning}
                </p>
              )}
            </TerminalCard>

            <p className="text-center text-sm text-muted-foreground">
              <Link to="/login" className="text-terminal-green hover:underline">
                Sign in
              </Link>{" "}
              for predictions and match intelligence.
            </p>
          </>
        )}
      </main>
      <FooterSection />
    </div>
  );
}
