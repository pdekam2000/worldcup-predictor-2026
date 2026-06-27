import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shield, BarChart3, AlertTriangle } from "lucide-react";
import { buildApiUrl } from "@/lib/config";
import {
  TRUST_RESEARCH_ONLY,
  TRUST_WINRATE_BEST_BETS,
  TRUST_NO_BET,
} from "@/lib/trustCopy";

export default function TrustStrip() {
  const [accuracy, setAccuracy] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(buildApiUrl("/api/public/accuracy"));
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && data?.data_available) {
          setAccuracy(data.accuracy_30d_pct);
        }
      } catch {
        /* optional */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="py-12 px-4">
      <div className="max-w-5xl mx-auto grid sm:grid-cols-3 gap-4">
        <div className="wc-premium-card p-5 flex gap-3">
          <Shield className="w-5 h-5 text-amber-700 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm text-slate-900">Transparent evaluation</p>
            <p className="text-xs text-slate-600 mt-1">{TRUST_WINRATE_BEST_BETS}</p>
          </div>
        </div>
        <Link to="/public/accuracy" className="wc-premium-card p-5 flex gap-3 hover:border-amber-300 transition-colors">
          <BarChart3 className="w-5 h-5 text-amber-700 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm text-slate-900">Live accuracy archive</p>
            <p className="text-xs text-slate-600 mt-1">
              {accuracy != null
                ? `Last 30 days: ${accuracy}% on evaluated best bets.`
                : "View real evaluated predictions — sample grows as matches finish."}
            </p>
          </div>
        </Link>
        <div className="wc-premium-card p-5 flex gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-700 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm text-slate-900">Research & caution</p>
            <p className="text-xs text-slate-600 mt-1">
              {TRUST_RESEARCH_ONLY} {TRUST_NO_BET}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
