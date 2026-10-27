import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Issue, RunState } from "../api/types";
import { IssueList } from "./IssueList";

/** Problems met so far by the run in progress; the list opens on request and refreshes as more turn up. */
export function RunProblems({ run }: { run: RunState }) {
  const [open, setOpen] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const count = run.issue_count ?? 0;

  useEffect(() => {
    if (!open || count === 0) return;
    api.runIssues(run.run_id).then((r) => setIssues(r.issues)).catch(() => undefined);
  }, [open, count, run.run_id]);

  if (count === 0) return null;
  return (
    <div className="mt-2 text-xs">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="text-warn underline decoration-dotted">
        {count === 1 ? "1 problem so far" : `${count} problems so far`} — {open ? "hide" : "show"}
      </button>
      {open && <div className="mt-2 rounded border border-line bg-surface p-3"><IssueList issues={issues} /></div>}
    </div>
  );
}
