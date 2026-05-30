import { useEffect, useState } from "react";
import { apiGet } from "@/services/api-client";
import type { SkillItem } from "@/types/api-types";

export function useSkillList() {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<{ skills: SkillItem[] }>("/skills?include_content=false")
      .then((r) => setSkills(r.skills))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return { skills, loading };
}
