import { useState, useCallback } from "react";
import type { SkillItem } from "@/types/api-types";

export interface SkillPickerState {
  open: boolean;
  query: string;
  highlightIndex: number;
  filteredSkills: SkillItem[];
}

/**
 * Extract the slash query starting at or before cursorPos.
 * Returns the "/xx" token if found at a word boundary, otherwise null.
 * Uses capture groups instead of lookbehind for Safari compatibility.
 */
function extractSlashQuery(value: string, cursorPos: number): string | null {
  const textBefore = value.slice(0, cursorPos);
  const match = /(^|\s)(\/\S*)$/.exec(textBefore);
  return match ? match[2] : null;
}

function filterSkills(skills: SkillItem[], query: string): SkillItem[] {
  if (!query) return skills;
  const q = query.toLowerCase();
  return skills.filter(
    (s) =>
      s.name.toLowerCase().includes(q) ||
      (s.header_description ?? "").toLowerCase().includes(q),
  );
}

export function useSkillPicker(skills: SkillItem[]) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(0);

  const filteredSkills = filterSkills(skills, query);

  const onInputChange = useCallback(
    (value: string, cursorPos: number, isComposing: boolean) => {
      if (isComposing) return;
      const token = extractSlashQuery(value, cursorPos);
      if (token === null) {
        setOpen(false);
        setQuery("");
        return;
      }
      const q = token.slice(1); // strip leading "/"
      setOpen(true);
      setQuery(q);
      setHighlightIndex(0);
    },
    [],
  );

  const moveUp = useCallback(() => {
    setHighlightIndex((i) => Math.max(i - 1, 0));
  }, []);

  const moveDown = useCallback(() => {
    setHighlightIndex((i) => Math.min(i + 1, Math.max(filteredSkills.length - 1, 0)));
  }, [filteredSkills.length]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setHighlightIndex(0);
  }, []);

  return {
    open,
    query,
    highlightIndex,
    filteredSkills,
    onInputChange,
    moveUp,
    moveDown,
    close,
    setHighlightIndex,
  };
}
