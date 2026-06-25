import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { changePassword } from "@/api/authApi";
import { fetchSettings, updateSettings } from "@/api/saasApi";
import { motion } from "framer-motion";
import { User, Globe, Bell, Moon, Shield, Save, Loader2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import PasswordInput from "@/components/auth/PasswordInput";

const PASSWORD_ERROR_MESSAGES = {
  current_password_invalid: "Current password is incorrect.",
  password_mismatch: "New password and confirmation do not match.",
  password_too_weak: "Password must be at least 8 characters.",
  password_same_as_old: "New password must be different from your current password.",
  unauthorized: "Please log in again to change your password.",
};

const DEFAULT_PREFS = {
  emailNotifications: true,
  pushNotifications: true,
  predictionAlerts: true,
  darkMode: true,
  twoFactor: false,
};

export default function SettingsPage() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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
      await load();
      toast({
        title: "Settings saved",
        description: "Your preferences have been updated.",
        duration: 4000,
      });
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

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPasswordError("");
    if (newPassword !== confirmPassword) {
      setPasswordError(PASSWORD_ERROR_MESSAGES.password_mismatch);
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError(PASSWORD_ERROR_MESSAGES.password_too_weak);
      return;
    }
    if (currentPassword === newPassword) {
      setPasswordError(PASSWORD_ERROR_MESSAGES.password_same_as_old);
      return;
    }
    setChangingPassword(true);
    try {
      await changePassword({
        currentPassword,
        newPassword,
        confirmPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast({
        title: "Password changed",
        description: "Please log in again with your new password.",
        duration: 5000,
      });
      await logout(false);
      navigate("/login", { replace: true, state: { message: "Password changed. Please log in again." } });
    } catch (err) {
      const message =
        PASSWORD_ERROR_MESSAGES[err.code] || err.message || "Could not change password.";
      setPasswordError(message);
    } finally {
      setChangingPassword(false);
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
        <div className="flex items-center justify-between mb-6 pb-6 border-b border-white/10">
          <div>
            <div className="text-sm font-medium">Two-Factor Authentication</div>
            <div className="text-xs text-muted-foreground">Coming soon — stored as preference only</div>
          </div>
          <Switch checked={settings.twoFactor} onCheckedChange={(v) => setSettings((p) => ({ ...p, twoFactor: v }))} />
        </div>
        <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Lock className="w-4 h-4 text-primary" /> Change Password</h3>
        {passwordError && (
          <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">{passwordError}</div>
        )}
        <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block" htmlFor="currentPassword">Current password</label>
            <PasswordInput
              id="currentPassword"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              leftIcon={Lock}
              label="Current password"
              disabled={changingPassword}
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block" htmlFor="newPassword">New password</label>
            <PasswordInput
              id="newPassword"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              leftIcon={Lock}
              label="New password"
              disabled={changingPassword}
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block" htmlFor="confirmPassword">Confirm new password</label>
            <PasswordInput
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              leftIcon={Lock}
              label="Confirm new password"
              disabled={changingPassword}
            />
          </div>
          <Button type="submit" variant="outline" size="sm" className="border-white/10 rounded-lg" disabled={changingPassword}>
            {changingPassword ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Changing…
              </>
            ) : (
              "Change Password"
            )}
          </Button>
        </form>
      </motion.div>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving} className="rounded-xl px-8">
          <Save className="w-4 h-4 mr-2" /> {saving ? "Saving…" : "Save Settings"}
        </Button>
      </div>
    </div>
  );
}
