import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BarChart3 } from "lucide-react";
import { fetchPublicAccuracy } from "@/api/socialTrustApi";
import PageMeta from "@/components/social/PageMeta";
import TrustWidgets from "@/components/social/TrustWidgets";
import { TerminalCard } from "@/components/terminal";
import { TRUST_WINRATE_BEST_BETS, TRUST_RESEARCH_ONLY } from "@/lib/trustCopy";

export default function PublicAccuracyPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPublicAccuracy()
      .then((d) => setData(d.accuracy))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  const title = "Public Accuracy — WorldCup Predictor";
  const desc = data?.data_available
    ? `Last 30 days: ${data.accuracy_30d_pct}% on ${data.accuracy_30d_sample} evaluated 1X2 picks.`
    : "Real evaluated prediction accuracy from our archive.";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <PageMeta title={title} description={desc} />
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" /> Home
        </Link>
        <h1 className="text-2xl font-display font-bold flex items-center gap-2">
          <BarChart3 className="w-7 h-7 text-primary" /> Public Accuracy
        </h1>
        <p className="text-muted-foreground text-sm">{desc}</p>
        <p className="text-xs text-muted-foreground">{TRUST_WINRATE_BEST_BETS}</p>

        <TrustWidgets trust={data} />

        {data?.markets && Object.keys(data.markets).length > 0 && (
          <TerminalCard title="By market (30 days)">
            <ul className="space-y-2 text-sm">
              {Object.entries(data.markets).map(([mk, rec]) => (
                <li key={mk} className="flex justify-between glass rounded px-3 py-2">
                  <span className="capitalize">{mk.replace(/_/g, " ")}</span>
                  <span>
                    {rec.accuracy_pct != null ? `${rec.accuracy_pct}%` : "—"} ({rec.evaluated} evaluated)
                  </span>
                </li>
              ))}
            </ul>
          </TerminalCard>
        )}

        <p className="text-xs text-muted-foreground flex gap-2 items-start glass rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 shrink-0 text-yellow-500" />
          {data?.disclaimer || TRUST_RESEARCH_ONLY}
        </p>
      </div>
    </div>
  );
}
