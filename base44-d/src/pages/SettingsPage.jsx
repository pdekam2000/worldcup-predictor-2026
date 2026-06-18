import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/AuthContext";
import { fetchSettings, updateSettings } from "@/api/saasApi";
import { motion } from "framer-motion";
import { User, Globe, Bell, Moon, Shield, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";

const DEFAULT_PREFS = {
  emailNotifications: true,
  pushNotifications: true,
  predictionAlerts: true,
  darkMode: true,
  twoFactor: false,
};

export default function SettingsPage() {
  const { toast } = useToast();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState({
    language: "en",
    timezone: "Europe/London",
    ...DEFAULT_PREFS,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSettings();
      const s = data.settings || {};
      const prefs = s.preferences || {};
      setSettings({
        language: s.language || "en",
        timezone: s.timezone || "Europe/London",
        emailNotifications: prefs.emailNotifications ?? true,
        pushNotifications: prefs.pushNotifications ?? true,
        predictionAlerts: prefs.predictionAlerts ?? true,
        darkMode: prefs.darkMode ?? true,
        twoFactor: prefs.twoFactor ?? false,
      });
    } catch (err) {
      toast({
        title: "Could not load settings",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSettings({
        language: settings.language,
        timezone: settings.timezone,
        preferences: {
          emailNotifications: settings.emailNotifications,
          pushNotifications: settings.pushNotifications,
          predictionAlerts: settings.predictionAlerts,
          darkMode: settings.darkMode,
          twoFactor: settings.twoFactor,
        },
      });
      toast({ title: "Settings saved", description: "Your preferences have been updated." });
    } catch (err) {
      toast({
        title: "Save failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your account and preferences.</p>
      </div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-6">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2"><User className="w-5 h-5 text-primary" /> Profile</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">Full Name</label>
            <Input value={user?.full_name || ""} readOnly className="bg-white/5 border-white/10 rounded-lg" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">Email</label>
            <Input value={user?.email || ""} readOnly className="bg-white/5 border-white/10 rounded-lg" />
          </div>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-xl p-6">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2"><Globe className="w-5 h-5 text-primary" /> Language & Timezone</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">Language</label>
            <Select value={settings.language} onValueChange={(v) => setSettings((p) => ({ ...p, language: v }))}>
              <SelectTrigger className="bg-white/5 border-white/10 rounded-lg"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-card border-white/10">
                <SelectItem value="en">🇬🇧 English</SelectItem>
                <SelectItem value="de">🇩🇪 Deutsch</SelectItem>
                <SelectItem value="fa">🇮🇷 فارسی</SelectItem>
                <SelectItem value="sr">🇷🇸 Srpski</SelectItem>
                <SelectItem value="hr">🇭🇷 Hrvatski</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">Timezone</label>
            <Select value={settings.timezone} onValueChange={(v) => setSettings((p) => ({ ...p, timezone: v }))}>
              <SelectTrigger className="bg-white/5 border-white/10 rounded-lg"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-card border-white/10">
                <SelectItem value="Europe/London">Europe/London (GMT)</SelectItem>
                <SelectItem value="Europe/Berlin">Europe/Berlin (CET)</SelectItem>
                <SelectItem value="Europe/Madrid">Europe/Madrid (CET)</SelectItem>
                <SelectItem value="America/New_York">America/New York (EST)</SelectItem>
                <SelectItem value="Asia/Tokyo">Asia/Tokyo (JST)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2"><Bell className="w-5 h-5 text-primary" /> Notifications</h2>
        <div className="space-y-4">
          {[
            { key: "emailNotifications", label: "Email Notifications", desc: "Receive prediction updates via email" },
            { key: "pushNotifications", label: "Push Notifications", desc: "Browser push notifications" },
            { key: "predictionAlerts", label: "Prediction Alerts", desc: "Alert when high-confidence predictions are available" },
          ].map((item) => (
            <div key={item.key} className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{item.label}</div>
                <div className="text-xs text-muted-foreground">{item.desc}</div>
              </div>
              <Switch checked={settings[item.key]} onCheckedChange={(v) => setSettings((p) => ({ ...p, [item.key]: v }))} />
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2"><Moon className="w-5 h-5 text-primary" /> Appearance</h2>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Dark Mode</div>
            <div className="text-xs text-muted-foreground">Use dark theme throughout the app</div>
          </div>
          <Switch checked={settings.darkMode} onCheckedChange={(v) => setSettings((p) => ({ ...p, darkMode: v }))} />
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass rounded-xl p-6">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2"><Shield className="w-5 h-5 text-primary" /> Security</h2>
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-sm font-medium">Two-Factor Authentication</div>
            <div className="text-xs text-muted-foreground">Coming soon — stored as preference only</div>
          </div>
          <Switch checked={settings.twoFactor} onCheckedChange={(v) => setSettings((p) => ({ ...p, twoFactor: v }))} />
        </div>
        <Button variant="outline" size="sm" className="border-white/10 rounded-lg" disabled>Change Password</Button>
      </motion.div>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving} className="rounded-xl px-8">
          <Save className="w-4 h-4 mr-2" /> {saving ? "Saving…" : "Save Settings"}
        </Button>
      </div>
    </div>
  );
}
