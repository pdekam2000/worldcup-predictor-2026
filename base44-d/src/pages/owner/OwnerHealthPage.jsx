import React, { useCallback, useEffect, useState } from "react";
import { fetchOwnerMonitoring, fetchOwnerOverview } from "@/api/saasApi";
import { IntelligenceCard, LoadingSkeleton } from "@/components/intelligence";

export default function OwnerHealthPage() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setOverview(await fetchOwnerOverview());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSkeleton lines={4} />;

  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-[#FFD166]">System Health</h1>
      <IntelligenceCard glow>
        <pre className="text-xs text-[#94A3B8] overflow-auto">{JSON.stringify(overview?.health, null, 2)}</pre>
      </IntelligenceCard>
    </div>
  );
}

export function OwnerApiUsagePage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchOwnerMonitoring().then(setData).catch(() => {});
  }, []);
  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-[#FFD166]">API Usage & Coverage</h1>
      <IntelligenceCard>
        <pre className="text-xs text-[#94A3B8] overflow-auto">{JSON.stringify(data?.api_quota, null, 2)}</pre>
      </IntelligenceCard>
    </div>
  );
}

export function OwnerDatabasePage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchOwnerMonitoring().then(setData).catch(() => {});
  }, []);
  return (
    <div className="space-y-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-[#FFD166]">Database</h1>
      <IntelligenceCard>
        <p className="text-sm text-[#94A3B8]">Postgres: {data?.postgres?.reachable ? "reachable" : "unreachable"}</p>
        <p className="text-sm text-[#94A3B8] mt-2">SQLite: {data?.sqlite?.path} ({data?.sqlite?.size_mb} MB)</p>
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
