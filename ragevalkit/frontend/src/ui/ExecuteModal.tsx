import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useRun } from "../RunContext";
import type { DatasetInfo, Group, VersionSummary } from "../types";
import { nextVersion } from "../lib";

const VERSION_RE = /^[A-Za-z0-9._-]{1,20}$/;

type Tab = "group" | "upload";

export function ExecuteModal({ onClose }: { onClose: () => void }) {
  const { start, startFromGroups, startRunAndSave } = useRun();
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [version, setVersion] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Group tab state
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState("active");
  const [notes, setNotes] = useState("");

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

  const [tab, setTab] = useState<Tab>("group");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);

    Promise.all([api.versions(), api.groups()]).then(([vs, gs]) => {
      setVersions(vs);
      setVersion(nextVersion(vs));
      setGroups(gs);
      if (gs.length > 0) {
        // Pre-select all groups by default
        setSelectedGroupIds(new Set(gs.map((g) => g.group_id)));
        setTab("group");
      } else {
        setTab("upload");
        api.defaultDataset().then(setDefaultInfo).catch((e) => setDefaultErr(e.message));
      }
    }).catch(() => {
      setTab("upload");
      api.defaultDataset().then(setDefaultInfo).catch((e) => setDefaultErr(e.message));
    });

    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (tab === "upload" && !defaultInfo) {
      api.defaultDataset().then(setDefaultInfo).catch((e) => setDefaultErr(e.message));
    }
  }, [tab, defaultInfo]);

  const exists = versions.some((v) => String(v.version) === version.trim());
  const versionValid = VERSION_RE.test(version.trim());
  const hasGroups = groups !== null && groups.length > 0;

  // Total cases across selected groups
  const selectedCount = groups
    ? groups.filter((g) => selectedGroupIds.has(g.group_id)).reduce((s, g) => s + g.member_count, 0)
    : 0;

  function toggleGroup(gid: string) {
    setSelectedGroupIds((prev) => {
      const next = new Set(prev);
      if (next.has(gid)) next.delete(gid);
      else next.add(gid);
      return next;
    });
  }

  function selectAll() { setSelectedGroupIds(new Set((groups ?? []).map((g) => g.group_id))); }
  function selectNone() { setSelectedGroupIds(new Set()); }

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

  const uploadDatasetOk = file ? !!fileInfo : !!defaultInfo;
  const groupDatasetOk = selectedGroupIds.size > 0;
  const datasetOk = tab === "group" ? groupDatasetOk : uploadDatasetOk;
  const canStart = versionValid && datasetOk && !validating && !submitting && (!exists || overwrite);
  const active = file ? fileInfo : defaultInfo;

  async function submit() {
    setSubmitting(true); setError("");
    try {
      if (tab === "group") {
        await startFromGroups(version.trim(), Array.from(selectedGroupIds), overwrite, statusFilter, notes.trim());
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={onClose}>
      <div className="card pop-in w-full max-w-lg bg-surface p-6" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-serif text-2xl font-medium">Execute session</h2>
            <p className="mt-0.5 text-sm text-muted">Grade every question in your test set.</p>
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

        {/* Tabs */}
        <div className="mt-5">
          <div className="mb-3 flex gap-1 rounded bg-surface-2 p-1">
            <button onClick={() => setTab("group")}
              className={`flex-1 rounded px-3 py-1.5 text-sm font-medium transition ${tab === "group" ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"}`}>
              From Groups
            </button>
            <button onClick={() => setTab("upload")}
              className={`flex-1 rounded px-3 py-1.5 text-sm font-medium transition ${tab === "upload" ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"}`}>
              Upload &amp; Run
            </button>
          </div>

          {tab === "group" ? (
            groups === null ? (
              <p className="text-xs text-muted">Loading groups…</p>
            ) : !hasGroups ? (
              <p className="text-xs text-muted">No groups yet. Upload an .xlsx in the "Upload &amp; Run" tab to get started.</p>
            ) : (
              <>
                <div className="flex items-center justify-between mb-2">
                  <label className="label">Select groups to run</label>
                  <div className="flex gap-2 text-xs">
                    <button onClick={selectAll} className="text-brand hover:underline">All</button>
                    <span className="text-muted">·</span>
                    <button onClick={selectNone} className="text-muted hover:text-fg">None</button>
                  </div>
                </div>
                <div className="max-h-44 overflow-y-auto rounded border border-line divide-y divide-line">
                  {groups.map((g) => {
                    const checked = selectedGroupIds.has(g.group_id);
                    return (
                      <label key={g.group_id}
                        className={`flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm transition hover:bg-surface-2 ${checked ? "bg-brand-soft" : ""}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleGroup(g.group_id)} className="accent-brand" />
                        <span className="flex-1 font-medium">{g.name}</span>
                        <span className="mono text-xs text-muted">{g.member_count} cases</span>
                      </label>
                    );
                  })}
                </div>
                {selectedGroupIds.size > 0 && (
                  <p className="mt-1.5 text-xs text-muted">
                    {selectedGroupIds.size} group{selectedGroupIds.size > 1 ? "s" : ""} · <span className="font-medium text-fg">{selectedCount}</span> test cases total
                  </p>
                )}
                <div className="mt-3">
                  <label className="label mb-1.5 block">Run cases with status</label>
                  <div className="flex gap-2">
                    {(["active", "inactive", "all"] as const).map((s) => (
                      <button key={s} onClick={() => setStatusFilter(s)}
                        className={`rounded border px-3 py-1.5 text-xs font-medium transition ${
                          statusFilter === s ? "border-brand bg-brand text-white" : "border-line text-muted hover:border-brand hover:text-brand"
                        }`}>
                        {s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>
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
            {submitting ? "Starting…" : "Start evaluation"}
          </button>
        </div>
      </div>
    </div>
  );
}
