import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bell,
  Eye,
  Plus,
  RefreshCw,
  Star,
  Trash2,
  TrendingUp,
} from "lucide-react";
import {
  addWatchlistItem,
  fetchAssistantNotifications,
  fetchWatchlist,
  removeWatchlistItem,
} from "@/api/assistantApi";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { SectionHeader, TerminalCard } from "@/components/terminal";

const WATCH_TYPES = [
  { id: "competition", label: "Competition" },
  { id: "team", label: "Team" },
  { id: "player", label: "Player" },
  { id: "fixture", label: "Fixture" },
  { id: "market", label: "Market" },
];

export default function WatchlistPage() {
  const { isAuthenticated } = useAuth();
  const [items, setItems] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [itemType, setItemType] = useState("fixture");
  const [itemId, setItemId] = useState("");
  const [itemName, setItemName] = useState("");

  const load = useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [wl, notif] = await Promise.all([
        fetchWatchlist(),
        fetchAssistantNotifications().catch(() => ({ notifications: [] })),
      ]);
      setItems(wl.watchlist || []);
      setAlerts((notif.notifications || []).slice(0, 8));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load watchlist");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    load();
  }, [load]);

  const handleAdd = async () => {
    if (!itemId.trim()) return;
    try {
      await addWatchlistItem({
        item_type: itemType,
        item_id: itemId.trim(),
        item_name: itemName.trim() || undefined,
      });
      setItemId("");
      setItemName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add item");
    }
  };

  const handleRemove = async (id) => {
    try {
      await removeWatchlistItem(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove item");
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="max-w-2xl mx-auto text-center py-16">
        <Eye className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
        <p className="text-muted-foreground">Log in to manage your watchlist.</p>
        <Link to="/login" className="text-primary hover:underline mt-2 inline-block">Sign in</Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  const fixtureItems = items.filter((i) => i.item_type === "fixture");

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <SectionHeader
        title="My Watchlist"
        subtitle="Follow competitions, teams, players, fixtures, and markets. Alerts only fire for watched items."
        icon={Eye}
      />

      {error && (
        <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>
      )}

      <TerminalCard title="Add to watchlist">
        <div className="grid gap-3 sm:grid-cols-4">
          <select
            value={itemType}
            onChange={(e) => setItemType(e.target.value)}
            className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm"
          >
            {WATCH_TYPES.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
          <input
            placeholder="ID (fixture id, team slug…)"
            value={itemId}
            onChange={(e) => setItemId(e.target.value)}
            className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm sm:col-span-2"
          />
          <input
            placeholder="Display name (optional)"
            value={itemName}
            onChange={(e) => setItemName(e.target.value)}
            className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <Button className="mt-3" size="sm" onClick={handleAdd}>
          <Plus className="w-4 h-4 mr-1" /> Add
        </Button>
      </TerminalCard>

      <div className="grid gap-4 md:grid-cols-2">
        <TerminalCard title={`Watched items (${items.length})`}>
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No watchlist items yet.</p>
          ) : (
            <ul className="space-y-2">
              {items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-2 text-sm glass rounded-lg px-3 py-2">
                  <div>
                    <span className="text-xs uppercase text-muted-foreground">{item.item_type}</span>
                    <p className="font-medium">{item.item_name || item.item_id}</p>
                  </div>
                  <button type="button" onClick={() => handleRemove(item.id)} className="text-red-400 hover:text-red-300">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </TerminalCard>

        <TerminalCard title="Upcoming alerts">
          {alerts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recent alerts for your watchlist.</p>
          ) : (
            <ul className="space-y-2">
              {alerts.map((a) => (
                <li key={a.id} className="text-sm glass rounded-lg px-3 py-2">
                  <p className="font-medium">{a.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{a.message}</p>
                </li>
              ))}
            </ul>
          )}
          <Link to="/notifications" className="text-xs text-primary hover:underline mt-2 inline-block">
            View all notifications
          </Link>
        </TerminalCard>
      </div>

      <TerminalCard title="Today's watched fixtures">
        {fixtureItems.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Add fixture IDs to track quality evolution and prediction updates.
          </p>
        ) : (
          <ul className="space-y-2">
            {fixtureItems.map((f) => (
              <li key={f.id}>
                <Link
                  to={`/matches/${f.item_id}`}
                  className="flex items-center gap-2 text-sm hover:text-primary"
                >
                  <Star className="w-4 h-4 text-yellow-500" />
                  {f.item_name || `Fixture ${f.item_id}`}
                  <TrendingUp className="w-3 h-3 text-muted-foreground ml-auto" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </TerminalCard>

      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
        <Link to="/daily-briefing">
          <Button variant="outline" size="sm">
            <Bell className="w-4 h-4 mr-1" /> Daily Briefing
          </Button>
        </Link>
      </div>
    </div>
  );
}
