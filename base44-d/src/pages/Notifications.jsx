import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Bell, Target, AlertCircle, CreditCard, BarChart3, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from "@/api/saasApi";

const typeIcons = {
  prediction: Target,
  system: AlertCircle,
  subscription: CreditCard,
  accuracy: BarChart3,
};

const typeColors = {
  prediction: "text-primary bg-primary/10",
  system: "text-orange-400 bg-orange-500/10",
  subscription: "text-accent bg-yellow-500/10",
  accuracy: "text-green-400 bg-green-500/10",
};

export default function Notifications() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNotifications();
      setNotifications(data.notifications || []);
    } catch (err) {
      setNotifications([]);
      setError(err instanceof Error ? err.message : "Failed to load notifications");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark notifications read");
    }
  };

  const markOneRead = async (id) => {
    try {
      await markNotificationRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark notification read");
    }
  };

  const unread = notifications.filter((n) => !n.is_read).length;

  if (loading) {
    return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" /></div>;
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold">Notifications</h1>
          <p className="text-sm text-muted-foreground mt-1">{unread} unread notification{unread !== 1 ? "s" : ""}</p>
        </div>
        {unread > 0 && (
          <Button variant="outline" size="sm" className="border-white/10 rounded-lg" onClick={markAllRead}>
            <Check className="w-4 h-4 mr-1" /> Mark all read
          </Button>
        )}
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}

      {notifications.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground glass rounded-2xl">
          <Bell className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No notifications yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {notifications.map((n, i) => {
            const Icon = typeIcons[n.type] || Bell;
            const color = typeColors[n.type] || "text-muted-foreground bg-white/5";
            return (
              <motion.div
                key={n.id || i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                onClick={() => !n.is_read && markOneRead(n.id)}
                className={`glass rounded-xl p-4 flex items-start gap-4 cursor-pointer hover:bg-white/10 ${!n.is_read ? "border-l-2 border-l-primary" : ""}`}
              >
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
                  <Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className={`text-sm font-semibold ${!n.is_read ? "text-foreground" : "text-muted-foreground"}`}>{n.title}</h3>
                    {!n.is_read && <span className="w-2 h-2 rounded-full bg-primary flex-shrink-0" />}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{n.message}</p>
                  <span className="text-xs text-muted-foreground/60 mt-2 block">
                    {n.created_date ? new Date(n.created_date).toLocaleDateString() : ""}
                  </span>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
