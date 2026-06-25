import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { buildApiUrl } from "@/lib/config";

export default function StatsSection() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(buildApiUrl("/api/system/summary"));
        if (!res.ok) throw new Error("unavailable");
        const data = await res.json();
        if (!cancelled) setStats(data);
      } catch {
        if (!cancelled) setStats(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const items = stats
    ? [
        { value: stats.archive?.total_predictions ?? 0, suffix: "", label: "Predictions Archived" },
        { value: stats.evaluation?.finished_evaluated ?? 0, suffix: "", label: "Finished Evaluations" },
        { value: stats.evaluation?.pending ?? 0, suffix: "", label: "Pending Evaluation" },
        {
          value:
            stats.evaluation?.finished_evaluated > 0 && stats.evaluation?.overall_accuracy != null
              ? (() => {
                  const n = Number(stats.evaluation.overall_accuracy);
                  return n <= 1 ? `${Math.round(n * 1000) / 10}%`.replace("%", "") : String(Math.round(n * 10) / 10);
                })()
              : null,
          suffix:
            stats.evaluation?.finished_evaluated > 0 && stats.evaluation?.overall_accuracy != null ? "%" : "",
          label: "Platform Accuracy",
        },
      ]
    : [];

  return (
    <section className="py-20 px-4 relative">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-primary/5 to-transparent" />
      <div className="max-w-5xl mx-auto relative z-10">
        <div className="glass rounded-2xl p-8 sm:p-12">
          {loading ? (
            <p className="text-center text-sm text-muted-foreground">Loading live platform stats…</p>
          ) : !stats ? (
            <p className="text-center text-sm text-muted-foreground">
              Live platform statistics will appear here once the backend is connected.
            </p>
          ) : (
            <>
              <p className="text-center text-xs text-muted-foreground mb-8">
                Real counts from the prediction archive — finished-match accuracy only when evaluations exist.
              </p>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
                {items.map((s, i) => (
                  <motion.div
                    key={s.label}
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1 }}
                    className="text-center"
                  >
                    <div className="text-3xl sm:text-4xl font-display font-bold text-gradient-blue">
                      {s.value == null ? "—" : `${s.value.toLocaleString()}${s.suffix}`}
                    </div>
                    <div className="text-sm text-muted-foreground mt-2">{s.label}</div>
                  </motion.div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
