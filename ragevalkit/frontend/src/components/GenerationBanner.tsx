import { useEffect, useState } from "react";
import { api } from "../api/client";
import { plural } from "../lib/format";
import type { GenSummary } from "../api/types";

function timeLeft(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.parse(iso) - Date.now()) / 60000));
  return minutes >= 120 ? `${Math.round(minutes / 60)} hours` : minutes >= 60 ? "an hour" : `${minutes} minutes`;
}

/**
 * Generated test cases that are still waiting: being written, or written but not yet added to the library.
 * They live on the server, so this finds them again after a closed tab or a dropped connection.
 */
export function GenerationBanner({ refreshKey, onOpen }: { refreshKey: number; onOpen: (batchId: string) => void }) {
  const [batches, setBatches] = useState<GenSummary[]>([]);
  const [tick, setTick] = useState(0);
  const [confirm, setConfirm] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    api.generateList().then((b) => { if (!stale) setBatches(b); }).catch(() => undefined);
    return () => { stale = true; };
  }, [refreshKey, tick]);

  // keep the progress current while something is being written
  useEffect(() => {
    if (!batches.some((b) => b.status === "running")) return;
    const t = window.setTimeout(() => setTick((n) => n + 1), 3000);
    return () => window.clearTimeout(t);
  }, [batches]);

  if (batches.length === 0) return null;
  return (
    <div className="mb-4 space-y-2">
      {batches.map((b) => (
        <div key={b.batch_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded border border-brand bg-brand-soft px-4 py-3 text-sm" role="status">
          {b.status === "running" ? (
            <span><b>Writing test cases…</b> {b.total_tasks ? `${b.done_tasks} of ${b.total_tasks} done` : "reading your documents"}</span>
          ) : b.status === "failed" ? (
            <span className="text-bad"><b>Generating test cases failed.</b> {b.error}</span>
          ) : (
            <span>
              <b>{plural(b.case_count, "generated test case")}</b> {b.case_count === 1 ? "is" : "are"} waiting for your review
              <span className="text-muted"> — deleted in {timeLeft(b.expires_at)} if not added</span>
            </span>
          )}
          <span className="ml-auto flex items-center gap-4 text-xs">
            <button onClick={() => onOpen(b.batch_id)} className="font-semibold text-brand hover:underline">
              {b.status === "running" ? "View progress" : b.status === "failed" ? "See why" : "Review and add"}
            </button>
            {b.status !== "running" && (confirm === b.batch_id ? (
              <span className="flex items-center gap-2">
                <span className="text-bad">Delete them?</span>
                <button onClick={() => api.generateDiscard(b.batch_id).then(() => { setConfirm(null); setTick((n) => n + 1); }).catch(() => setConfirm(null))}
                  className="text-bad hover:underline">Yes</button>
                <button onClick={() => setConfirm(null)} className="text-muted hover:underline">No</button>
              </span>
            ) : (
              <button onClick={() => setConfirm(b.batch_id)} className="text-muted hover:text-bad">Discard</button>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}
