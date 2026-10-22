import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { apiPath } from "./base";
import type { RunSelection, RunState } from "./types";

interface RunCtx {
  run: RunState | null;
  /** Bumps every time a run finishes so lists can refetch. */
  versionsKey: number;
  start: (version: string, file: File | null, overwrite: boolean) => Promise<void>;
  /** Run groups and/or individually picked test cases from the library. */
  startFromSelection: (version: string, overwrite: boolean, notes: string, selection: RunSelection) => Promise<void>;
  startRunAndSave: (version: string, file: File, overwrite: boolean, groupName: string) => Promise<void>;
  requestStop: () => void;
  dismiss: () => void;
}

const Ctx = createContext<RunCtx>(null as unknown as RunCtx);
export const useRun = () => useContext(Ctx);

const POLL_MS = 2000;

/**
 * Tracks the active evaluation run so any page can show live progress. Uses server-sent events; if the stream
 * breaks (e.g. a proxy buffers or drops it) it falls back to polling the run list, so progress still updates.
 */
export function RunProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<RunState | null>(null);
  const [versionsKey, setVersionsKey] = useState(0);
  const es = useRef<EventSource | null>(null);
  const poller = useRef<number | null>(null);

  const stop = useCallback(() => {
    es.current?.close();
    es.current = null;
    if (poller.current !== null) window.clearInterval(poller.current);
    poller.current = null;
  }, []);

  const finish = useCallback(() => {
    stop();
    setVersionsKey((k) => k + 1);
  }, [stop]);

  const poll = useCallback((runId: string) => {
    if (poller.current !== null) return;
    poller.current = window.setInterval(() => {
      api.runs().then((runs) => {
        const current = runs.find((r) => r.run_id === runId);
        if (!current) return;
        setRun(current);
        if (current.status !== "running") finish();
      }).catch(() => undefined);
    }, POLL_MS);
  }, [finish]);

  const attach = useCallback((runId: string) => {
    stop();
    const source = new EventSource(apiPath(`runs/${runId}/stream`));
    source.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      setRun({
        run_id: ev.run_id, version: ev.version, status: ev.status, total: ev.total, done: ev.done,
        current_question: ev.current_question, date: ev.date, dataset: ev.dataset, error: ev.error,
      });
      if (ev.type === "done" || ev.type === "error" || ev.type === "stopped") finish();
    };
    source.onerror = () => {
      // a dropped stream: switch to polling instead of letting the browser retry forever
      source.close();
      es.current = null;
      poll(runId);
    };
    es.current = source;
  }, [stop, finish, poll]);

  // Pick up a run that is already going (e.g. after a page refresh).
  useEffect(() => {
    api.runs().then((runs) => {
      const active = runs.find((r) => r.status === "running");
      if (active) {
        setRun(active);
        attach(active.run_id);
      }
    }).catch(() => undefined);
    return stop;
  }, [attach, stop]);

  const start = useCallback(async (version: string, file: File | null, overwrite: boolean) => {
    const started = await api.startRun(version, file, overwrite);
    setRun(started);
    attach(started.run_id);
  }, [attach]);

  const startFromSelection = useCallback(async (version: string, overwrite: boolean, notes: string, selection: RunSelection) => {
    const started = await api.startRunFromSelection(version, overwrite, notes, selection);
    setRun(started);
    attach(started.run_id);
  }, [attach]);

  const startRunAndSave = useCallback(async (version: string, file: File, overwrite: boolean, groupName: string) => {
    const started = await api.startRunAndSave(version, file, overwrite, groupName);
    setRun(started);
    attach(started.run_id);
  }, [attach]);

  const requestStop = useCallback(() => {
    if (!run?.run_id) return;
    api.stopRun(run.run_id).catch(() => undefined);
  }, [run]);

  return (
    <Ctx.Provider value={{ run, versionsKey, start, startFromSelection, startRunAndSave, requestStop, dismiss: () => setRun(null) }}>
      {children}
    </Ctx.Provider>
  );
}
