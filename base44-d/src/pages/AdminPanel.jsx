import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { motion } from "framer-motion";
import {
  Users, CreditCard, BarChart3, Activity, Server, Globe, Trophy, Target,
  ChevronRight, CheckCircle, AlertCircle, XCircle
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const mockUsers = [
  { id: "1", full_name: "Marcus Williams", email: "marcus@example.com", role: "admin", plan: "elite", created_date: "2026-01-15" },
  { id: "2", full_name: "Sarah Kim", email: "sarah@example.com", role: "user", plan: "pro", created_date: "2026-02-20" },
  { id: "3", full_name: "David Rodriguez", email: "david@example.com", role: "user", plan: "pro", created_date: "2026-03-05" },
  { id: "4", full_name: "Elena Martin", email: "elena@example.com", role: "user", plan: "free", created_date: "2026-04-10" },
  { id: "5", full_name: "James Taylor", email: "james@example.com", role: "user", plan: "elite", created_date: "2026-05-01" },
];

const systemServices = [
  { name: "Prediction Engine", status: "operational", uptime: "99.97%" },
  { name: "Match Data API", status: "operational", uptime: "99.95%" },
  { name: "User Auth Service", status: "operational", uptime: "99.99%" },
  { name: "Notification Service", status: "degraded", uptime: "98.50%" },
  { name: "Analytics Pipeline", status: "operational", uptime: "99.90%" },
];

const statusIcon = { operational: CheckCircle, degraded: AlertCircle, down: XCircle };
const statusColor = { operational: "text-green-400", degraded: "text-yellow-400", down: "text-red-400" };

export default function AdminPanel() {
  const [users, setUsers] = useState(mockUsers);
  const [search, setSearch] = useState("");

  useEffect(() => {
    base44.entities.User.list("-created_date", 50).then(data => {
      if (data.length > 0) setUsers(data.map(u => ({ ...u, plan: "pro" })));
    }).catch(() => {});
  }, []);

  const stats = [
    { label: "Total Users", value: "12,750", icon: Users, color: "text-primary", bg: "bg-primary/10", change: "+248 this week" },
    { label: "Paid Subscribers", value: "4,320", icon: CreditCard, color: "text-green-400", bg: "bg-green-500/10", change: "+86 this week" },
    { label: "Predictions Today", value: "1,284", icon: Target, color: "text-accent", bg: "bg-yellow-500/10", change: "+12% vs avg" },
    { label: "System Uptime", value: "99.95%", icon: Server, color: "text-purple-400", bg: "bg-purple-500/10", change: "Last 30 days" },
  ];

  const filteredUsers = users.filter(u =>
    `${u.full_name} ${u.email}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold">Admin Panel</h1>
        <p className="text-sm text-muted-foreground mt-1">Platform overview and management.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s, i) => (
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
              <Input placeholder="Search users..." value={search} onChange={e => setSearch(e.target.value)} className="w-64 bg-white/5 border-white/10 rounded-lg" />
            </div>
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
                  {filteredUsers.map((u, i) => (
                    <tr key={u.id || i} className="hover:bg-white/5">
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
                      <td className="py-3 text-muted-foreground">{new Date(u.created_date).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="system" className="mt-4">
          <div className="glass rounded-xl p-5">
            <h2 className="font-display font-semibold mb-4">System Services</h2>
            <div className="space-y-3">
              {systemServices.map((svc, i) => {
                const Icon = statusIcon[svc.status];
                return (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <div className="flex items-center gap-3">
                      <Icon className={`w-5 h-5 ${statusColor[svc.status]}`} />
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
          <div className="glass rounded-xl p-5">
            <h2 className="font-display font-semibold mb-4">Managed Leagues</h2>
            <div className="space-y-3">
              {["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "Eredivisie", "Liga Portugal"].map((l, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                  <div className="flex items-center gap-3">
                    <Trophy className="w-5 h-5 text-primary" />
                    <span className="font-medium text-sm">{l}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400">Active</span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}