import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { motion } from "framer-motion";
import {
  Users, CreditCard, BarChart3, Server, Trophy, Target, Shield, Settings,
  CheckCircle, AlertCircle, XCircle, Globe, Edit, Trash2, UserCheck
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";

const ROLES = ["user", "admin", "super_admin"];
const PLANS = ["free", "pro", "elite", "unlimited"];

const mockUsers = [
  { id: "1", full_name: "Pedram Kamangar", email: "pedram@example.com", role: "super_admin", plan: "unlimited", created_date: "2026-01-01" },
  { id: "2", full_name: "Marcus Williams", email: "marcus@example.com", role: "admin", plan: "elite", created_date: "2026-01-15" },
  { id: "3", full_name: "Sarah Kim", email: "sarah@example.com", role: "user", plan: "pro", created_date: "2026-02-20" },
  { id: "4", full_name: "Elena Martin", email: "elena@example.com", role: "user", plan: "free", created_date: "2026-04-10" },
  { id: "5", full_name: "James Taylor", email: "james@example.com", role: "user", plan: "elite", created_date: "2026-05-01" },
];

const systemServices = [
  { name: "Prediction Engine", status: "operational", uptime: "99.97%" },
  { name: "Match Data API", status: "operational", uptime: "99.95%" },
  { name: "User Auth Service", status: "operational", uptime: "99.99%" },
  { name: "Notification Service", status: "degraded", uptime: "98.50%" },
  { name: "Analytics Pipeline", status: "operational", uptime: "99.90%" },
  { name: "Payment Gateway", status: "operational", uptime: "99.98%" },
];

const statusIcon = { operational: CheckCircle, degraded: AlertCircle, down: XCircle };
const statusColor = { operational: "text-green-400", degraded: "text-yellow-400", down: "text-red-400" };
const roleColor = { super_admin: "bg-red-500/10 text-red-400", admin: "bg-accent/10 text-accent", user: "bg-white/5 text-muted-foreground" };
const planColor = { unlimited: "bg-red-500/10 text-red-400", elite: "bg-yellow-500/10 text-accent", pro: "bg-primary/10 text-primary", free: "bg-white/5 text-muted-foreground" };

export default function SuperAdminPanel() {
  const { toast } = useToast();
  const [users, setUsers] = useState(mockUsers);
  const [search, setSearch] = useState("");
  const [editingUser, setEditingUser] = useState(null);

  useEffect(() => {
    base44.entities.User.list("-created_date", 100).then(data => {
      if (data.length > 0) setUsers(data.map(u => ({ ...u, plan: u.plan || "free" })));
    }).catch(() => {});
  }, []);

  const handleRoleChange = async (userId, newRole) => {
    try {
      await base44.entities.User.update(userId, { role: newRole });
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, role: newRole } : u));
      toast({ title: "Role updated", description: `User role set to ${newRole}` });
    } catch {
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, role: newRole } : u));
      toast({ title: "Updated locally" });
    }
  };

  const stats = [
    { label: "Total Users", value: users.length.toLocaleString(), icon: Users, color: "text-primary", bg: "bg-primary/10" },
    { label: "Paid Subscribers", value: users.filter(u => u.plan !== "free").length, icon: CreditCard, color: "text-green-400", bg: "bg-green-500/10" },
    { label: "Admins", value: users.filter(u => u.role === "admin" || u.role === "super_admin").length, icon: Shield, color: "text-accent", bg: "bg-yellow-500/10" },
    { label: "System Uptime", value: "99.95%", icon: Server, color: "text-purple-400", bg: "bg-purple-500/10" },
  ];

  const filtered = users.filter(u => `${u.full_name} ${u.email}`.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
          <Shield className="w-5 h-5 text-red-400" />
        </div>
        <div>
          <h1 className="text-2xl font-display font-bold">Super Admin Panel</h1>
          <p className="text-xs text-red-400 font-medium">Full system access • Pedram Kamangar</p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s, i) => (
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
          {["users", "roles", "system", "leagues", "predictions", "settings"].map(tab => (
            <TabsTrigger key={tab} value={tab} className="rounded-lg capitalize data-[state=active]:bg-primary data-[state=active]:text-primary-foreground text-xs">
              {tab}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="users" className="mt-4">
          <div className="glass rounded-xl p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
              <h2 className="font-display font-semibold">All Users</h2>
              <Input placeholder="Search users..." value={search} onChange={e => setSearch(e.target.value)} className="w-full sm:w-64 bg-white/5 border-white/10 rounded-lg" />
            </div>
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
                  {filtered.map((u, i) => (
                    <tr key={u.id || i} className="hover:bg-white/5">
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
          </div>
        </TabsContent>

        <TabsContent value="roles" className="mt-4">
          <div className="glass rounded-xl p-5 space-y-3">
            <h2 className="font-display font-semibold mb-4">Manage User Roles & Plans</h2>
            {filtered.map((u, i) => (
              <div key={u.id || i} className="flex flex-wrap items-center gap-3 p-3 rounded-lg bg-white/5">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{u.full_name}</div>
                  <div className="text-xs text-muted-foreground">{u.email}</div>
                </div>
                <Select value={u.role} onValueChange={v => handleRoleChange(u.id, v)}>
                  <SelectTrigger className="w-32 bg-white/5 border-white/10 rounded-lg text-xs h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-white/10">
                    {ROLES.map(r => <SelectItem key={r} value={r} className="text-xs">{r}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={u.plan} onValueChange={v => setUsers(prev => prev.map(usr => usr.id === u.id ? { ...usr, plan: v } : usr))}>
                  <SelectTrigger className="w-28 bg-white/5 border-white/10 rounded-lg text-xs h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-card border-white/10">
                    {PLANS.map(p => <SelectItem key={p} value={p} className="text-xs">{p}</SelectItem>)}
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
              {systemServices.map((svc, i) => {
                const Icon = statusIcon[svc.status];
                return (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <div className="flex items-center gap-3">
                      <Icon className={`w-4 h-4 ${statusColor[svc.status]}`} />
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
          <div className="glass rounded-xl p-5">
            <h2 className="font-display font-semibold mb-4">League Management</h2>
            <div className="space-y-3">
              {["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "Eredivisie", "Liga Portugal", "Turkish Süper Lig", "Serbian SuperLiga", "HNL Croatia"].map((l, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                  <div className="flex items-center gap-3"><Trophy className="w-4 h-4 text-primary" /><span className="text-sm font-medium">{l}</span></div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full text-xs bg-green-500/10 text-green-400">Active</span>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"><Edit className="w-3.5 h-3.5" /></Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="predictions" className="mt-4">
          <div className="glass rounded-xl p-5">
            <h2 className="font-display font-semibold mb-4">Prediction Management</h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <div className="grid grid-cols-3 gap-3">
                {[["Total Predictions", "48,230"], ["Pending", "1,284"], ["Accuracy Rate", "72.4%"]].map(([label, val]) => (
                  <div key={label} className="p-4 rounded-xl bg-white/5 text-center">
                    <div className="text-xl font-display font-bold text-foreground">{val}</div>
                    <div className="text-xs mt-1">{label}</div>
                  </div>
                ))}
              </div>
              <p className="text-xs pt-2">Full prediction management including bulk updates, result verification, and confidence recalibration is available via the API settings panel once backend is connected.</p>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="settings" className="mt-4">
          <div className="glass rounded-xl p-5 space-y-4">
            <h2 className="font-display font-semibold">Global System Settings</h2>
            {[
              { label: "App Name", value: "WorldCup Predictor Pro" },
              { label: "Support Email", value: "support@wcppredictor.com" },
              { label: "Max Free Predictions/Day", value: "1" },
              { label: "Default Language", value: "en" },
            ].map(({ label, value }) => (
              <div key={label}>
                <label className="text-xs text-muted-foreground mb-1.5 block">{label}</label>
                <Input defaultValue={value} className="bg-white/5 border-white/10 rounded-lg text-sm" />
              </div>
            ))}
            <Button className="rounded-xl"><Settings className="w-4 h-4 mr-2" /> Save Global Settings</Button>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}