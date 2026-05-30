
import { useRef, useCallback } from "react";
import { useUIStore } from "@/store/ui-store";

interface UseAutoScrollOptions {
  onNearTop?: () => void;
  scrollRef?: React.RefObject<HTMLDivElement | null>;
}

interface UseAutoScrollReturn {
  autoScroll: boolean;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  handleScroll: () => void;
  scrollToBottom: () => void;
}

export function useAutoScroll(options?: UseAutoScrollOptions): UseAutoScrollReturn {
  const internalScrollRef = useRef<HTMLDivElement | null>(null);
  // Use the caller-supplied ref when available so handleScroll and scrollToBottom
  // read from the same DOM element that the div is actually attached to.
  const scrollRef = options?.scrollRef ?? internalScrollRef;
  const autoScroll = useUIStore((s) => s.autoScroll);
  const setAutoScroll = useUIStore((s) => s.setAutoScroll);
  // Keep latest onNearTop in a ref so handleScroll never needs to be recreated
  const onNearTopRef = useRef(options?.onNearTop);
  onNearTopRef.current = options?.onNearTop;

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;

    // Threshold to account for sub-pixel rounding and incomplete layout
    const threshold = 40;
    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;

    if (distanceFromBottom > threshold) {
      // User scrolled up away from bottom — disable auto-scroll
      if (autoScroll) {
        setAutoScroll(false);
      }
    } else {
      // User is at or near bottom — re-enable auto-scroll
      if (!autoScroll) {
        setAutoScroll(true);
      }
    }

    // Trigger load-more when near top
    if (el.scrollTop < 80) {
      onNearTopRef.current?.();
    }
  }, [scrollRef, autoScroll, setAutoScroll]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [scrollRef]);

  return { autoScroll, scrollRef, handleScroll, scrollToBottom };
}