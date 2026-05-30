
import { useState, useEffect, useCallback } from "react";
import { apiGet, apiPut } from "@/services/api-client";
import type { SettingsData } from "@/types/api-types";

interface UseSettingsReturn {
  settings: SettingsData | null;
  loading: boolean;
  update: (patch: Partial<SettingsData>) => Promise<SettingsData>;
}

export function useSettings(): UseSettingsReturn {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadSettings() {
      setLoading(true);
      try {
        const resp = await apiGet<SettingsData>("/settings");
        if (!cancelled) {
          setSettings(resp);
        }
      } catch {
        // Load failure — settings remain null, UI shows error state
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadSettings();

    return () => {
      cancelled = true;
    };
  }, []);

  const update = useCallback(
    async (patch: Partial<SettingsData>): Promise<SettingsData> => {
      const resp = await apiPut<SettingsData>("/settings", patch);
      setSettings(resp);
      return resp;
    },
    [],
  );

  return { settings, loading, update };
}