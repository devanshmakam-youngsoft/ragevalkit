import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { fmt, fmtDate, fmtSeconds, plural } from "../lib/format";
import { useRun } from "../context/RunContext";
import { GLOSSARY, Term } from "./Hint";
import type { GroupHistory as History, GroupRunStat } from "../api/types";

const SHOWN = 5;

function Figure({ label, run, children }: { label: string; run: GroupRunStat | null; children?: React.ReactNode }) {
  return (
    <div className="min-w-[210px]">
      <div className="label">{label}</div>
      {run ? (
        <>
          <div className="mt-1.5 flex items-baseline gap-3">
            <Link to={`/v/${run.version}`} className="num text-[28px] leading-none text-brand hover:underline">v{run.version}</Link>
            <span className="text-xs text-muted">{fmtDate(run.date)}</span>
          </div>
          <div className="mono mt-1.5 text-xs text-muted">
            answer {fmt(run.avg_answer_marks)} · context {fmt(run.avg_material_marks)} · {fmtSeconds(run.avg_total_time)}
          </div>
          {children}
        </>
      ) : (
        <div className="mt-1.5 text-sm text-muted">—</div>
      )}
    </div>
  );
}

/** How a group has done: its last run, the best version so far, and every run in between. */
export function GroupHistory({ groupId, onRun }: { groupId: string; onRun: () => void }) {
  const { versionsKey } = useRun();
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState("");
  const [all, setAll] = useState(false);

  useEffect(() => {
    let stale = false;
    setHistory(null);
    api.groupHistory(groupId)
      .then((h) => { if (!stale) { setHistory(h); setError(""); } })
      .catch((e) => { if (!stale) setError(e.message); });
    return () => { stale = true; };
  }, [groupId, versionsKey]);

  if (error) return null;
  if (!history) return <div className="card mb-4 px-5 py-4 text-sm text-muted">Loading history…</div>;

  const { runs, best, last } = history;
  const shown = all ? runs : runs.slice(0, SHOWN);
  return (
    <section className="card mb-4 overflow-hidden">
      <div className="flex flex-wrap items-start gap-x-10 gap-y-4 p-5">
        {runs.length === 0 ? (
          <div>
            <div className="label">History</div>
            <p className="mt-1.5 text-sm text-muted">This group has not been run yet.</p>
          </div>
        ) : (
          <>
            <Figure label="Last run" run={last} />
            <Figure label="Best version so far" run={best}>
              {best && <div className="mono mt-1 text-[11px] text-brand">overall score {best.quality?.toFixed(2)}{best === last ? " · also the latest" : ""}</div>}
            </Figure>
            <div className="min-w-[120px]">
              <div className="label">Runs</div>
              <div className="num mt-1.5 text-[28px] leading-none">{history.run_count}</div>
            </div>
          </>
        )}
        <button onClick={onRun} disabled={history.group.member_count === 0}
          className="ml-auto rounded bg-brand px-4 py-2 text-sm font-medium text-white enabled:hover:brightness-110 disabled:opacity-40">
          Run this group
        </button>
      </div>
      {history.basis_note && <p className="px-5 pb-3 text-xs text-warn">{history.basis_note}</p>}
      {history.compared_cases != null && runs.length > 1 && (
        <p className="px-5 pb-3 text-xs text-muted">
          "Best" and the overall score compare versions on the {plural(history.compared_cases, "test case")} they all ran in this group.
          The other columns show what the group scored in each run.
        </p>
      )}

      {runs.length > 0 && (
        <div className="overflow-x-auto border-t border-line">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
              <tr>
                <th className="px-5 py-2.5 font-medium">Version</th>
                <th className="px-3 py-2.5 font-medium">Executed</th>
                <th className="px-3 py-2.5 font-medium">Cases</th>
                <th className="px-3 py-2.5 font-medium"><Term k="answer" avg /></th>
                <th className="px-3 py-2.5 font-medium"><Term k="context" avg /></th>
                <th className="px-3 py-2.5 font-medium"><Term k="time" avg /></th>
                <th className="px-3 py-2.5 font-medium"><Term k="overall" /></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {shown.map((r) => (
                <tr key={r.version}>
                  <td className="px-5 py-2.5">
                    <Link to={`/v/${r.version}`} className="mono font-medium text-brand hover:underline">v{r.version}</Link>
                    {best?.version === r.version && <span className="mono ml-2 text-[10px] uppercase tracking-wider text-brand">best</span>}
                    {r.stopped && <span className="mono ml-2 text-[10px] text-warn">stopped</span>}
                    {r.failed_rows > 0 && <span className="mono ml-2 text-[10px] text-bad">{r.failed_rows} failed</span>}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted">{fmtDate(r.date)}</td>
                  <td className="mono px-3 py-2.5 text-xs">{r.total_rows}</td>
                  <td className="mono px-3 py-2.5">{fmt(r.avg_answer_marks)}</td>
                  <td className="mono px-3 py-2.5">{fmt(r.avg_material_marks)}</td>
                  <td className="mono px-3 py-2.5">{fmtSeconds(r.avg_total_time)}</td>
                  <td className="mono px-3 py-2.5">{r.quality == null ? "—" : r.quality.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs.length > SHOWN && (
            <button onClick={() => setAll((a) => !a)} className="w-full border-t border-line px-5 py-2.5 text-left text-xs text-brand hover:underline">
              {all ? "Show fewer" : `Show all ${runs.length} runs`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
