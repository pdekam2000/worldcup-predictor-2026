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
      <IntelligenceCard>
        <pre className="text-xs overflow-auto text-[#94A3B8]">{JSON.stringify(data, null, 2)}</pre>
      </IntelligenceCard>
    </div>
  );
}
