import { create } from "zustand";
import { apiGet, apiPost, apiDelete } from "@/services/api-client";

export interface NotificationItem {
  id: string;
  title: string;
  content: string;
  source: string;
  cron_job_id?: string;
  is_read: number;
  created_at: string;
}

interface NotificationState {
  notifications: NotificationItem[];
  unreadCount: number;
  loading: boolean;
  selectedId: string | null;
  setUnreadCount: (count: number) => void;
  incrementUnread: () => void;
  fetchUnreadCount: () => Promise<void>;
  fetchNotifications: () => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  deleteNotification: (id: string) => Promise<void>;
  select: (id: string | null) => void;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  loading: false,
  selectedId: null,

  setUnreadCount: (count) => set({ unreadCount: count }),
  incrementUnread: () => set({ unreadCount: get().unreadCount + 1 }),

  fetchUnreadCount: async () => {
    try {
      const result = await apiGet<{ unread_count: number }>("/notifications/unread-count");
      set({ unreadCount: result.unread_count });
    } catch { /* ignore */ }
  },

  fetchNotifications: async () => {
    set({ loading: true });
    try {
      const result = await apiGet<{ notifications: NotificationItem[]; unread_count: number }>("/notifications");
      set({ notifications: result.notifications, unreadCount: result.unread_count, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  markRead: async (id) => {
    try {
      await apiPost(`/notifications/${id}/read`, {});
      set((state) => ({
        notifications: state.notifications.map((n) => n.id === id ? { ...n, is_read: 1 } : n),
        unreadCount: Math.max(0, state.unreadCount - 1),
      }));
    } catch { /* ignore */ }
  },

  markAllRead: async () => {
    try {
      await apiPost("/notifications/mark-all-read", {});
      set((state) => ({
        notifications: state.notifications.map((n) => ({ ...n, is_read: 1 })),
        unreadCount: 0,
      }));
    } catch { /* ignore */ }
  },

  deleteNotification: async (id) => {
    try {
      await apiDelete(`/notifications/${id}`);
      set((state) => ({
        notifications: state.notifications.filter((n) => n.id !== id),
        unreadCount: state.notifications.find((n) => n.id === id && n.is_read === 0)
          ? state.unreadCount - 1 : state.unreadCount,
      }));
    } catch { /* ignore */ }
  },

  select: (id) => set({ selectedId: id }),
}));