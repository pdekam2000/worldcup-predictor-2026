import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { fetchNotifications } from "@/api/saasApi";
import { fetchAssistantNotifications } from "@/api/assistantApi";

export default function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchNotifications().catch(() => ({ notifications: [], unread_count: 0 })),
      fetchAssistantNotifications().catch(() => ({ notifications: [], unread_count: 0 })),
    ])
      .then(([legacy, assistant]) => {
        if (cancelled) return;
        const legacyUnread =
          Number(legacy.unread_count) ||
          (legacy.notifications || []).filter((n) => !n.is_read).length;
        const assistantUnread =
          Number(assistant.unread_count) ||
          (assistant.notifications || []).filter((n) => !n.is_read).length;
        setUnreadCount(legacyUnread + assistantUnread);
      })
      .catch(() => {
        if (!cancelled) setUnreadCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Link
      to="/notifications"
      className="relative p-2 rounded-lg hover:bg-white/5 transition-colors"
      aria-label={unreadCount > 0 ? `${unreadCount} unread notifications` : "Notifications"}
    >
      <Bell className="w-5 h-5 text-muted-foreground hover:text-foreground transition-colors" />
      {unreadCount > 0 && (
        <span className="absolute top-1 right-1 min-w-[18px] h-[18px] px-1 flex items-center justify-center bg-primary text-primary-foreground text-[10px] font-bold rounded-full">
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
    </Link>
  );
}
