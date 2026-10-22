import { useEffect, useState } from "react";
import { api } from "./api";
import { useRun } from "./RunContext";
import { compareVersions } from "./lib";
import type { VersionDetail, VersionSummary } from "./types";

/** All finished versions, oldest first. Refetches whenever a run finishes. */
export function useVersions() {
  const { versionsKey } = useRun();
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.versions()
      .then((v) => { setVersions([...v].sort((a, b) => compareVersions(a.version, b.version))); setError(""); })
      .catch((e) => setError(e.message));
  }, [versionsKey]);
  return { versions, error };
}

export function useVersionDetail(version: string) {
  const [data, setData] = useState<VersionDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setData(null);
    api.version(version).then(setData).catch((e) => setError(e.message));
  }, [version]);
  return { data, error };
}
