import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, Server, Users, Zap, FlaskConical, Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchOwnerOverview } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

function StatTile({ label, value, tone = "green" }) {
  const toneClass =
    tone === "gold" ? "text-[#FFD166]" : tone === "cyan" ? "text-[#67E8F9]" : "text-[#00E676]";
  return (
    <IntelligenceCard>
      <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${toneClass}`}>{value}</p>
    </IntelligenceCard>
  );
}

export default function OwnerCommandCenter() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerOverview());
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
  if (error) return <ErrorState message={error} onRetry={load} type="forbidden" />;

  const health = data?.health || {};
  const users = data?.users || {};
  const api = data?.api_quota || {};
  const auto = data?.autonomous || {};

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="intel-page-hero border-[#FFD166]/15">
        <h1 className="text-2xl font-bold text-[#FFD166]">System Overview</h1>
        <p className="text-sm text-[#94A3B8] mt-2">
          Enterprise command center — health, queue, autonomous runtime, and platform status.
        </p>
        <div className="flex flex-wrap gap-2 mt-4">
          <Button asChild size="sm" variant="outline" className="border-[#FFD166]/30">
            <Link to="/owner/autonomous"><FlaskConical className="w-4 h-4 mr-2" />Autonomous</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/owner/monitoring"><Activity className="w-4 h-4 mr-2" />Monitoring</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/owner/notifications"><Bell className="w-4 h-4 mr-2" />Notifications</Link>
          </Button>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile label="Postgres" value={health.postgres || "—"} tone="cyan" />
        <StatTile label="Users" value={users.total ?? "—"} />
        <StatTile label="API calls today" value={api.calls_today ?? "—"} tone="gold" />
        <StatTile label="Predictions today" value={auto.predictions_today ?? 0} />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <IntelligenceCard glow>
          <h2 className="font-semibold flex items-center gap-2 text-[#F8FAFC]">
            <Server className="w-4 h-4 text-[#00E676]" /> Health
          </h2>
          <ul className="mt-3 space-y-2 text-sm text-[#94A3B8]">
            <li>API: {health.api}</li>
            <li>Prediction engine: {health.prediction_engine}</li>
            <li>PostgreSQL: {health.postgres}</li>
          </ul>
        </IntelligenceCard>
        <IntelligenceCard>
          <h2 className="font-semibold flex items-center gap-2 text-[#F8FAFC]">
            <Zap className="w-4 h-4 text-[#FFD166]" /> Autonomous Runtime
          </h2>
          <ul className="mt-3 space-y-2 text-sm text-[#94A3B8]">
            <li>Platform: {auto.platform_enabled ? "enabled" : "disabled"}</li>
            <li>Consecutive successes: {auto.consecutive_successes ?? 0} / {auto.required_for_scheduler ?? 3}</li>
            <li>Scheduler: {auto.scheduler_enabled ? "on" : "off"}</li>
            <li>Evaluations today: {auto.evaluations_today ?? 0}</li>
          </ul>
        </IntelligenceCard>
      </div>

      <IntelligenceCard>
        <h2 className="font-semibold flex items-center gap-2">
          <Users className="w-4 h-4" /> Subscriptions
        </h2>
        <p className="text-sm text-[#94A3B8] mt-2">Paid subscribers: {users.paid ?? "—"}</p>
      </IntelligenceCard>
    </div>
  );
}
