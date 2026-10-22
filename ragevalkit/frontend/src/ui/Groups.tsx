import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ExecuteModal } from "./ExecuteModal";
import { ImportDialog } from "./ImportDialog";
import { SectionTabs } from "./SectionTabs";
import { TopBar } from "./TopBar";
import { fmt, fmtDate } from "../lib";
import { Pager, usePaging } from "./Pager";
import type { Group, GroupRunStat } from "../types";

export default function Groups() {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [error, setError] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [importErr, setImportErr] = useState("");
  const [notice, setNotice] = useState("");
  const [importFor, setImportFor] = useState<{ groupId?: string } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [deletedGroups, setDeletedGroups] = useState<Group[]>([]);
  const [showDeleted, setShowDeleted] = useState(false);
  const [pendingPurge, setPendingPurge] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [runGroupId, setRunGroupId] = useState<string | null>(null);
  const navigate = useNavigate();
  const paging = usePaging(groups ?? [], groups?.length ?? 0, 25);

  const load = () => {
    api.groups().then(setGroups).catch((e) => setError(e.message));
    api.groups(true).then((all) => setDeletedGroups(all.filter((g) => g.deleted_at))).catch(() => undefined);
  };

  useEffect(() => { load(); }, []);

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

  async function handleRestore(groupId: string) {
    try {
      await api.restoreGroup(groupId);
      setImportErr("");
      load();
    } catch (e) {
      setImportErr((e as Error).message);
    }
  }

  async function handlePurge(groupId: string) {
    try {
      await api.purgeGroup(groupId);
      setPendingPurge(null);
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

  return (
    <>
      <TopBar crumbs={[{ label: "Test Cases", to: "/test-cases" }, { label: "Groups" }]} />
      <div className="mx-auto max-w-[1280px] px-6 pb-16 pt-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-serif text-[32px] font-medium leading-none tracking-tight">Test Cases</h1>
            <p className="mono mt-2 text-xs text-muted">Questions and expected answers tracked across eval runs</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setImportFor({})}
              className="rounded border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-2">
              Import
            </button>
            <button
              onClick={() => setShowNew(true)}
              className="rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:brightness-110"
            >
              + New group
            </button>
          </div>
        </div>

        <SectionTabs active="groups" />

        <div className="mb-5 rounded border border-line bg-surface-2 px-4 py-3 text-sm text-muted">
          <span className="font-medium text-fg">Groups are labels.</span> Put a label on any test cases, then run a whole
          group — or several — in one go. A test case can carry any number of labels, and you can also run hand-picked
          test cases from the All test cases tab. Click a group to see its test cases and how it has done.
        </div>

        {notice && <p className="mb-3 text-sm text-good" role="status">{notice}</p>}
        {importErr && <p className="mb-4 text-sm text-bad">{importErr}</p>}

        <div className="card overflow-hidden">
          {error && <p className="px-5 py-6 text-sm text-bad">{error}</p>}
          {!groups && !error && <p className="px-5 py-12 text-center text-muted">Loading…</p>}
          {groups?.length === 0 && (
            <div className="px-5 py-16 text-center">
              <div className="font-serif text-lg">No groups yet</div>
              <div className="mt-1 text-sm text-muted">Click "New group", or use Import to bring in test cases and create groups from a file.</div>
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
                    onClick={() => navigate(`/test-cases/groups/${encodeURIComponent(g.group_id)}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && e.target === e.currentTarget) navigate(`/test-cases/groups/${encodeURIComponent(g.group_id)}`);
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
                        <button
                          onClick={() => setImportFor({ groupId: g.group_id })}
                          className="text-xs font-medium text-muted hover:text-brand"
                        >Import into…</button>
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

      {deletedGroups.length > 0 && (
        <section className="mx-auto max-w-[1280px] px-6 pb-16">
          <button onClick={() => setShowDeleted((s) => !s)} className="mb-2 flex items-center gap-2 text-sm text-muted hover:text-fg">
            <span>{showDeleted ? "▼" : "▶"}</span>
            <span>Deleted groups ({deletedGroups.length})</span>
          </button>
          {showDeleted && (
            <div className="card divide-y divide-line overflow-hidden">
              <p className="px-5 py-3 text-xs text-muted">
                Deleted groups are hidden but kept, so past versions that used them still read correctly. Restore one to use it again.
              </p>
              {deletedGroups.map((g) => (
                <div key={g.group_id} className="flex flex-wrap items-center gap-4 px-5 py-3.5">
                  <span className="font-medium">{g.name}</span>
                  <span className="mono text-xs text-muted">{g.member_count} {g.member_count === 1 ? "case" : "cases"}</span>
                  <span className="ml-auto flex items-center gap-4 text-xs">
                    <button onClick={() => handleRestore(g.group_id)} className="font-medium text-brand hover:underline">Restore</button>
                    {pendingPurge === g.group_id ? (
                      <span className="flex items-center gap-2">
                        <span className="text-bad">Delete forever?</span>
                        <button onClick={() => handlePurge(g.group_id)} className="text-bad hover:underline">Yes</button>
                        <button onClick={() => setPendingPurge(null)} className="text-muted hover:underline">No</button>
                      </span>
                    ) : (
                      <button onClick={() => setPendingPurge(g.group_id)} className="text-bad hover:underline">Delete forever…</button>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {importFor && (
        <ImportDialog
          groups={groups ?? []}
          initialGroupId={importFor.groupId}
          onClose={() => setImportFor(null)}
          onDone={(message) => { setImportFor(null); setNotice(message); load(); }}
        />
      )}
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
        {when ? fmtDate(run.date) : `overall ${run.quality == null ? "—" : run.quality.toFixed(1)} · answer ${fmt(run.avg_answer_marks)}`}
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
