
import { useEffect, useCallback } from "react";
import { useSessionStore } from "@/store/session-store";
import { apiGet, apiPost, apiDelete } from "@/services/api-client";
import type { SessionItem } from "@/types/api-types";

interface SessionsResponse {
  sessions: SessionItem[];
}

// Matches the backend CreateSessionResponse schema (flat, not nested)
interface CreateSessionResponse {
  session_id: string;
  title?: string;
  model: string;
  created_at: string;
}

interface UseSessionsReturn {
  sessions: SessionItem[];
  activeSessionId: string | null;
  loading: boolean;
  create: (title: string) => Promise<SessionItem>;
  delete: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useSessions(): UseSessionsReturn {
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const loading = useSessionStore((s) => s.loading);

  const setSessions = useSessionStore((s) => s.setSessions);
  const setLoading = useSessionStore((s) => s.setLoading);
  const addSession = useSessionStore((s) => s.addSession);
  const removeSession = useSessionStore((s) => s.removeSession);

  useEffect(() => {
    let cancelled = false;

    async function loadSessions() {
      setLoading(true);
      try {
        const resp = await apiGet<SessionsResponse>("/sessions?page_size=100");
        if (!cancelled) {
          setSessions(resp.sessions);
        }
      } catch {
        // Load failure — store remains empty, UI shows empty/error state
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadSessions();

    return () => {
      cancelled = true;
    };
  }, [setSessions, setLoading]);

  const create = useCallback(
    async (title: string): Promise<SessionItem> => {
      const resp = await apiPost<CreateSessionResponse>("/sessions", { title });
      const session: SessionItem = {
        session_id: resp.session_id,
        title: resp.title,
        model: resp.model,
        created_at: resp.created_at,
        message_count: 0,
        is_active: false,
      };
      addSession(session);
      return session;
    },
    [addSession],
  );

  const deleteSession = useCallback(
    async (id: string): Promise<void> => {
      await apiDelete(`/sessions/${id}`);
      removeSession(id);
    },
    [removeSession],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiGet<SessionsResponse>("/sessions?page_size=100");
      setSessions(resp.sessions);
    } catch {
      // Refresh failure — keep existing sessions
    } finally {
      setLoading(false);
    }
  }, [setSessions, setLoading]);

  return {
    sessions,
    activeSessionId,
    loading,
    create,
    delete: deleteSession,
    refresh,
  };
}