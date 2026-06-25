import React, { useCallback, useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { fetchOwnerNotifications } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

export default function OwnerNotificationsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchOwnerNotifications();
      setItems(res?.notifications || []);
    } catch (err) {
      setError(classifyApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSkeleton lines={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
        <Bell className="w-6 h-6" /> Notification Center
      </h1>
      {items.length === 0 && (
        <IntelligenceCard className="text-center text-[#94A3B8]">No notifications yet.</IntelligenceCard>
      )}
      {items.map((n) => (
        <IntelligenceCard key={n.id || n.at} className={n.level === "error" ? "border-red-500/30" : ""}>
          <p className="font-semibold text-[#F8FAFC]">{n.title}</p>
          <p className="text-sm text-[#94A3B8] mt-1">{n.detail}</p>
          <p className="text-[10px] text-[#64748B] mt-2">{n.at}</p>
        </IntelligenceCard>
      ))}
    </div>
  );
}
