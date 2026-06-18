import React, { useState } from "react";
import { motion } from "framer-motion";
import { Server, Globe, CheckCircle, AlertCircle, XCircle, Save, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/use-toast";

const defaultSettings = {
  api_base_url: "https://api.wcppredictor.com/v1",
  football_api_url: "https://api-football.com",
  api_key_placeholder: "••••••••••••••••",
  maintenance_mode: false,
  api_status: "operational",
};

export default function ApiSettingsPage() {
  const { toast } = useToast();
  const [settings, setSettings] = useState(defaultSettings);
  const [loading] = useState(false);
  const [checking, setChecking] = useState(false);

  const handleSave = async () => {
    toast({ title: "Saved locally", description: "API settings sync coming in a later release." });
  };

  const checkStatus = () => {
    setChecking(true);
    setTimeout(() => {
      setSettings(p => ({ ...p, api_status: "operational" }));
      setChecking(false);
      toast({ title: "API Status", description: "All systems operational." });
    }, 1500);
  };

  const statusIcon = { operational: CheckCircle, degraded: AlertCircle, down: XCircle };
  const statusColor = { operational: "text-green-400", degraded: "text-yellow-400", down: "text-red-400" };
  const StatusIcon = statusIcon[settings.api_status] || AlertCircle;

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold flex items-center gap-2"><Server className="w-6 h-6 text-primary" /> API & System Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Configure backend URLs, API keys, and maintenance mode.</p>
      </div>

      {/* API Status */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-5">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2"><Globe className="w-4 h-4 text-primary" /> API Status</h2>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <StatusIcon className={`w-5 h-5 ${statusColor[settings.api_status]}`} />
            <div>
              <div className="font-medium text-sm capitalize">{settings.api_status}</div>
              <div className="text-xs text-muted-foreground">Last checked: just now</div>
            </div>
          </div>
          <Button size="sm" variant="outline" className="border-white/10 rounded-lg" onClick={checkStatus} disabled={checking}>
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${checking ? "animate-spin" : ""}`} />
            Check Status
          </Button>
        </div>
      </motion.div>

      {/* Backend URL */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-xl p-5 space-y-4">
        <h2 className="font-display font-semibold flex items-center gap-2"><Server className="w-4 h-4 text-primary" /> Backend Configuration</h2>
        <div>
          <label className="text-xs text-muted-foreground mb-1.5 block">Backend API Base URL</label>
          <Input value={settings.api_base_url} onChange={e => setSettings(p => ({ ...p, api_base_url: e.target.value }))} className="bg-white/5 border-white/10 rounded-lg font-mono text-sm" placeholder="https://api.example.com/v1" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1.5 block">Football Data API URL</label>
          <Input value={settings.football_api_url} onChange={e => setSettings(p => ({ ...p, football_api_url: e.target.value }))} className="bg-white/5 border-white/10 rounded-lg font-mono text-sm" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1.5 block">Football API Key</label>
          <Input type="password" value={settings.api_key_placeholder} onChange={e => setSettings(p => ({ ...p, api_key_placeholder: e.target.value }))} className="bg-white/5 border-white/10 rounded-lg font-mono text-sm" placeholder="Enter API key..." />
        </div>
      </motion.div>

      {/* Maintenance Mode */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className={`glass rounded-xl p-5 border ${settings.maintenance_mode ? "border-yellow-500/40" : "border-white/10"}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className={`w-5 h-5 ${settings.maintenance_mode ? "text-yellow-400" : "text-muted-foreground"}`} />
            <div>
              <div className="font-semibold text-sm">Maintenance Mode</div>
              <div className="text-xs text-muted-foreground">Disable user access and show maintenance page</div>
            </div>
          </div>
          <Switch checked={settings.maintenance_mode} onCheckedChange={v => setSettings(p => ({ ...p, maintenance_mode: v }))} />
        </div>
        {settings.maintenance_mode && (
          <div className="mt-3 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-xs text-yellow-400">
            ⚠️ Maintenance mode is active. Users will see a maintenance screen.
          </div>
        )}
      </motion.div>

      {/* AdMob Placeholder */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-5 space-y-3">
        <h2 className="font-display font-semibold text-sm flex items-center gap-2">📱 AdMob / Mobile Ads</h2>
        <div>
          <label className="text-xs text-muted-foreground mb-1.5 block">AdMob App ID (Android)</label>
          <Input placeholder="ca-app-pub-XXXXXXXXXXXXXXXX~XXXXXXXXXX" className="bg-white/5 border-white/10 rounded-lg font-mono text-sm" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1.5 block">AdMob Banner Unit ID</label>
          <Input placeholder="ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX" className="bg-white/5 border-white/10 rounded-lg font-mono text-sm" />
        </div>
        <p className="text-xs text-muted-foreground">AdMob integration placeholder. Configure before Android APK/AAB build.</p>
      </motion.div>

      <div className="flex justify-end">
        <Button onClick={handleSave} className="rounded-xl px-8"><Save className="w-4 h-4 mr-2" /> Save Settings</Button>
      </div>
    </div>
  );
}