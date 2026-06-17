import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { motion } from "framer-motion";
import { Bell, Zap, Target, CheckCircle, Settings2, BellOff } from "lucide-react";
import { Switch } from "@/components/ui/switch";

const mockAlerts = [
  { id: "1", type: "high_confidence", title: "High Confidence Pick", message: "Bayern Munich vs Dortmund — 82% confidence prediction available", confidence: 82, is_read: false, created_date: new Date().toISOString() },
  { id: "2", type: "match_result", title: "Match Result In", message: "Arsenal vs Chelsea — Your prediction was CORRECT ✅", is_read: false, created_date: new Date(Date.now() - 3600000).toISOString() },
  { id: "3", type: "new_prediction", title: "New Prediction", message: "PSG vs Marseille — New AI prediction ready to view", is_read: true, created_date: new Date(Date.now() - 7200000).toISOString() },
];

const alertConfig = {
  high_confidence: { icon: Zap, color: "text-accent", bg: "bg-yellow-500/10" },
  match_result: { icon: CheckCircle, color: "text-green-400", bg: "bg-green-500/10" },
  new_prediction: { icon: Target, color: "text-primary", bg: "bg-primary/10" },
  system: { icon: Bell, color: "text-muted-foreground", bg: "bg-white/5" },
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [prefs, setPrefs] = useState({ newPredictions: true, highConfidence: true, matchResults: true });

  useEffect(() => {
    const load = async () => {
      try {
        const user = await base44.auth.me();
        const data = await base44.entities.Alert.filter({ user_id: user.id }, "-created_date", 30);
        setAlerts(data.length > 0 ? data : mockAlerts);
      } catch {
        setAlerts(mockAlerts);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const markRead = async (id) => {
    try { await base44.entities.Alert.update(id, { is_read: true }); } catch {}
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, is_read: true } : a));
  };

  const unreadCount = alerts.filter(a => !a.is_read).length;

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold flex items-center gap-2">
            <Bell className="w-6 h-6 text-primary" /> Alerts
            {unreadCount > 0 && <span className="ml-1 px-2 py-0.5 rounded-full bg-primary text-primary-foreground text-xs font-semibold">{unreadCount}</span>}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Notifications for predictions, results, and high-confidence matches.</p>
        </div>
      </div>

      {/* Alert preferences */}
      <div className="glass rounded-xl p-5">
        <h2 className="font-semibold text-sm mb-4 flex items-center gap-2"><Settings2 className="w-4 h-4 text-primary" /> Alert Preferences</h2>
        <div className="space-y-3">
          {[
            { key: "newPredictions", label: "New Predictions", desc: "When a new AI prediction is available" },
            { key: "highConfidence", label: "High Confidence Matches", desc: "When confidence is above 75%" },
            { key: "matchResults", label: "Match Results", desc: "When a predicted match ends" },
          ].map(item => (
            <div key={item.key} className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{item.label}</div>
                <div className="text-xs text-muted-foreground">{item.desc}</div>
              </div>
              <Switch checked={prefs[item.key]} onCheckedChange={v => setPrefs(p => ({ ...p, [item.key]: v }))} />
            </div>
          ))}
        </div>
      </div>

      {/* Alert list */}
      {loading ? (
        <div className="flex justify-center py-10"><div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" /></div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-16 glass rounded-2xl">
          <BellOff className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-30" />
          <p className="text-muted-foreground">No alerts yet.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert, i) => {
            const ac = alertConfig[alert.type] || alertConfig.system;
            return (
              <motion.div key={alert.id || i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                onClick={() => !alert.is_read && markRead(alert.id)}
                className={`glass rounded-xl p-4 flex items-start gap-3 cursor-pointer transition-all hover:bg-white/10 ${!alert.is_read ? "border-l-2 border-primary" : ""}`}>
                <div className={`w-9 h-9 rounded-xl ${ac.bg} flex items-center justify-center flex-shrink-0`}>
                  <ac.icon className={`w-4 h-4 ${ac.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className={`text-sm font-medium ${!alert.is_read ? "" : "text-muted-foreground"}`}>{alert.title}</p>
                    <span className="text-xs text-muted-foreground flex-shrink-0">{new Date(alert.created_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{alert.message}</p>
                  {alert.confidence && <span className="text-xs font-semibold text-accent mt-1 inline-block">{alert.confidence}% confidence</span>}
                </div>
                {!alert.is_read && <div className="w-2 h-2 rounded-full bg-primary flex-shrink-0 mt-1.5" />}
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}