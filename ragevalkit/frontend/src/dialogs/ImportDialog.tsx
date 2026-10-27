import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { plural } from "../lib/format";
import type { Group, ImportMapping, ImportPreview, ImportResult } from "../api/types";

type Step = "file" | "check" | "options" | "done";

const STEPS: { key: Step; label: string }[] = [
  { key: "file", label: "File" },
  { key: "check", label: "Check" },
  { key: "options", label: "Add" },
];

const OUTCOME: Record<string, { label: string; cls: string }> = {
  new: { label: "new", cls: "text-good" },
  update: { label: "update", cls: "text-warn" },
  unchanged: { label: "unchanged", cls: "text-muted" },
};

/** Download the rows that could not be imported, with the reason, ready to fix and upload again. */
function downloadProblems(result: ImportResult) {
  const quote = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const header = [...result.columns, "problem"];
  const lines = [header.map(quote).join(",")];
  for (const p of result.problem_rows) lines.push([...result.columns.map((c) => p.cells[c] ?? ""), p.reason].map(quote).join(","));
  const url = URL.createObjectURL(new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "rows_to_fix.csv";
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Bulk import in three small steps: pick a file (or paste rows), check what it will do before anything is
 * saved, then choose whether the cases go into a group. Groups are optional — "no group" is the default.
 */
export function ImportDialog({ groups, initialGroupId, onClose, onDone }: {
  groups: Group[];
  initialGroupId?: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [step, setStep] = useState<Step>("file");
  const [source, setSource] = useState<"file" | "paste">("file");
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [drag, setDrag] = useState(false);
  const [sheet, setSheet] = useState<string | null>(null);
  const [mapping, setMapping] = useState<ImportMapping | null>(null);
  const [showColumns, setShowColumns] = useState(false);
  const [showAllProblems, setShowAllProblems] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [labelMode, setLabelMode] = useState<"none" | "existing" | "new">(initialGroupId ? "existing" : "none");
  const [groupIds, setGroupIds] = useState<Set<string>>(new Set(initialGroupId ? [initialGroupId] : []));
  const [newGroupName, setNewGroupName] = useState("");
  const [updateBySlot, setUpdateBySlot] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, busy]);

  async function check(f: File, opts: { sheet?: string | null; mapping?: ImportMapping | null } = {}) {
    setBusy(true); setError("");
    try {
      const p = await api.previewImport(f, opts);
      setFile(f); setPreview(p); setSheet(p.sheet); setMapping(p.mapping);
      setShowColumns(p.question_missing);
      setStep("check");
      if (!newGroupName) setNewGroupName(f.name.replace(/\.[^.]+$/, ""));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const fromPaste = () => new File([pasted], "pasted.tsv", { type: "text/tab-separated-values" });

  async function run() {
    if (!file || !preview) return;
    setBusy(true); setError("");
    try {
      const r = await api.importCases(file, {
        sheet, mapping,
        groupIds: labelMode === "existing" ? [...groupIds] : [],
        newGroupName: labelMode === "new" ? newGroupName.trim() : undefined,
        updateBySlot,
      });
      setResult(r); setStep("done");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const c = preview?.counts;
  const importable = c ? c.new + c.update + c.unchanged : 0;
  const labelsOk = labelMode === "none" || (labelMode === "existing" && groupIds.size > 0) || (labelMode === "new" && newGroupName.trim().length > 0);
  const toggleGroup = (id: string) => setGroupIds((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const chip = (label: string, value: number, tone: string) => (
    <span className="rounded border border-line bg-surface-2 px-2.5 py-1 text-xs">
      <span className={`mono mr-1.5 text-sm font-semibold ${tone}`}>{value}</span>{label}
    </span>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={() => !busy && onClose()}>
      <div className="card pop-in flex max-h-[94vh] w-full max-w-3xl flex-col bg-surface" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 className="font-serif text-2xl font-medium">Import test cases</h2>
            {step !== "done" && (
              <ol className="mt-1.5 flex items-center gap-2 text-xs text-muted">
                {STEPS.map((s, i) => (
                  <li key={s.key} className={`flex items-center gap-2 ${step === s.key ? "font-semibold text-fg" : ""}`}>
                    {i > 0 && <span aria-hidden>›</span>}
                    <span className={`grid h-4 w-4 place-items-center rounded-full text-[10px] ${step === s.key ? "bg-brand text-white" : "bg-surface-2"}`}>{i + 1}</span>
                    {s.label}
                  </li>
                ))}
              </ol>
            )}
          </div>
          <button onClick={onClose} disabled={busy} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {/* ---------- 1. file ---------- */}
          {step === "file" && (
            <>
              <div className="mb-4 flex gap-1 rounded bg-surface-2 p-1">
                {(["file", "paste"] as const).map((s) => (
                  <button key={s} onClick={() => setSource(s)}
                    className={`flex-1 rounded px-3 py-1.5 text-sm font-medium transition ${source === s ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"}`}>
                    {s === "file" ? "Upload a file" : "Paste rows"}
                  </button>
                ))}
              </div>
              {source === "file" ? (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) check(f); }}
                  onClick={() => input.current?.click()}
                  className={`flex cursor-pointer flex-col items-center gap-1.5 rounded border-2 border-dashed p-10 text-center transition ${drag ? "border-brand bg-brand-soft" : "border-line hover:border-brand/60"}`}
                >
                  <span className="text-base font-medium">{busy ? "Reading…" : "Drop a file here, or click to choose"}</span>
                  <span className="text-xs text-muted">Excel (.xlsx) or CSV. Only the question column is required.</span>
                  <input ref={input} type="file" accept=".xlsx,.xlsm,.csv,.tsv,.txt" hidden
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) check(f); e.target.value = ""; }} />
                </div>
              ) : (
                <>
                  <textarea value={pasted} onChange={(e) => setPasted(e.target.value)} rows={9} spellCheck={false}
                    placeholder={"question\texpected_answer\nWhat is the refund window?\t30 days"}
                    className="mono w-full rounded border border-line bg-surface-2 p-3 text-xs outline-none focus:border-brand" />
                  <p className="mt-1.5 text-xs text-muted">Copy cells from Excel or Google Sheets and paste them here. The first line holds the column names.</p>
                  <button onClick={() => check(fromPaste())} disabled={busy || !pasted.trim()}
                    className="mt-3 rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110">
                    {busy ? "Reading…" : "Check rows"}
                  </button>
                </>
              )}
              <p className="mt-4 text-sm text-muted">
                Not sure how to lay it out?{" "}
                <a href={api.importTemplateUrl()} className="font-medium text-brand hover:underline">Download the template</a>
                {" "}— it has the right columns, two examples and a short guide.
              </p>
            </>
          )}

          {/* ---------- 2. check ---------- */}
          {step === "check" && preview && c && (
            <>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                <span className="font-medium">{preview.filename}</span>
                <span className="text-muted">{plural(preview.total_rows, "row")}</span>
                {preview.sheets.length > 1 && (
                  <label className="flex items-center gap-2 text-xs text-muted">
                    Sheet
                    <select value={sheet ?? ""} disabled={busy}
                      onChange={(e) => file && check(file, { sheet: e.target.value, mapping: null })}
                      className="rounded border border-line bg-surface-2 px-2 py-1 text-xs text-fg outline-none">
                      {preview.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </label>
                )}
                <button onClick={() => { setStep("file"); setError(""); }} className="ml-auto text-xs text-brand hover:underline">Choose another file</button>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {chip("new", c.new, "text-good")}
                {chip("will be updated", c.update, "text-warn")}
                {chip("already there", c.unchanged, "text-muted")}
                {chip("can't be imported", c.problem, c.problem ? "text-bad" : "text-muted")}
              </div>

              <ul className="mt-3 space-y-1 text-xs text-muted">
                {preview.question_missing && <li className="text-bad">No question column was found — choose it below.</li>}
                {preview.auto_chat && !preview.question_missing && <li>No chat column: every question becomes its own single-turn chat.</li>}
                {!preview.auto_chat && preview.auto_turn && <li>No turn column: turns are numbered 1, 2, 3… within each chat, in file order.</li>}
                {preview.ignored_columns.length > 0 && <li>Ignored columns: {preview.ignored_columns.join(", ")}</li>}
              </ul>

              <div className="mt-3">
                <button onClick={() => setShowColumns((s) => !s)} className="text-xs font-medium text-brand hover:underline">
                  {showColumns ? "Hide column matching" : "Check which column is which"}
                </button>
                {showColumns && mapping && (
                  <div className="mt-2 grid gap-x-6 gap-y-2 rounded border border-line bg-surface-2 p-3 sm:grid-cols-2">
                    {preview.fields.map((f) => (
                      <label key={f} className="flex items-center justify-between gap-3 text-xs">
                        <span className={f === "question" && !mapping[f] ? "font-semibold text-bad" : "text-muted"}>
                          {preview.field_labels[f]}{f === "question" ? " *" : ""}
                        </span>
                        <select value={mapping[f] ?? ""} disabled={busy}
                          onChange={(e) => {
                            const next = { ...mapping, [f]: e.target.value || null };
                            setMapping(next);
                            if (file) check(file, { sheet, mapping: next });
                          }}
                          className="w-44 rounded border border-line bg-surface px-2 py-1 text-xs text-fg outline-none">
                          <option value="">— none —</option>
                          {preview.columns.map((col) => <option key={col} value={col}>{col}</option>)}
                        </select>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {preview.sample.length > 0 && (
                <div className="mt-4 overflow-x-auto rounded border border-line">
                  <table className="w-full min-w-[560px] text-left text-xs">
                    <thead className="bg-surface-2 uppercase tracking-[0.06em] text-muted">
                      <tr>
                        <th className="px-3 py-2 font-medium">Row</th>
                        <th className="px-3 py-2 font-medium">Chat</th>
                        <th className="px-3 py-2 font-medium">Turn</th>
                        <th className="px-3 py-2 font-medium">Question</th>
                        <th className="px-3 py-2 font-medium">Groups</th>
                        <th className="px-3 py-2 font-medium">Result</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {preview.sample.map((r) => (
                        <tr key={r.row}>
                          <td className="mono px-3 py-2 text-muted">{r.row}</td>
                          <td className="mono max-w-[110px] truncate px-3 py-2" title={r.chat_id}>{r.chat_id}</td>
                          <td className="mono px-3 py-2 text-muted">{r.turn_no}</td>
                          <td className="max-w-[300px] truncate px-3 py-2" title={r.question}>{r.question}</td>
                          <td className="max-w-[140px] truncate px-3 py-2 text-muted">{r.groups.join(", ") || "—"}</td>
                          <td className={`px-3 py-2 font-medium ${OUTCOME[r.outcome]?.cls ?? ""}`}>{OUTCOME[r.outcome]?.label ?? r.outcome}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {c.new + c.update + c.unchanged > preview.sample.length && (
                    <p className="border-t border-line bg-surface-2 px-3 py-1.5 text-[11px] text-muted">
                      Showing the first {preview.sample.length} usable rows.
                    </p>
                  )}
                </div>
              )}

              {preview.problems.length > 0 && (
                <div className="mt-4 rounded border border-bad/50 p-3">
                  <div className="text-xs font-semibold text-bad">{plural(c.problem, "row")} can't be imported</div>
                  <ul className="mt-1.5 space-y-1 text-xs">
                    {(showAllProblems ? preview.problems : preview.problems.slice(0, 5)).map((p) => (
                      <li key={p.row}><span className="mono text-muted">Row {p.row}</span> — {p.reason}</li>
                    ))}
                  </ul>
                  {preview.problems.length > 5 && (
                    <button onClick={() => setShowAllProblems((s) => !s)} className="mt-1.5 text-xs text-brand hover:underline">
                      {showAllProblems ? "Show fewer" : `Show ${preview.problems.length - 5} more`}
                    </button>
                  )}
                  <p className="mt-1.5 text-[11px] text-muted">You can import the rest now and download these rows to fix afterwards.</p>
                </div>
              )}
            </>
          )}

          {/* ---------- 3. options ---------- */}
          {step === "options" && preview && c && (
            <>
              <div className="label mb-2">Put these test cases in…</div>
              <div className="space-y-2">
                <label className={`flex cursor-pointer items-start gap-3 rounded border p-3 text-sm ${labelMode === "none" ? "border-brand bg-brand-soft" : "border-line"}`}>
                  <input type="radio" name="mode" checked={labelMode === "none"} onChange={() => setLabelMode("none")} className="mt-0.5 accent-brand" />
                  <span><span className="font-medium">No group</span><span className="block text-xs text-muted">Just add them to the library. You can label them later.</span></span>
                </label>
                <label className={`flex cursor-pointer items-start gap-3 rounded border p-3 text-sm ${labelMode === "existing" ? "border-brand bg-brand-soft" : "border-line"}`}>
                  <input type="radio" name="mode" checked={labelMode === "existing"} onChange={() => setLabelMode("existing")} className="mt-0.5 accent-brand" />
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">Existing groups</span>
                    {labelMode === "existing" && (groups.length === 0 ? (
                      <span className="mt-1 block text-xs text-muted">There are no groups yet.</span>
                    ) : (
                      <span className="mt-2 block max-h-40 divide-y divide-line overflow-y-auto rounded border border-line bg-surface">
                        {groups.map((g) => (
                          <span key={g.group_id} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-surface-2">
                            <input type="checkbox" checked={groupIds.has(g.group_id)} onChange={() => toggleGroup(g.group_id)} className="accent-brand" />
                            <span className="flex-1 truncate">{g.name}</span>
                            <span className="mono text-xs text-muted">{g.member_count}</span>
                          </span>
                        ))}
                      </span>
                    ))}
                  </span>
                </label>
                <label className={`flex cursor-pointer items-start gap-3 rounded border p-3 text-sm ${labelMode === "new" ? "border-brand bg-brand-soft" : "border-line"}`}>
                  <input type="radio" name="mode" checked={labelMode === "new"} onChange={() => setLabelMode("new")} className="mt-0.5 accent-brand" />
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">A new group</span>
                    {labelMode === "new" && (
                      <input value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} placeholder="Group name" autoFocus
                        className="mt-2 w-full rounded border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand" />
                    )}
                  </span>
                </label>
              </div>

              {preview.group_names_in_file.length > 0 && (
                <p className="mt-3 rounded bg-surface-2 px-3 py-2 text-xs text-muted">
                  The file has a groups column, so each row is also added to the groups it names
                  ({preview.group_names_in_file.join(", ")}){preview.new_group_names.length > 0 && <> — new: <b className="text-fg">{preview.new_group_names.join(", ")}</b></>}.
                </p>
              )}

              {preview.slot_conflicts > 0 && (
                <div className="mt-4 rounded border border-warn/60 p-3 text-sm">
                  <div className="font-medium">
                    {plural(preview.slot_conflicts, "row")} use{preview.slot_conflicts === 1 ? "s" : ""} the same chat and turn as a test case you already have, with a different question.
                  </div>
                  <label className="mt-2 flex cursor-pointer items-start gap-2 text-xs">
                    <input type="radio" name="slot" checked={!updateBySlot} onChange={() => setUpdateBySlot(false)} className="mt-0.5 accent-brand" />
                    <span><b>Add them as new test cases</b> (the existing ones stay as they are)</span>
                  </label>
                  <label className="mt-1.5 flex cursor-pointer items-start gap-2 text-xs">
                    <input type="radio" name="slot" checked={updateBySlot} onChange={() => setUpdateBySlot(true)} className="mt-0.5 accent-brand" />
                    <span><b>Update the existing test cases</b> with the new question (a new version is saved, history is kept)</span>
                  </label>
                </div>
              )}

              <p className="mt-4 text-sm">
                Ready to import: <b>{plural(c.new, "new test case")}</b>
                {c.update > 0 && <>, <b>{c.update} updated</b></>}
                {c.unchanged > 0 && <>, {c.unchanged} already there</>}.
              </p>
            </>
          )}

          {/* ---------- done ---------- */}
          {step === "done" && result && (
            <div className="py-2">
              <div className="font-serif text-xl font-medium">Import finished</div>
              <ul className="mt-3 space-y-1.5 text-sm">
                <li><b className="text-good">{result.new}</b> new test case{result.new !== 1 ? "s" : ""} added</li>
                {result.updated > 0 && <li><b className="text-warn">{result.updated}</b> updated (a new version was saved)</li>}
                {result.unchanged > 0 && <li><b>{result.unchanged}</b> already in the library, unchanged</li>}
                {result.labelled > 0 && <li><b>{result.labelled}</b> group label{result.labelled !== 1 ? "s" : ""} added</li>}
                {result.groups_created.length > 0 && <li>New group{result.groups_created.length !== 1 ? "s" : ""}: <b>{result.groups_created.join(", ")}</b></li>}
              </ul>
              {result.problems > 0 && (
                <div className="mt-4 rounded border border-bad/50 p-3 text-sm">
                  <b className="text-bad">{plural(result.problems, "row")}</b> could not be imported.
                  <button onClick={() => downloadProblems(result)} className="ml-3 rounded border border-line px-3 py-1 text-xs font-medium hover:bg-surface-2">
                    Download them with the reason
                  </button>
                  <p className="mt-1.5 text-xs text-muted">Fix the rows, then import that file — the rows that already went in are left unchanged.</p>
                </div>
              )}
            </div>
          )}

          {error && <p className="mt-4 rounded border border-bad p-3 text-sm text-bad" role="alert">{error}</p>}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-line px-6 py-4">
          {step === "check" && <button onClick={() => setStep("file")} className="rounded px-4 py-2 text-sm font-medium text-muted hover:bg-surface-2">Back</button>}
          {step === "options" && <button onClick={() => setStep("check")} disabled={busy} className="rounded px-4 py-2 text-sm font-medium text-muted hover:bg-surface-2">Back</button>}
          {(step === "file") && <span />}
          {step === "done" && <span />}
          <div className="flex gap-2">
            {step === "check" && (
              <button onClick={() => setStep("options")} disabled={busy || importable === 0 || preview?.question_missing}
                className="rounded bg-brand px-5 py-2 text-sm font-medium text-white disabled:opacity-40 enabled:hover:brightness-110">
                Next
              </button>
            )}
            {step === "options" && (
              <button onClick={run} disabled={busy || !labelsOk}
                className="rounded bg-brand px-5 py-2 text-sm font-medium text-white disabled:opacity-40 enabled:hover:brightness-110">
                {busy ? "Importing…" : "Import"}
              </button>
            )}
            {step === "done" && result && (
              <button onClick={() => onDone(`${plural(result.new, "test case")} added${result.updated ? `, ${result.updated} updated` : ""}${result.problems ? `, ${plural(result.problems, "row")} skipped` : ""}`)}
                className="rounded bg-brand px-5 py-2 text-sm font-medium text-white hover:brightness-110">
                Done
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
