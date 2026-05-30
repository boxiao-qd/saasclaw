import { create } from "zustand";
import type { SSEEventType, SSEEventEnvelope } from "@/types/sse-events";

interface SSEState {
  connected: boolean;
  reconnecting: boolean;
  lastEvent: SSEEventEnvelope | null;
  errorCount: number;
  setConnected: (v: boolean) => void;
  setReconnecting: (v: boolean) => void;
  pushEvent: (event: SSEEventEnvelope) => void;
  incrementError: () => void;
}

export const useSSEStore = create<SSEState>((set) => ({
  connected: false,
  reconnecting: false,
  lastEvent: null,
  errorCount: 0,
  setConnected: (v) => set({ connected: v }),
  setReconnecting: (v) => set({ reconnecting: v }),
  pushEvent: (event) => set({ lastEvent: event }),
  incrementError: () => set((s) => ({ errorCount: s.errorCount + 1 })),
}));