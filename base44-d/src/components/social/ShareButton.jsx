import React, { useState } from "react";
import { Check, Link2, Share2 } from "lucide-react";
import {
  absoluteShareUrl,
  createComboShare,
  createPaperReportShare,
  createPickShare,
  createPlanShare,
} from "@/api/socialTrustApi";
import { Button } from "@/components/ui/button";

const CREATORS = {
  pick: createPickShare,
  combo: createComboShare,
  plan: createPlanShare,
  paper_report: createPaperReportShare,
};

export default function ShareButton({
  type = "pick",
  payload = {},
  label = "Share",
  size = "sm",
  variant = "outline",
  requireOptIn = false,
  className = "",
}) {
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  const handleShare = async () => {
    setError(null);
    if (requireOptIn && type === "paper_report") {
      const ok = window.confirm(
        "Share anonymized virtual betting results publicly? No personal data will be included."
      );
      if (!ok) return;
      payload = { ...payload, opt_in: true };
    }
    setBusy(true);
    try {
      const create = CREATORS[type];
      if (!create) throw new Error("Unknown share type");
      const result = await create(payload);
      const path = result.share_path;
      const url = absoluteShareUrl(path);
      if (navigator.share) {
        try {
          await navigator.share({ title: result.og?.title || label, url });
          return;
        } catch {
          /* fall through to clipboard */
        }
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Share failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={className}>
      <Button type="button" variant={variant} size={size} disabled={busy} onClick={handleShare}>
        {copied ? <Check className="w-4 h-4 mr-1" /> : <Share2 className="w-4 h-4 mr-1" />}
        {copied ? "Link copied" : label}
      </Button>
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
      {copied && (
        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
          <Link2 className="w-3 h-3" /> Public link copied
        </p>
      )}
    </div>
  );
}
