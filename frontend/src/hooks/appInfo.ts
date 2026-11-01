import { useEffect, useState } from "react";
import { api } from "../api/client";

let known: string | null = null;

/** The dashboard's name, as the server sets it. Empty until the server has answered. */
export function useAppName(): string {
  const [name, setName] = useState(known ?? "");
  useEffect(() => {
    if (known) return;
    api.info()
      .then((info) => { known = info.name; setName(info.name); document.title = info.name; })
      .catch(() => undefined);
  }, []);
  return name;
}
