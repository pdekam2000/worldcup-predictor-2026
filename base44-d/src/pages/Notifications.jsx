import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { motion } from "framer-motion";
import { Bell, Target, AlertCircle, CreditCard, BarChart3, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

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

const mockNotifications = [
  { id: "1", type: "prediction", title: "New Predictions Available", message: "12 new match predictions for today are ready. Check the Match Center for details.", is_read: false, created_date: "2026-06-17T08:00:00Z" },
  { id: "2", type: "accuracy", title: "Weekly Accuracy Report", message: "Your weekly accuracy report is ready. This week's accuracy: 76.4%.", is_read: false, created_date: "2026-06-16T10:00:00Z" },
  { id: "3", type: "subscription", title: "Subscription Renewal", message: "Your Pro subscription will renew on July 1, 2026 for €19.00.", is_read: true, created_date: "2026-06-15T12:00:00Z" },
  { id: "4", type: "system", title: "System Maintenance", message: "Scheduled maintenance on June 20, 2026 from 02:00 to 04:00 UTC.", is_read: true, created_date: "2026-06-14T14:00:00Z" },
  { id: "5", type: "prediction", title: "High Confidence Match", message: "Bayern Munich vs Dortmund has an 82% confidence prediction. View now.", is_read: true, created_date: "2026-06-13T09:00:00Z" },
];

export default function Notifications() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    base44.entities.Notification.list("-created_date", 50)
      .then(data => setNotifications(data.length > 0 ? data : mockNotifications))
      .catch(() => setNotifications(mockNotifications))
      .finally(() => setLoading(false));
  }, []);

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
  };

  const unread = notifications.filter(n => !n.is_read).length;

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
              className={`glass rounded-xl p-4 flex items-start gap-4 ${!n.is_read ? "border-l-2 border-l-primary" : ""}`}
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
                  {new Date(n.created_date).toLocaleDateString()}
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>

      {notifications.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Bell className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No notifications yet.</p>
        </div>
      )}
    </div>
  );
}