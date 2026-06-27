import React, { useEffect, useState } from "react";
import { Shield, Loader2 } from "lucide-react";
import PasswordInput from "@/components/auth/PasswordInput";
import { Button } from "@/components/ui/button";

/**
 * Second-factor admin gate — key verified server-side only.
 * @param {"admin"|"super_admin"} gate
 */
export default function AdminGatePrompt({
  gate = "admin",
  onVerified,
  checkStatus,
  verifyKey,
}) {
  const [accessKey, setAccessKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [locked, setLocked] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const status = await checkStatus();
        if (cancelled) return;
        const passed =
          gate === "super_admin"
            ? status?.super_admin_gate_passed
            : status?.admin_gate_passed;
        if (passed) {
          onVerified?.();
          return;
        }
        setLocked(Boolean(status?.locked));
        setRetryAfter(Number(status?.retry_after_seconds || 0));
      } catch {
        if (!cancelled) setError("Access denied.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [checkStatus, gate, onVerified]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (locked || !accessKey.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await verifyKey(accessKey.trim());
      setAccessKey("");
      onVerified?.();
    } catch (err) {
      const detail = err?.detail;
      if (detail && typeof detail === "object") {
        setLocked(Boolean(detail.locked));
        setRetryAfter(Number(detail.retry_after_seconds || 0));
      }
      setError("Access denied.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto py-16 px-4">
      <div className="glass rounded-2xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
            <Shield className="w-5 h-5 text-accent" />
          </div>
          <div>
            <h2 className="font-display font-semibold">Additional verification</h2>
            <p className="text-xs text-muted-foreground">Enter your access key to continue.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <PasswordInput
            id="admin-gate-key"
            value={accessKey}
            onChange={(e) => setAccessKey(e.target.value)}
            autoComplete="off"
            placeholder="Access key"
            label="Access key"
            disabled={locked || submitting}
          />
          {error && <p className="text-sm text-red-300">{error}</p>}
          {locked && retryAfter > 0 && (
            <p className="text-xs text-muted-foreground">
              Too many attempts. Try again in {retryAfter}s.
            </p>
          )}
          <Button type="submit" className="w-full" disabled={locked || submitting || !accessKey.trim()}>
            {submitting ? "Verifying…" : "Continue"}
          </Button>
        </form>
      </div>
    </div>
  );
}
