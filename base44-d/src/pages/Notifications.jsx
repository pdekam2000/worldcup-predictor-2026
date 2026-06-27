import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Bell,
  Target,
  AlertCircle,
  CreditCard,
  BarChart3,
  Check,
  Ticket,
  NotebookPen,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from "@/api/saasApi";
import {
  fetchAssistantNotifications,
  markAllAssistantNotificationsRead,
  markAssistantNotificationRead,
} from "@/api/assistantApi";

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "prediction", label: "Prediction" },
  { id: "quality", label: "Quality" },
  { id: "combo", label: "Combo" },
  { id: "paper_betting", label: "Paper Betting" },
  { id: "system", label: "System" },
  { id: "archive", label: "Archive" },
];

const typeIcons = {
  prediction: Target,
  quality: Sparkles,
  combo: Ticket,
  paper_betting: NotebookPen,
  system: AlertCircle,
  subscription: CreditCard,
  accuracy: BarChart3,
  archive: BarChart3,
};

const typeColors = {
  prediction: "text-primary bg-primary/10",
  quality: "text-violet-400 bg-violet-500/10",
  combo: "text-cyan-400 bg-cyan-500/10",
  paper_betting: "text-emerald-400 bg-emerald-500/10",
  system: "text-orange-400 bg-orange-500/10",
  subscription: "text-accent bg-yellow-500/10",
  accuracy: "text-green-400 bg-green-500/10",
  archive: "text-green-400 bg-green-500/10",
};

function normalizeAssistant(n) {
  return {
    id: `asst-${n.id}`,
    assistantId: n.id,
    source: "assistant",
    type: n.category,
    title: n.title,
    message: n.message,
    is_read: Boolean(n.is_read),
    created_date: n.created_at,
    link: n.link,
  };
}

function normalizeLegacy(n) {
  return {
    ...n,
    source: "legacy",
    assistantId: null,
  };
}

export default function Notifications() {
  const [notifications, setNotifications] = useState([]);
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const cat = category === "all" ? undefined : category;
      const [legacy, assistant] = await Promise.all([
        fetchNotifications().catch(() => ({ notifications: [] })),
        fetchAssistantNotifications(cat).catch(() => ({ notifications: [] })),
      ]);
      const merged = [
        ...(assistant.notifications || []).map(normalizeAssistant),
        ...(legacy.notifications || []).map(normalizeLegacy),
      ].sort((a, b) => String(b.created_date).localeCompare(String(a.created_date)));
      setNotifications(merged);
    } catch (err) {
      setNotifications([]);
      setError(err instanceof Error ? err.message : "Failed to load notifications");
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    load();
  }, [load]);

  const markAllRead = async () => {
    try {
      await Promise.all([
        markAllNotificationsRead().catch(() => {}),
        markAllAssistantNotificationsRead().catch(() => {}),
      ]);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark notifications read");
    }
  };

  const markOneRead = async (n) => {
    try {
      if (n.source === "assistant" && n.assistantId != null) {
        await markAssistantNotificationRead(n.assistantId);
      } else {
        await markNotificationRead(n.id);
      }
      setNotifications((prev) =>
        prev.map((item) => (item.id === n.id ? { ...item, is_read: true } : item))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark notification read");
    }
  };

  const filtered =
    category === "all"
      ? notifications
      : notifications.filter((n) => n.type === category);

  const unread = notifications.filter((n) => !n.is_read).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-bold">Notifications</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {unread} unread · AI alerts & account updates
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/daily-briefing">
            <Button variant="outline" size="sm" className="border-white/10 rounded-lg">
              Daily Briefing
            </Button>
          </Link>
          {unread > 0 && (
            <Button variant="outline" size="sm" className="border-white/10 rounded-lg" onClick={markAllRead}>
              <Check className="w-4 h-4 mr-1" /> Mark all read
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setCategory(c.id)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              category === c.id
                ? "border-primary bg-primary/10 text-primary"
                : "border-white/10 text-muted-foreground hover:text-foreground"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}

      {filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground glass rounded-2xl">
          <Bell className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No notifications in this category.</p>
          <Link to="/watchlist" className="text-primary text-sm hover:underline mt-2 inline-block">
            Set up your watchlist
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((n, i) => {
            const Icon = typeIcons[n.type] || Bell;
            const color = typeColors[n.type] || "text-muted-foreground bg-white/5";
            const inner = (
              <motion.div
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                onClick={() => !n.is_read && markOneRead(n)}
                className={`glass rounded-xl p-4 flex items-start gap-4 cursor-pointer hover:bg-white/10 ${
                  !n.is_read ? "border-l-2 border-l-primary" : ""
                }`}
              >
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
                  <Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className={`text-sm font-semibold ${!n.is_read ? "text-foreground" : "text-muted-foreground"}`}>
                      {n.title}
                    </h3>
                    {!n.is_read && <span className="w-2 h-2 rounded-full bg-primary flex-shrink-0" />}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{n.message}</p>
                  <span className="text-xs text-muted-foreground/60 mt-2 block capitalize">
                    {n.type}
                    {n.created_date ? ` · ${new Date(n.created_date).toLocaleString()}` : ""}
                  </span>
                </div>
              </motion.div>
            );
            return n.link ? (
              <Link key={n.id || i} to={n.link} className="block">
                {inner}
              </Link>
            ) : (
              <div key={n.id || i}>{inner}</div>
            );
          })}
        </div>
      )}
    </div>
  );
}
