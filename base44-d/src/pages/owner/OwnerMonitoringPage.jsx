import React, { useCallback, useEffect, useState } from "react";
import { Cpu } from "lucide-react";
import { fetchOwnerMonitoring } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

export default function OwnerMonitoringPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerMonitoring());
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
  if (error) return <ErrorState message={error} onRetry={load} />;

  const sys = data?.system || {};
  const ram = sys.ram || {};
  const disk = sys.disk || {};
  const quota = data?.api_quota || {};
  const pg = data?.postgres || {};
  const sqlite = data?.sqlite || {};
  const sched = data?.scheduler || {};
  const cycles = data?.autonomous_cycles || [];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
        <Cpu className="w-6 h-6" /> Enterprise Monitoring
      </h1>
      <div className="grid sm:grid-cols-3 gap-4">
        <IntelligenceCard>
          <p className="text-xs uppercase text-[#94A3B8]">CPU</p>
          <p className="text-2xl font-bold text-[#00E676]">{sys.cpu_percent ?? "—"}%</p>
        </IntelligenceCard>
        <IntelligenceCard>
          <p className="text-xs uppercase text-[#94A3B8]">RAM</p>
          <p className="text-2xl font-bold">{ram.percent ?? "—"}%</p>
          <p className="text-xs text-[#94A3B8]">{ram.used_gb} / {ram.total_gb} GB</p>
        </IntelligenceCard>
        <IntelligenceCard>
          <p className="text-xs uppercase text-[#94A3B8]">Disk</p>
          <p className="text-2xl font-bold">{disk.percent ?? "—"}%</p>
        </IntelligenceCard>
      </div>

      <div className="grid sm:grid-cols-2 gap-4 text-sm">
        <IntelligenceCard>
          <h2 className="font-semibold text-[#F8FAFC] mb-2">Database</h2>
          <p className="text-[#94A3B8]">Postgres: {pg.reachable ? "reachable" : "unreachable"}</p>
          <p className="text-[#94A3B8] mt-1">SQLite: {sqlite.path} ({sqlite.size_mb} MB)</p>
        </IntelligenceCard>
        <IntelligenceCard>
          <h2 className="font-semibold text-[#F8FAFC] mb-2">API quota</h2>
          <p className="text-[#94A3B8]">Live requests: {quota.live_requests ?? 0}</p>
          <p className="text-[#94A3B8] mt-1">Risk: {quota.quota_risk ?? "—"} · Cache hit: {quota.cache_hit_rate ?? "—"}</p>
        </IntelligenceCard>
      </div>

      <IntelligenceCard>
        <h2 className="font-semibold text-[#F8FAFC] mb-2">Scheduler</h2>
        <p className="text-sm text-[#94A3B8]">
          {sched.timer_unit || "worldcup-autonomous.timer"} — {sched.active ? "active" : "inactive"} /{" "}
          {sched.enabled ? "enabled" : "disabled"}
        </p>
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold text-[#F8FAFC] mb-2">Recent autonomous cycles</h2>
        {cycles.length === 0 ? (
          <p className="text-sm text-[#94A3B8]">No cycle history.</p>
        ) : (
          <ul className="text-sm text-[#94A3B8] space-y-1">
            {cycles.map((c) => (
              <li key={c.id}>
                #{c.id} · {c.status} · {c.started_at || "—"}
              </li>
            ))}
          </ul>
        )}
      </IntelligenceCard>
    </div>
  );
}
