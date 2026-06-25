import React, { useCallback, useEffect, useState } from "react";
import { FlaskConical, Play, Power, PowerOff, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchOwnerAutonomousStatus,
  ownerRunAutonomousOnce,
  ownerRunAutonomousEvaluation,
  ownerRunAutonomousCertification,
  ownerEnableScheduler,
  ownerDisableScheduler,
} from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

export default function OwnerAutonomousPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchOwnerAutonomousStatus();
      setStatus(res);
    } catch (err) {
      setError(classifyApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runAction = async (key, fn) => {
    setBusy(key);
    setError(null);
    try {
      const res = await fn();
      setLastResult(res);
      await load();
    } catch (err) {
      setError(classifyApiError(err).message);
    } finally {
      setBusy("");
    }
  };

  if (loading && !status) return <LoadingSkeleton lines={5} />;
  if (error && !status) return <ErrorState message={error} onRetry={load} />;

  const auto = status || {};
  const canEnable = auto.can_enable_scheduler;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
          <FlaskConical className="w-6 h-6" /> Autonomous Runtime
        </h1>
        <p className="text-sm text-[#94A3B8] mt-1">
          Run once, evaluate, certify. Scheduler unlocks after 3 consecutive successful runs.
        </p>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      <IntelligenceCard glow>
        <div className="grid sm:grid-cols-2 gap-3 text-sm">
          <p>Last run: {auto.last_run?.at || "—"}</p>
          <p>Status: {auto.last_run?.status || auto.last_error || "—"}</p>
          <p>Success streak: {auto.consecutive_successes ?? 0} / {auto.required_for_scheduler ?? 3}</p>
          <p>Scheduler: {auto.scheduler_enabled ? "enabled" : "disabled"}</p>
        </div>
      </IntelligenceCard>

      <div className="flex flex-wrap gap-2">
        <Button disabled={!!busy} onClick={() => runAction("once", ownerRunAutonomousOnce)}>
          <Play className="w-4 h-4 mr-2" />
          {busy === "once" ? "Running…" : "Run once"}
        </Button>
        <Button variant="outline" disabled={!!busy} onClick={() => runAction("eval", ownerRunAutonomousEvaluation)}>
          <RefreshCw className="w-4 h-4 mr-2" /> Run evaluation
        </Button>
        <Button variant="outline" disabled={!!busy} onClick={() => runAction("cert", ownerRunAutonomousCertification)}>
          <ShieldCheck className="w-4 h-4 mr-2" /> Run certification
        </Button>
        <Button
          variant="outline"
          disabled={!!busy || !canEnable}
          onClick={() => runAction("enable", ownerEnableScheduler)}
          title={!canEnable ? "Requires 3 consecutive successful runs" : ""}
        >
          <Power className="w-4 h-4 mr-2" /> Enable scheduler
        </Button>
        <Button variant="outline" disabled={!!busy} onClick={() => runAction("disable", ownerDisableScheduler)}>
          <PowerOff className="w-4 h-4 mr-2" /> Disable scheduler
        </Button>
      </div>

      {lastResult && (
        <IntelligenceCard>
          <p className="text-xs uppercase text-[#94A3B8] mb-2">Last action result</p>
          <pre className="text-xs overflow-auto max-h-64 text-[#94A3B8]">
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        </IntelligenceCard>
      )}
    </div>
  );
}
