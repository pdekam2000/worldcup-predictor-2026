import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import PageMeta from "@/components/social/PageMeta";
import TrustWidgets from "@/components/social/TrustWidgets";
import { TerminalCard } from "@/components/terminal";
import { apiOrigin } from "@/lib/config";

const DISCLAIMER =
  "For analysis and entertainment only. Past performance does not guarantee future results.";

export default function SharePublicLayout({ fetcher, shareId, renderPayload }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!shareId) {
      setLoading(false);
      setError("Invalid share link");
      return;
    }
    setLoading(true);
    fetcher(shareId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [shareId, fetcher]);

  const og = data?.og;
  const share = data?.share;
  const payload = share?.payload;
  const pageUrl = typeof window !== "undefined" ? window.location.href : "";
  const ogImage = og?.image?.startsWith("http") ? og.image : `${apiOrigin()}${og?.image || "/og-image.png"}`;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !payload) {
    return (
      <div className="min-h-screen bg-background p-6 max-w-lg mx-auto text-center py-20">
        <p className="text-muted-foreground">{error || "Share not found"}</p>
        <Link to="/" className="text-primary hover:underline mt-4 inline-block">Home</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <PageMeta title={og?.title} description={og?.description} image={ogImage} url={pageUrl} />
      <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" /> WorldCup Predictor
        </Link>
        <h1 className="text-2xl font-display font-bold">{og?.title}</h1>
        <p className="text-sm text-muted-foreground">{og?.description}</p>

        <TerminalCard>{renderPayload(payload)}</TerminalCard>

        <TrustWidgets trust={data?.trust} />

        <p className="text-xs text-muted-foreground flex gap-2 items-start glass rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 shrink-0 text-yellow-500" />
          {payload.disclaimer || DISCLAIMER}
        </p>

        <Link to="/register" className="block text-center text-sm text-primary hover:underline">
          Create free account for full AI analysis
        </Link>
      </div>
    </div>
  );
}
