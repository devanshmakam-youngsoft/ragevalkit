import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useRun } from "../RunContext";
import type { DatasetInfo, Group, RunPreview, RunSelection, TestCase, VersionSummary } from "../types";
import { nextVersion } from "../lib";
import { GroupChips } from "./GroupChips";

const VERSION_RE = /^[A-Za-z0-9._-]{1,20}$/;
const MAX_LISTED = 200;

type Tab = "library" | "upload";
type Mode = "groups" | "cases";

/** Pre-selection when the dialog is opened from somewhere that already knows what to run. */
export interface ExecuteInitial {
  mode: Mode;
  groupIds?: string[];
  tcIds?: string[];
}

export function ExecuteModal({ onClose, initial }: { onClose: () => void; initial?: ExecuteInitial }) {
  const { start, startFromSelection, startRunAndSave } = useRun();
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [version, setVersion] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState("");

  // Library tab state
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [mode, setMode] = useState<Mode>(initial?.mode ?? "groups");
  const [groupIds, setGroupIds] = useState<Set<string>>(new Set(initial?.groupIds ?? []));
  const [tcIds, setTcIds] = useState<Set<string>>(new Set(initial?.tcIds ?? []));
  const [statusFilter, setStatusFilter] = useState("active");
  const [includeContext, setIncludeContext] = useState(true);
  const [caseQuery, setCaseQuery] = useState("");
  const [preview, setPreview] = useState<RunPreview | null>(null);
  const [previewErr, setPreviewErr] = useState("");

  // Upload tab state
  const [defaultInfo, setDefaultInfo] = useState<DatasetInfo | null>(null);
  const [defaultErr, setDefaultErr] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInfo, setFileInfo] = useState<DatasetInfo | null>(null);
  const [fileErr, setFileErr] = useState("");
  const [validating, setValidating] = useState(false);
  const [drag, setDrag] = useState(false);
  const [saveAsGroup, setSaveAsGroup] = useState(false);
  const [groupName, setGroupName] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const [tab, setTab] = useState<Tab>("library");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);

    Promise.all([api.versions(), api.groups(), api.testCases()]).then(([vs, gs, tcs]) => {
      setVersions(vs);
      setVersion(nextVersion(vs));
      setGroups(gs);
      setCases(tcs.filter((c) => c.status !== "deleted"));
      if (initial) {
        setTab("library");
      } else if (gs.length > 0) {
        setGroupIds(new Set(gs.map((g) => g.group_id))); // nothing narrower asked for: start from everything
        setTab("library");
      } else {
        setTab("upload");
      }
    }).catch(() => setTab("upload"));

    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose]);

  useEffect(() => {
    if (tab === "upload" && !defaultInfo) {
      api.defaultDataset().then(setDefaultInfo).catch((e) => setDefaultErr(e.message));
    }
  }, [tab, defaultInfo]);

  const exists = versions.some((v) => String(v.version) === version.trim());
  const versionValid = VERSION_RE.test(version.trim());

  // What the library tab would run, as sent to the server.
  const selection: RunSelection | null = useMemo(() => {
    if (mode === "groups") {
      return groupIds.size ? { groupIds: [...groupIds], statusFilter, includeContext } : null;
    }
    return tcIds.size ? { tcIds: [...tcIds], includeContext } : null;
  }, [mode, groupIds, tcIds, statusFilter, includeContext]);

  // Ask the server how many cases that is (it knows about status, overlaps and earlier turns).
  useEffect(() => {
    if (tab !== "library" || !selection) { setPreview(null); setPreviewErr(""); return; }
    let stale = false;
    const t = window.setTimeout(() => {
      api.previewRun(selection)
        .then((p) => { if (!stale) { setPreview(p); setPreviewErr(""); } })
        .catch((e) => { if (!stale) { setPreview(null); setPreviewErr((e as Error).message); } });
    }, 250);
    return () => { stale = true; window.clearTimeout(t); };
  }, [tab, selection]);

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    setter(next);
  };

  const shownCases = useMemo(() => {
    const q = caseQuery.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter((c) =>
      c.question.toLowerCase().includes(q) || c.chat_id.toLowerCase().includes(q) ||
      c.groups.some((g) => g.name.toLowerCase().includes(q)));
  }, [cases, caseQuery]);

  async function pick(f: File | undefined) {
    if (!f) return;
    setFile(f); setFileInfo(null); setFileErr(""); setValidating(true);
    if (!groupName) setGroupName(f.name.replace(/\.xlsx$/i, ""));
    try { setFileInfo(await api.validateDataset(f)); }
    catch (e) { setFileErr((e as Error).message); }
    finally { setValidating(false); }
  }

  function clearFile() {
    setFile(null); setFileInfo(null); setFileErr("");
    if (input.current) input.current.value = "";
  }

  const hasCollisions = (preview?.collisions.length ?? 0) > 0;
  const libraryOk = !!preview && preview.total > 0 && !hasCollisions;
  const uploadOk = file ? !!fileInfo : !!defaultInfo;
  const datasetOk = tab === "library" ? libraryOk : uploadOk;
  const canStart = versionValid && datasetOk && !validating && !submitting && (!exists || overwrite);
  const active = file ? fileInfo : defaultInfo;

  async function submit() {
    setSubmitting(true); setError("");
    try {
      if (tab === "library" && selection) {
        await startFromSelection(version.trim(), overwrite, notes.trim(), selection);
      } else if (saveAsGroup && groupName.trim() && file) {
        await startRunAndSave(version.trim(), file, overwrite, groupName.trim());
      } else {
        await start(version.trim(), file, overwrite);
      }
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  }

  const segment = (on: boolean) =>
    `flex-1 rounded px-3 py-1.5 text-sm font-medium transition ${on ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={onClose}>
      <div className="card pop-in max-h-[94vh] w-full max-w-xl overflow-y-auto bg-surface p-6" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-serif text-2xl font-medium">Execute session</h2>
            <p className="mt-0.5 text-sm text-muted">Run test cases against your pipeline and grade every answer.</p>
          </div>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        {/* Version */}
        <label className="label mt-5 block">Version number</label>
        <input value={version} onChange={(e) => { setVersion(e.target.value); setOverwrite(false); }}
          className="mt-1.5 w-full rounded border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
          placeholder="e.g. 7" />
        {!versionValid && version && <p className="mt-1.5 text-xs text-bad">Use letters, digits, ".", "_" or "-" (max 20 chars).</p>}
        {versionValid && exists && (
          <label className="mt-2 flex cursor-pointer items-start gap-2 rounded bg-warn-soft p-3 text-xs text-warn">
            <span className="flex-1">Version {version} already exists. Tick to overwrite.</span>
            <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} className="mt-0.5" />
          </label>
        )}

        {/* Source */}
        <div className="mt-5">
          <div className="mb-3 flex gap-1 rounded bg-surface-2 p-1">
            <button onClick={() => setTab("library")} className={segment(tab === "library")}>From library</button>
            <button onClick={() => setTab("upload")} className={segment(tab === "upload")}>Upload &amp; Run</button>
          </div>

          {tab === "library" ? (
            groups === null ? (
              <p className="text-xs text-muted">Loading…</p>
            ) : cases.length === 0 ? (
              <p className="text-xs text-muted">The library is empty. Upload an .xlsx in the "Upload &amp; Run" tab, or add test cases on the Test Cases page.</p>
            ) : (
              <>
                <div className="mb-3 flex items-center gap-3">
                  <span className="label">Run</span>
                  <div className="flex gap-1 rounded bg-surface-2 p-1">
                    <button onClick={() => setMode("groups")} className={`${segment(mode === "groups")} px-4`}>Groups</button>
                    <button onClick={() => setMode("cases")} className={`${segment(mode === "cases")} px-4`}>Pick test cases</button>
                  </div>
                </div>

                {mode === "groups" ? (
                  <>
                    <div className="mb-2 flex items-center justify-between">
                      <label className="label">Groups to run</label>
                      <div className="flex gap-2 text-xs">
                        <button onClick={() => setGroupIds(new Set(groups.map((g) => g.group_id)))} className="text-brand hover:underline">All</button>
                        <span className="text-muted">·</span>
                        <button onClick={() => setGroupIds(new Set())} className="text-muted hover:text-fg">None</button>
                      </div>
                    </div>
                    {groups.length === 0 ? (
                      <p className="text-xs text-muted">No groups yet — switch to "Pick test cases", or create groups on the Groups page.</p>
                    ) : (
                      <div className="max-h-44 divide-y divide-line overflow-y-auto rounded border border-line">
                        {groups.map((g) => {
                          const checked = groupIds.has(g.group_id);
                          return (
                            <label key={g.group_id}
                              className={`flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm transition hover:bg-surface-2 ${checked ? "bg-brand-soft" : ""}`}>
                              <input type="checkbox" checked={checked} onChange={() => toggle(groupIds, setGroupIds, g.group_id)} className="accent-brand" />
                              <span className="flex-1 truncate font-medium">{g.name}</span>
                              <span className="mono text-xs text-muted">{g.member_count} cases</span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                    <div className="mt-3">
                      <label className="label mb-1.5 block">Include cases that are</label>
                      <div className="flex gap-2">
                        {(["active", "inactive", "all"] as const).map((s) => (
                          <button key={s} onClick={() => setStatusFilter(s)}
                            className={`rounded border px-3 py-1.5 text-xs font-medium transition ${
                              statusFilter === s ? "border-brand bg-brand text-white" : "border-line text-muted hover:border-brand hover:text-brand"
                            }`}>
                            {s === "all" ? "Active + inactive" : s.charAt(0).toUpperCase() + s.slice(1)}
                          </button>
                        ))}
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="mb-2 flex items-center gap-2">
                      <input value={caseQuery} onChange={(e) => setCaseQuery(e.target.value)} placeholder="Search by question, chat or group…"
                        className="min-w-0 flex-1 rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
                      <div className="flex shrink-0 gap-2 text-xs">
                        <button onClick={() => setTcIds(new Set([...tcIds, ...shownCases.slice(0, MAX_LISTED).map((c) => c.tc_id)]))}
                          className="text-brand hover:underline">Select shown</button>
                        <span className="text-muted">·</span>
                        <button onClick={() => setTcIds(new Set())} className="text-muted hover:text-fg">Clear</button>
                      </div>
                    </div>
                    <div className="max-h-56 divide-y divide-line overflow-y-auto rounded border border-line">
                      {shownCases.slice(0, MAX_LISTED).map((c) => {
                        const checked = tcIds.has(c.tc_id);
                        return (
                          <label key={c.tc_id}
                            className={`flex cursor-pointer items-start gap-3 px-3 py-2 text-sm transition hover:bg-surface-2 ${checked ? "bg-brand-soft" : ""}`}>
                            <input type="checkbox" checked={checked} onChange={() => toggle(tcIds, setTcIds, c.tc_id)} className="mt-1 accent-brand" />
                            <span className="mono mt-0.5 w-[76px] shrink-0 text-[11px] text-muted">{c.chat_id} · {c.turn_no}</span>
                            <span className="min-w-0 flex-1">
                              <span className="line-clamp-2">{c.question}</span>
                              {(c.groups.length > 0 || c.status !== "active") && (
                                <span className="mt-1 flex flex-wrap items-center gap-1.5">
                                  <GroupChips groups={c.groups} max={2} />
                                  {c.status !== "active" && <span className="mono text-[10px] text-muted">{c.status}</span>}
                                </span>
                              )}
                            </span>
                          </label>
                        );
                      })}
                      {shownCases.length === 0 && <p className="px-3 py-6 text-center text-xs text-muted">No test cases match.</p>}
                    </div>
                    {shownCases.length > MAX_LISTED && (
                      <p className="mt-1.5 text-xs text-muted">Showing the first {MAX_LISTED} of {shownCases.length} — narrow the search to see the rest.</p>
                    )}
                  </>
                )}

                {/* What will actually run */}
                <div className="mt-4 rounded border border-line bg-surface-2 px-3.5 py-3 text-sm">
                  {!selection ? (
                    <span className="text-muted">{mode === "groups" ? "Select at least one group." : "Select at least one test case."}</span>
                  ) : previewErr ? (
                    <span className="text-bad">{previewErr}</span>
                  ) : !preview ? (
                    <span className="text-muted">Counting…</span>
                  ) : (
                    <>
                      <div>
                        <span className="font-medium">{preview.total}</span> test case{preview.total !== 1 ? "s" : ""} will run
                        {preview.context > 0 && (
                          <span className="text-muted"> — {preview.selected} selected + {preview.context} earlier turn{preview.context !== 1 ? "s" : ""} for context</span>
                        )}
                      </div>
                      {preview.total === 0 && <div className="mt-1 text-xs text-warn">Nothing matches — try including inactive cases or pick other groups.</div>}
                      {preview.missing > 0 && <div className="mt-1 text-xs text-warn">{preview.missing} picked case{preview.missing !== 1 ? "s were" : " was"} deleted and will be skipped.</div>}
                      {hasCollisions && (
                        <div className="mt-1 text-xs text-bad">
                          Chat {preview.collisions[0].chat_id} turn {preview.collisions[0].turn_no} is used by {preview.collisions[0].tc_ids.length} different
                          test cases{preview.collisions.length > 1 ? ` (and ${preview.collisions.length - 1} more clash${preview.collisions.length > 2 ? "es" : ""})` : ""}.
                          Deselect one or change its chat / turn.
                        </div>
                      )}
                    </>
                  )}
                </div>
                <label className="mt-2 flex cursor-pointer items-start gap-2 text-xs text-muted">
                  <input type="checkbox" checked={includeContext} onChange={(e) => setIncludeContext(e.target.checked)} className="mt-0.5 accent-brand" />
                  <span>
                    Include earlier turns of each conversation. A follow-up question needs the turns before it for context;
                    turning this off runs only what you selected.
                  </span>
                </label>
              </>
            )
          ) : (
            <>
              <div className="flex items-center gap-3 rounded border border-line bg-surface-2 p-3.5">
                <div className="mono grid h-9 w-11 shrink-0 place-items-center border border-line text-[10px] text-brand">.xlsx</div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{file ? file.name : defaultInfo?.name ?? "Default dataset"}</div>
                  <div className="text-xs text-muted">
                    {validating ? "Checking…" : active ? `${active.rows} questions · ${active.chats} conversations` : defaultErr || "Loading…"}
                    {!file && defaultInfo && " · from data folder"}
                  </div>
                </div>
                {validating ? <span className="mono text-xs text-muted">checking</span>
                  : active ? <span className="mono text-xs text-good">valid</span> : null}
                {file && <button onClick={clearFile} className="text-xs font-medium text-brand hover:underline">Use default</button>}
              </div>
              {!file && (
                <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                  onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
                  onClick={() => input.current?.click()}
                  className={`mt-3 flex cursor-pointer flex-col items-center gap-1 rounded border-2 border-dashed p-4 text-center text-sm transition ${drag ? "border-brand bg-brand-soft" : "border-line hover:border-brand/60"}`}>
                  <span className="font-medium">Upload a different .xlsx</span>
                  <span className="text-xs text-muted">Needs: chat_id, turn_no, type, question, expected_answer</span>
                </div>
              )}
              <input ref={input} type="file" accept=".xlsx" hidden onChange={(e) => pick(e.target.files?.[0])} />
              {fileErr && <div className="mt-3 border border-bad p-3 text-xs text-bad">{fileErr}</div>}
              <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" checked={saveAsGroup} onChange={(e) => setSaveAsGroup(e.target.checked)} />
                <span>Save as test case group</span>
              </label>
              {saveAsGroup && (
                <input value={groupName} onChange={(e) => setGroupName(e.target.value)}
                  placeholder="Group name…"
                  className="mt-2 w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
              )}
            </>
          )}
        </div>

        {/* Notes */}
        <label className="label mt-5 block">Run notes <span className="normal-case font-normal text-muted">(optional)</span></label>
        <input value={notes} onChange={(e) => setNotes(e.target.value)}
          placeholder="What changed in this version? e.g. Switched to GPT-4o, tuned retrieval k=5"
          className="mt-1.5 w-full rounded border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/25" />

        {error && <div className="mt-3 border border-bad p-3 text-xs text-bad">{error}</div>}

        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-4 py-2.5 text-sm font-medium text-muted hover:bg-surface-2">Cancel</button>
          <button onClick={submit} disabled={!canStart}
            className="rounded bg-brand px-5 py-2.5 text-sm font-medium text-white transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40">
            {submitting ? "Starting…" : tab === "library" && preview ? `Run ${preview.total} test case${preview.total !== 1 ? "s" : ""}` : "Start evaluation"}
          </button>
        </div>
      </div>
    </div>
  );
}
