import { create } from "zustand";
import type { SessionItem } from "@/types/api-types";

interface SessionState {
  sessions: SessionItem[];
  activeSessionId: string | null;
  loading: boolean;
  setSessions: (sessions: SessionItem[]) => void;
  setActiveSession: (id: string | null) => void;
  setLoading: (v: boolean) => void;
  addSession: (session: SessionItem) => void;
  removeSession: (id: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  activeSessionId: null,
  loading: false,
  setSessions: (sessions) => set({ sessions: [...sessions].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()) }),
  setActiveSession: (id) => set({ activeSessionId: id }),
  setLoading: (v) => set({ loading: v }),
  addSession: (session) => set((s) => ({ sessions: [session, ...s.sessions] })),
  removeSession: (id) => set((s) => ({ sessions: s.sessions.filter((x) => x.session_id !== id) })),
}));