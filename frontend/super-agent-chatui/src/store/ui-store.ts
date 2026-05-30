import { create } from "zustand";

interface UIState {
  sidebarOpen: boolean;
  inputDraft: string;
  autoScroll: boolean;
  setSidebarOpen: (v: boolean) => void;
  setInputDraft: (v: string) => void;
  setAutoScroll: (v: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  inputDraft: "",
  autoScroll: true,
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  setInputDraft: (v) => set({ inputDraft: v }),
  setAutoScroll: (v) => set({ autoScroll: v }),
}));