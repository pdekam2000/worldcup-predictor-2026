import React, { useCallback, useEffect, useState } from "react";
import { FlaskConical, Play, Power, PowerOff, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  const [dryRun, setDryRun] = useState(false);
  const [fixtureLimit, setFixtureLimit] = useState(10);

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
  const readiness = auto.scheduler_readiness || {};
  const canEnable = auto.can_enable_scheduler;
  const report = lastResult?.report || lastResult;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
          <FlaskConical className="w-6 h-6" /> Autonomous Runtime
        </h1>
        <p className="text-sm text-[#94A3B8] mt-1">
          Run once → review → certify. Scheduler unlocks after 3 consecutive successes.
        </p>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      <IntelligenceCard glow>
        <div className="grid sm:grid-cols-2 gap-3 text-sm">
          <p>Last run: {auto.last_run?.at || "—"}</p>
          <p>Status: {auto.last_run?.status || auto.last_error || "—"}</p>
          <p>Success streak: {auto.consecutive_successes ?? 0} / {auto.required_for_scheduler ?? 3}</p>
          <p>Scheduler: {auto.scheduler_enabled ? "enabled" : "disabled"}</p>
          <p>Readiness: {readiness.scheduler_status || "—"}</p>
          <p>API calls (last): {auto.last_run?.api_calls_used ?? "—"}</p>
          <p>Duplicates skipped: {auto.last_run?.duplicate_skipped ?? "—"}</p>
        </div>
      </IntelligenceCard>

      {readiness.blockers?.length > 0 && !canEnable && (
        <IntelligenceCard className="border-red-500/20">
          <p className="text-xs uppercase text-red-300 mb-2">Scheduler blocked</p>
          <ul className="text-sm text-[#94A3B8] list-disc pl-5 space-y-1">
            {readiness.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </IntelligenceCard>
      )}

      <IntelligenceCard>
        <div className="grid sm:grid-cols-2 gap-4 mb-4">
          <div className="flex items-center gap-2">
            <input
              id="dry-run"
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="rounded"
            />
            <Label htmlFor="dry-run" className="text-sm">Dry-run mode (no snapshots)</Label>
          </div>
          <div>
            <Label htmlFor="fixture-limit" className="text-xs text-[#94A3B8]">Fixture limit</Label>
            <Input
              id="fixture-limit"
              type="number"
              min={1}
              max={50}
              value={fixtureLimit}
              onChange={(e) => setFixtureLimit(Number(e.target.value) || 10)}
              className="h-9 mt-1"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!!busy}
            onClick={() => runAction("once", () => ownerRunAutonomousOnce({ dryRun, fixtureLimit }))}
          >
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
            title={!canEnable ? (readiness.blockers?.[0] || "Scheduler gates not met") : ""}
          >
            <Power className="w-4 h-4 mr-2" /> Enable scheduler
          </Button>
          <Button variant="outline" disabled={!!busy} onClick={() => runAction("disable", ownerDisableScheduler)}>
            <PowerOff className="w-4 h-4 mr-2" /> Disable scheduler
          </Button>
        </div>
      </IntelligenceCard>

      {report && (
        <IntelligenceCard>
          <p className="text-xs uppercase text-[#94A3B8] mb-2">Last run report</p>
          <div className="grid sm:grid-cols-2 gap-2 text-sm mb-3">
            <p>Fixtures discovered: {(report.discovery || {}).fixture_count ?? (report.discovery || {}).fixtures_discovered ?? "—"}</p>
            <p>Production snapshots: {(report.predictions || {}).production_snapshots ?? "—"}</p>
            <p>Elite snapshots: {(report.predictions || {}).elite_snapshots ?? "—"}</p>
            <p>Pending evaluations: {(report.evaluation || {}).pending ?? "—"}</p>
            <p>API calls: {report.api_calls_used ?? "—"}</p>
            <p>Errors: {(report.predictions || {}).errors ?? 0}</p>
          </div>
          <pre className="text-xs overflow-auto max-h-64 text-[#94A3B8]">
            {JSON.stringify(report, null, 2)}
          </pre>
        </IntelligenceCard>
      )}
    </div>
  );
}
