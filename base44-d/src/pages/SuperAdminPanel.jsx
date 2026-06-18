import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Users, CreditCard, Server, Trophy, Target, Shield, Settings,
  CheckCircle, AlertCircle, XCircle,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import {
  fetchAdminStats,
  fetchAdminUsers,
  fetchAdminHealth,
  updateAdminUserRole,
  updateAdminUserPlan,
} from "@/api/saasApi";

const ROLES = ["user", "admin"];
const PLANS = ["free", "pro", "elite", "unlimited"];

const statusIcon = { operational: CheckCircle, degraded: AlertCircle, down: XCircle };
const statusColor = { operational: "text-green-400", degraded: "text-yellow-400", down: "text-red-400" };
const roleColor = { admin: "bg-accent/10 text-accent", user: "bg-white/5 text-muted-foreground" };
const planColor = { unlimited: "bg-red-500/10 text-red-400", elite: "bg-yellow-500/10 text-accent", pro: "bg-primary/10 text-primary", free: "bg-white/5 text-muted-foreground" };

export default function SuperAdminPanel() {
  const { toast } = useToast();
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [services, setServices] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, usersData, healthData] = await Promise.all([
        fetchAdminStats(),
        fetchAdminUsers({ limit: 200 }),
        fetchAdminHealth(),
      ]);
      setStats(statsData);
      setUsers(usersData.users || []);
      setServices(healthData.services || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRoleChange = async (userId, newRole) => {
    try {
      const data = await updateAdminUserRole(userId, newRole);
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, ...data.user } : u)));
      toast({ title: "Role updated", description: `User role set to ${newRole}` });
    } catch (err) {
      toast({
        title: "Update failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const handlePlanChange = async (userId, newPlan) => {
    try {
      await updateAdminUserPlan(userId, newPlan);
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, plan: newPlan } : u)));
      toast({ title: "Plan updated", description: `Subscription plan set to ${newPlan}` });
    } catch (err) {
      toast({
        title: "Update failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const statCards = [
    { label: "Total Users", value: stats ? String(stats.total_users) : "—", icon: Users, color: "text-primary", bg: "bg-primary/10" },
    { label: "Paid Subscribers", value: stats ? String(stats.paid_subscribers) : "—", icon: CreditCard, color: "text-green-400", bg: "bg-green-500/10" },
    { label: "Admins", value: String(users.filter((u) => u.role === "admin").length), icon: Shield, color: "text-accent", bg: "bg-yellow-500/10" },
    { label: "System Status", value: services.some((s) => s.status !== "operational") ? "Degraded" : "Healthy", icon: Server, color: "text-purple-400", bg: "bg-purple-500/10" },
  ];

  const filtered = users.filter((u) => `${u.full_name} ${u.email}`.toLowerCase().includes(search.toLowerCase()));

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
          <Shield className="w-5 h-5 text-red-400" />
        </div>
        <div>
          <h1 className="text-2xl font-display font-bold">Super Admin Panel</h1>
          <p className="text-xs text-red-400 font-medium">Admin access • PostgreSQL-backed user management</p>
        </div>
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }} className="glass rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}><s.icon className={`w-4 h-4 ${s.color}`} /></div>
            </div>
            <div className="text-2xl font-display font-bold">{s.value}</div>
          </motion.div>
        ))}
      </div>

      <Tabs defaultValue="users">
        <TabsList className="glass border-white/10 rounded-xl p-1 flex-wrap h-auto gap-1">
          {["users", "roles", "system", "leagues", "predictions", "settings"].map((tab) => (
            <TabsTrigger key={tab} value={tab} className="rounded-lg capitalize data-[state=active]:bg-primary data-[state=active]:text-primary-foreground text-xs">
              {tab}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="users" className="mt-4">
          <div className="glass rounded-xl p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
              <h2 className="font-display font-semibold">All Users</h2>
              <Input placeholder="Search users..." value={search} onChange={(e) => setSearch(e.target.value)} className="w-full sm:w-64 bg-white/5 border-white/10 rounded-lg" />
            </div>
            {filtered.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground text-sm">No users found.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground text-xs border-b border-white/10">
                      <th className="pb-3 font-medium px-2">Name</th>
                      <th className="pb-3 font-medium px-2">Email</th>
                      <th className="pb-3 font-medium px-2">Role</th>
                      <th className="pb-3 font-medium px-2">Plan</th>
                      <th className="pb-3 font-medium px-2">Joined</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {filtered.map((u) => (
                      <tr key={u.id} className="hover:bg-white/5">
                        <td className="py-3 px-2 font-medium">{u.full_name}</td>
                        <td className="py-3 px-2 text-muted-foreground text-xs">{u.email}</td>
                        <td className="py-3 px-2">
                          <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${roleColor[u.role] || roleColor.user}`}>{u.role}</span>
                        </td>
                        <td className="py-3 px-2">
                          <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${planColor[u.plan] || planColor.free}`}>{u.plan}</span>
                        </td>
                        <td className="py-3 px-2 text-muted-foreground text-xs">{u.created_date ? new Date(u.created_date).toLocaleDateString() : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="roles" className="mt-4">
          <div className="glass rounded-xl p-5 space-y-3">
            <h2 className="font-display font-semibold mb-4">Manage User Roles & Plans</h2>
            {filtered.map((u) => (
              <div key={u.id} className="flex flex-wrap items-center gap-3 p-3 rounded-lg bg-white/5">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{u.full_name}</div>
                  <div className="text-xs text-muted-foreground">{u.email}</div>
                </div>
                <Select value={u.role} onValueChange={(v) => handleRoleChange(u.id, v)}>
                  <SelectTrigger className="w-32 bg-white/5 border-white/10 rounded-lg text-xs h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-white/10">
                    {ROLES.map((r) => <SelectItem key={r} value={r} className="text-xs">{r}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={u.plan} onValueChange={(v) => handlePlanChange(u.id, v)}>
                  <SelectTrigger className="w-28 bg-white/5 border-white/10 rounded-lg text-xs h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-white/10">
                    {PLANS.map((p) => <SelectItem key={p} value={p} className="text-xs">{p}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="system" className="mt-4">
          <div className="glass rounded-xl p-5">
            <h2 className="font-display font-semibold mb-4">System Health</h2>
            <div className="space-y-3">
              {services.map((svc, i) => {
                const Icon = statusIcon[svc.status] || AlertCircle;
                return (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <div className="flex items-center gap-3">
                      <Icon className={`w-4 h-4 ${statusColor[svc.status] || "text-muted-foreground"}`} />
                      <span className="font-medium text-sm">{svc.name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground">{svc.uptime}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${svc.status === "operational" ? "bg-green-500/10 text-green-400" : svc.status === "degraded" ? "bg-yellow-500/10 text-yellow-400" : "bg-red-500/10 text-red-400"}`}>{svc.status}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="leagues" className="mt-4">
          <div className="glass rounded-xl p-5 text-center py-16 text-muted-foreground">
            <Trophy className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">League management UI is not configured yet.</p>
          </div>
        </TabsContent>

        <TabsContent value="predictions" className="mt-4">
          <div className="glass rounded-xl p-5 text-center py-16 text-muted-foreground">
            <Target className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Global prediction management is handled by the prediction engine.</p>
            <p className="text-xs mt-1">Per-user history is available under Prediction History.</p>
          </div>
        </TabsContent>

        <TabsContent value="settings" className="mt-4">
          <div className="glass rounded-xl p-5 text-center py-16 text-muted-foreground">
            <Settings className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Global system settings are not stored in PostgreSQL yet.</p>
            <p className="text-xs mt-1">Use environment variables and `.env` for deployment configuration.</p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
