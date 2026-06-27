import React, { useCallback, useEffect, useState } from "react";
import { fetchOwnerHealthDashboard } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

const STATUS_STYLES = {
  green: "border-[#00E676]/40 bg-[#00E676]/10 text-[#00E676]",
  yellow: "border-[#FFD166]/40 bg-[#FFD166]/10 text-[#FFD166]",
  red: "border-red-500/40 bg-red-500/10 text-red-300",
};

function HealthCard({ card }) {
  const style = STATUS_STYLES[card.status] || STATUS_STYLES.red;
  return (
    <IntelligenceCard className={style}>
      <p className="text-xs uppercase tracking-wide opacity-80">{card.title}</p>
      <p className="text-lg font-semibold mt-1">{card.detail}</p>
      {card.last_run && (
        <p className="text-[10px] mt-2 opacity-70">Last run: {String(card.last_run).slice(0, 19)}</p>
      )}
    </IntelligenceCard>
  );
}

export default function OwnerHealthPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerHealthDashboard());
    } catch (err) {
      setError(classifyApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) return <LoadingSkeleton lines={6} />;
  if (error && !data) return <ErrorState message={error} onRetry={load} />;

  const cards = data?.cards || [];
  const quota = data?.monitoring?.api_quota || {};

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-[#FFD166]">System Health</h1>
        <p className="text-sm text-[#94A3B8] mt-1">
          API · Postgres · Scheduler · PredOps · Shadow · Disk · RAM · CPU
        </p>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {cards.map((card) => (
          <HealthCard key={card.id} card={card} />
        ))}
      </div>

      <IntelligenceCard>
        <h2 className="font-semibold text-[#F8FAFC] mb-2">API usage today</h2>
        <p className="text-sm text-[#94A3B8]">
          Live requests: {quota.live_requests ?? 0} · Cache hit: {quota.cache_hit_rate ?? "—"} · Risk:{" "}
          {quota.quota_risk ?? "—"}
        </p>
      </IntelligenceCard>
    </div>
  );
}

export function OwnerApiUsagePage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchOwnerHealthDashboard().then(setData).catch(() => {});
  }, []);
  const quota = data?.monitoring?.api_quota || {};
  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-[#FFD166]">API Usage & Coverage</h1>
      <IntelligenceCard>
        <p className="text-sm text-[#94A3B8]">Live requests: {quota.live_requests ?? 0}</p>
        <p className="text-sm text-[#94A3B8] mt-1">Quota risk: {quota.quota_risk ?? "—"}</p>
      </IntelligenceCard>
    </div>
  );
}

export function OwnerDatabasePage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchOwnerHealthDashboard().then(setData).catch(() => {});
  }, []);
  const pg = data?.monitoring?.postgres || {};
  const sqlite = data?.monitoring?.sqlite || {};
  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-[#FFD166]">Database</h1>
      <IntelligenceCard>
        <p className="text-sm text-[#94A3B8]">Postgres: {pg.reachable ? "reachable" : "unreachable"}</p>
        <p className="text-sm text-[#94A3B8] mt-2">SQLite: {sqlite.path} ({sqlite.size_mb} MB)</p>
      </IntelligenceCard>
    </div>
  );
}

export function OwnerLogsPage() {
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-[#FFD166] mb-4">Logs</h1>
      <IntelligenceCard>
        <p className="text-sm text-[#94A3B8]">
          Server logs: inspect via <code className="text-[#00E676]">journalctl -u worldcup-api</code> and{" "}
          <code className="text-[#00E676]">journalctl -u worldcup-autonomous</code> on the host.
        </p>
      </IntelligenceCard>
    </div>
  );
}
