import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ExecuteModal } from "./ExecuteModal";
import { TopBar } from "./TopBar";
import { fmt, fmtDate } from "../lib";
import { Pager, usePaging } from "./Pager";
import type { Group, GroupRunStat } from "../types";

export default function Groups() {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [error, setError] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [importing, setImporting] = useState<string | null>(null); // group_id being imported into
  const [importErr, setImportErr] = useState("");
  const [drag, setDrag] = useState(false);
  const [dropName, setDropName] = useState("");
  const [dropFile, setDropFile] = useState<File | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [runGroupId, setRunGroupId] = useState<string | null>(null);
  const navigate = useNavigate();
  const paging = usePaging(groups ?? [], groups?.length ?? 0, 25);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = () => {
    api.groups().then(setGroups).catch((e) => setError(e.message));
  };

  useEffect(() => { load(); }, []);

  async function handleImport(groupId: string, file: File) {
    setImporting(groupId); setImportErr("");
    try {
      await api.importIntoGroup(groupId, file);
      load();
    } catch (e) {
      setImportErr((e as Error).message);
    } finally {
      setImporting(null);
    }
  }

  async function handleRename() {
    if (!renaming) return;
    try {
      await api.renameGroup(renaming.id, renaming.name);
      setRenaming(null);
      setImportErr("");
      load();
    } catch (e) {
      setImportErr((e as Error).message);
    }
  }

  async function handleDelete(groupId: string) {
    try {
      await api.deleteGroup(groupId);
      setPendingDelete(null);
      load();
    } catch (e) {
      setImportErr((e as Error).message);
    }
  }

  async function handleDropCreate() {
    if (!dropFile || !dropName.trim()) return;
    setCreating(true);
    try {
      const grp = await api.createGroup(dropName.trim());
      await api.importIntoGroup(grp.group_id, dropFile);
      setDropFile(null); setDropName("");
      load();
    } catch (e) {
      setImportErr((e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <TopBar crumbs={[{ label: "Groups" }]} />
      <div className="mx-auto max-w-[1280px] px-6 pb-16 pt-5">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h1 className="font-serif text-[32px] font-medium leading-none tracking-tight">Test Case Groups</h1>
            <p className="mono mt-2 text-xs text-muted">Label test cases so you can run any set of them together</p>
          </div>
          <button
            onClick={() => setShowNew(true)}
            className="rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:brightness-110"
          >
            + New Group
          </button>
        </div>

        {/* Info banner */}
        <div className="mb-5 rounded border border-line bg-surface-2 px-4 py-3 text-sm text-muted">
          <span className="font-medium text-fg">Groups are labels.</span> Put a label on any test cases, then run a whole
          group — or several — in one go. A test case can carry any number of labels, and you can also run hand-picked
          test cases from the Test Cases page. Click a group to see its test cases.
        </div>

        {/* Drop zone */}
        {!dropFile ? (
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault(); setDrag(false);
              const f = e.dataTransfer.files[0];
              if (f) { setDropFile(f); setDropName(f.name.replace(/\.xlsx$/i, "")); }
            }}
            onClick={() => fileInput.current?.click()}
            className={`mb-5 flex cursor-pointer flex-col items-center gap-1 rounded border-2 border-dashed p-5 text-center text-sm transition ${drag ? "border-brand bg-brand-soft" : "border-line hover:border-brand/60"}`}
          >
            <span className="font-medium">Drop an .xlsx here to create a new group</span>
            <span className="text-xs text-muted">Or click to pick a file</span>
          </div>
        ) : (
          <div className="mb-5 rounded border border-brand bg-brand-soft p-4">
            <div className="mb-2 text-sm font-medium">Create new group from: <span className="text-brand">{dropFile.name}</span></div>
            <div className="flex items-center gap-2">
              <input
                value={dropName}
                onChange={(e) => setDropName(e.target.value)}
                placeholder="Group name…"
                className="flex-1 rounded border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand"
              />
              <button
                onClick={handleDropCreate}
                disabled={creating || !dropName.trim()}
                className="rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110"
              >
                {creating ? "Creating…" : "Create & Import"}
              </button>
              <button
                onClick={() => { setDropFile(null); setDropName(""); }}
                className="rounded border border-line px-4 py-2 text-sm hover:bg-surface-2"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        <input ref={fileInput} type="file" accept=".xlsx" hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) { setDropFile(f); setDropName(f.name.replace(/\.xlsx$/i, "")); }
          }} />

        {importErr && <p className="mb-4 text-sm text-bad">{importErr}</p>}

        <div className="card overflow-hidden">
          {error && <p className="px-5 py-6 text-sm text-bad">{error}</p>}
          {!groups && !error && <p className="px-5 py-12 text-center text-muted">Loading…</p>}
          {groups?.length === 0 && (
            <div className="px-5 py-16 text-center">
              <div className="font-serif text-lg">No groups yet</div>
              <div className="mt-1 text-sm text-muted">Drop an .xlsx above or click "New Group" to create your first group.</div>
            </div>
          )}
          {groups && groups.length > 0 && (
            <p className="mb-3 px-5 pt-4 text-xs text-muted">
              {groups.length} group{groups.length !== 1 ? "s" : ""} · {groups.reduce((s, g) => s + g.member_count, 0)} total test cases
            </p>
          )}
          {groups && groups.length > 0 && (
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-3 py-3 font-medium">Test cases</th>
                  <th className="px-3 py-3 font-medium">Last run</th>
                  <th className="px-3 py-3 font-medium">Best version</th>
                  <th className="px-3 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {paging.rows.map((g) => (
                  <tr key={g.group_id} tabIndex={0}
                    className="cursor-pointer align-middle outline-none hover:bg-surface-2 focus-visible:bg-surface-2"
                    onClick={() => navigate(`/test-cases?group_id=${encodeURIComponent(g.group_id)}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && e.target === e.currentTarget) navigate(`/test-cases?group_id=${encodeURIComponent(g.group_id)}`);
                    }}>
                    <td className="px-5 py-4 font-medium" onClick={renaming?.id === g.group_id ? (e) => e.stopPropagation() : undefined}>
                      {renaming?.id === g.group_id ? (
                        <span className="flex items-center gap-2">
                          <input value={renaming.name} autoFocus
                            onChange={(e) => setRenaming({ id: g.group_id, name: e.target.value })}
                            onKeyDown={(e) => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") setRenaming(null); }}
                            className="w-56 rounded border border-line bg-surface px-2 py-1 text-sm outline-none focus:border-brand" />
                          <button onClick={handleRename} disabled={!renaming.name.trim()} className="text-xs font-medium text-brand hover:underline disabled:opacity-50">Save</button>
                          <button onClick={() => setRenaming(null)} className="text-xs text-muted hover:underline">Cancel</button>
                        </span>
                      ) : g.name}
                    </td>
                    <td className="mono px-3 py-4">
                      {g.member_count === 0
                        ? <span className="text-xs text-muted">0 cases</span>
                        : g.member_count}
                    </td>
                    <td className="px-3 py-4"><RunCell run={g.last_run ?? null} when /></td>
                    <td className="px-3 py-4"><RunCell run={g.best_run ?? null} /></td>
                    <td className="px-3 py-4" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => setRunGroupId(g.group_id)}
                          disabled={g.member_count === 0}
                          className="text-xs font-medium text-brand hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                        >Run</button>
                        <button
                          onClick={() => setRenaming({ id: g.group_id, name: g.name })}
                          className="text-xs font-medium text-muted hover:text-brand"
                        >Rename</button>
                        <label className={`cursor-pointer text-xs font-medium text-muted hover:text-brand ${importing === g.group_id ? "opacity-50" : ""}`}>
                          {importing === g.group_id ? "Importing…" : "Import .xlsx"}
                          <input
                            type="file"
                            accept=".xlsx"
                            hidden
                            disabled={importing !== null}
                            onChange={(e) => {
                              const f = e.target.files?.[0];
                              if (f) handleImport(g.group_id, f);
                              e.target.value = "";
                            }}
                          />
                        </label>
                        {pendingDelete === g.group_id ? (
                          <span className="flex items-center gap-1">
                            <span className="text-xs text-bad">Sure?</span>
                            <button
                              onClick={() => handleDelete(g.group_id)}
                              className="text-xs text-bad hover:underline"
                            >Yes</button>
                            <button
                              onClick={() => setPendingDelete(null)}
                              className="text-xs text-muted hover:underline"
                            >No</button>
                          </span>
                        ) : (
                          <button
                            onClick={() => setPendingDelete(g.group_id)}
                            className="text-xs text-bad hover:underline"
                          >Delete</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Pager p={paging} sizes={[25, 50, 100]} />
        </div>
      </div>

      {runGroupId && <ExecuteModal initial={{ mode: "groups", groupIds: [runGroupId] }} onClose={() => setRunGroupId(null)} />}
      {showNew && (
        <NewGroupModal
          onClose={() => setShowNew(false)}
          onSaved={() => { load(); setShowNew(false); }}
        />
      )}
    </>
  );
}

/** A group's run for the list: the version, and either when it ran or how well it did. */
function RunCell({ run, when = false }: { run: GroupRunStat | null; when?: boolean }) {
  if (!run) return <span className="text-xs text-muted">Not run yet</span>;
  return (
    <div>
      <span className="mono font-medium text-brand">v{run.version}</span>
      <div className="mt-0.5 text-xs text-muted">
        {when ? fmtDate(run.date) : `quality ${run.quality == null ? "—" : run.quality.toFixed(1)} · answer ${fmt(run.avg_answer_marks)}`}
      </div>
    </div>
  );
}

function NewGroupModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    if (!name.trim()) { setErr("Name is required."); return; }
    setSaving(true); setErr("");
    try {
      await api.createGroup(name.trim());
      onSaved();
    } catch (e: unknown) {
      setErr((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={onClose}>
      <div className="card pop-in w-full max-w-sm bg-surface p-6" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <h2 className="font-serif text-xl font-medium">New Group</h2>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>
        <label className="label mt-4 block">Group name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          autoFocus
          placeholder="e.g. Production v2 test set"
          className="mt-1.5 w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand"
        />
        {err && <p className="mt-2 text-xs text-bad">{err}</p>}
        <div className="mt-4 flex gap-2">
          <button onClick={save} disabled={saving || !name.trim()}
            className="rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110">
            {saving ? "Creating…" : "Create"}
          </button>
          <button onClick={onClose} className="rounded border border-line px-4 py-2 text-sm hover:bg-surface-2">Cancel</button>
        </div>
      </div>
    </div>
  );
}
