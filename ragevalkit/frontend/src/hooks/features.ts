import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Features } from "../api/types";

let known: Features | null = null;

/** What the server has switched on. `null` until it has answered, so a link is not shown and then taken away. */
export function useFeatures(): Features | null {
  const [features, setFeatures] = useState<Features | null>(known);
  useEffect(() => {
    if (known) return;
    api.features()
      .then((f) => { known = f; setFeatures(f); })
      .catch(() => setFeatures({ guide: false }));
  }, []);
  return features;
}
