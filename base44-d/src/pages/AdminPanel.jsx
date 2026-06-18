import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Users, CreditCard, BarChart3, Server, Trophy, Target,
  CheckCircle, AlertCircle, XCircle
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { fetchAdminStats, fetchAdminUsers, fetchAdminHealth } from "@/api/saasApi";

const statusIcon = { operational: CheckCircle, degraded: AlertCircle, down: XCircle };
const statusColor = { operational: "text-green-400", degraded: "text-yellow-400", down: "text-red-400" };

export default function AdminPanel() {
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
        fetchAdminUsers({ limit: 100 }),
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

  const statCards = [
    { label: "Total Users", value: stats ? String(stats.total_users) : "—", icon: Users, color: "text-primary", bg: "bg-primary/10", change: "From PostgreSQL" },
    { label: "Paid Subscribers", value: stats ? String(stats.paid_subscribers) : "—", icon: CreditCard, color: "text-green-400", bg: "bg-green-500/10", change: "Non-free plans" },
    { label: "Predictions Today", value: stats ? String(stats.predictions_today) : "0", icon: Target, color: "text-accent", bg: "bg-yellow-500/10", change: "Tracking coming soon" },
    { label: "System Status", value: services.some((s) => s.status !== "operational") ? "Degraded" : "Healthy", icon: Server, color: "text-purple-400", bg: "bg-purple-500/10", change: "Live health check" },
  ];

  const filteredUsers = users.filter((u) =>
    `${u.full_name} ${u.email}`.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold">Admin Panel</h1>
        <p className="text-sm text-muted-foreground mt-1">Platform overview and management.</p>
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }} className="glass rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}><s.icon className={`w-4 h-4 ${s.color}`} /></div>
            </div>
            <div className="text-2xl font-display font-bold">{s.value}</div>
            <div className="text-xs text-muted-foreground mt-1">{s.change}</div>
          </motion.div>
        ))}
      </div>

      <Tabs defaultValue="users">
        <TabsList className="glass border-white/10 rounded-xl p-1">
          <TabsTrigger value="users" className="rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">Users</TabsTrigger>
          <TabsTrigger value="system" className="rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">System Health</TabsTrigger>
          <TabsTrigger value="leagues" className="rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">Leagues</TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="mt-4">
          <div className="glass rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold">Users</h2>
              <Input placeholder="Search users..." value={search} onChange={(e) => setSearch(e.target.value)} className="w-64 bg-white/5 border-white/10 rounded-lg" />
            </div>
            {filteredUsers.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground text-sm">No users found.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground text-xs">
                      <th className="pb-3 font-medium">Name</th>
                      <th className="pb-3 font-medium">Email</th>
                      <th className="pb-3 font-medium">Role</th>
                      <th className="pb-3 font-medium">Plan</th>
                      <th className="pb-3 font-medium">Joined</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {filteredUsers.map((u) => (
                      <tr key={u.id} className="hover:bg-white/5">
                        <td className="py-3 font-medium">{u.full_name}</td>
                        <td className="py-3 text-muted-foreground">{u.email}</td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${u.role === "admin" ? "bg-accent/10 text-accent" : "bg-white/5 text-muted-foreground"}`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${
                            u.plan === "elite" ? "bg-yellow-500/10 text-accent" :
                            u.plan === "pro" ? "bg-primary/10 text-primary" :
                            "bg-white/5 text-muted-foreground"
                          }`}>{u.plan}</span>
                        </td>
                        <td className="py-3 text-muted-foreground">{u.created_date ? new Date(u.created_date).toLocaleDateString() : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="system" className="mt-4">
          <div className="glass rounded-xl p-5">
            <h2 className="font-display font-semibold mb-4">System Services</h2>
            <div className="space-y-3">
              {services.map((svc, i) => {
                const Icon = statusIcon[svc.status] || AlertCircle;
                return (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <div className="flex items-center gap-3">
                      <Icon className={`w-5 h-5 ${statusColor[svc.status] || "text-muted-foreground"}`} />
                      <span className="font-medium text-sm">{svc.name}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-muted-foreground">Uptime: {svc.uptime}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                        svc.status === "operational" ? "bg-green-500/10 text-green-400" :
                        svc.status === "degraded" ? "bg-yellow-500/10 text-yellow-400" :
                        "bg-red-500/10 text-red-400"
                      }`}>{svc.status}</span>
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
            <p className="text-sm">League management is not configured yet.</p>
            <p className="text-xs mt-1">Competitions are managed via the prediction engine registry.</p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
