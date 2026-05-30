
import { useState, useCallback, useRef } from "react";
import { apiGet } from "@/services/api-client";
import type { SearchResultItem } from "@/types/api-types";

interface SearchResponse {
  results: SearchResultItem[];
}

interface UseSearchReturn {
  results: SearchResultItem[];
  loading: boolean;
  search: (query: string) => Promise<void>;
}

export function useSearch(): UseSearchReturn {
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const currentQueryRef = useRef<string>("");

  const search = useCallback(async (query: string) => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    currentQueryRef.current = query;
    setLoading(true);

    try {
      const resp = await apiGet<SearchResponse>(
        `/search?q=${encodeURIComponent(query)}`,
      );
      // Only update if this query is still the latest one
      if (currentQueryRef.current === query) {
        setResults(resp.results);
      }
    } catch {
      // Search failure — keep previous results, UI can show error indicator
      if (currentQueryRef.current === query) {
        setResults([]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  return { results, loading, search };
}