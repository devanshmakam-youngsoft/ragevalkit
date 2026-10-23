import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { AddToGroupModal } from "./AddToGroupModal";
import type { Crumb } from "./Breadcrumbs";
import { ExecuteModal } from "./ExecuteModal";
import { ChatTurn, GroupChips } from "./GroupChips";
import { GenerateDialog } from "./GenerateDialog";
import { GenerationBanner } from "./GenerationBanner";
import { GroupHistory } from "./GroupHistory";
import { ImportDialog } from "./ImportDialog";
import { Pager, usePaging } from "./Pager";
import { SectionTabs } from "./SectionTabs";
import { TopBar } from "./TopBar";
import { fmtDate, plural } from "../lib";
import type { Group, TestCase } from "../types";

type StatusFilter = "active" | "inactive" | "deleted" | "all";
type Status = "active" | "inactive" | "deleted";

/** Filter value for "cases that carry no group label". */
const NO_GROUP = "__none__";

const STATUS_COLORS: Record<string, string> = {
  active: "text-good",
  inactive: "text-muted",
  deleted: "text-bad",
};

export default function TestCases() {
  const { groupId: routeGroupId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const legacyGroup = searchParams.get("group_id") ?? searchParams.get("dataset_id");
  const groupId = routeGroupId ?? (searchParams.get("ungrouped") === "1" ? NO_GROUP : "");

  const [cases, setCases] = useState<TestCase[] | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [showNew, setShowNew] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showRun, setShowRun] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showGroupRun, setShowGroupRun] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [generate, setGenerate] = useState<{ resumeId?: string } | null>(null);
  const [bannerKey, setBannerKey] = useState(0);
  const headerBox = useRef<HTMLInputElement>(null);

  const realGroupId = groupId && groupId !== NO_GROUP ? groupId : "";

  const loadGroups = () => { api.groups().then(setGroups).catch(() => undefined); };
  const load = () => {
    api.testCases(realGroupId || undefined, statusFilter === "all" ? undefined : statusFilter)
      .then((rows) => { setCases(statusFilter === "all" ? rows.filter((r) => r.status !== "deleted") : rows); setError(""); })
      .catch((e) => setError(e.message));
  };

  useEffect(loadGroups, []);
  useEffect(() => { setCases(null); load(); }, [groupId, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  // A short confirmation line that clears itself.
  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(t);
  }, [notice]);

  const setGroupFilter = (value: string) => {
    navigate(value === NO_GROUP ? "/test-cases?ungrouped=1" : value ? `/test-cases/groups/${encodeURIComponent(value)}` : "/test-cases");
    setChecked(new Set());
  };

  const filtered = useMemo(() => {
    let rows = cases ?? [];
    if (groupId === NO_GROUP) rows = rows.filter((c) => c.groups.length === 0);
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((c) =>
      c.question.toLowerCase().includes(q) ||
      c.expected_answer.toLowerCase().includes(q) ||
      c.chat_id.toLowerCase().includes(q) ||
      c.groups.some((g) => g.name.toLowerCase().includes(q)));
  }, [cases, query, groupId]);

  const paging = usePaging(filtered, `${groupId}|${statusFilter}|${query}`, 50);
  const countText = statusFilter === "all"
    ? `Active ${filtered.filter((c) => c.status === "active").length} · Inactive ${filtered.filter((c) => c.status === "inactive").length}`
    : `${statusFilter[0].toUpperCase()}${statusFilter.slice(1)} · ${plural(filtered.length, "case")}`;
  const inTrash = statusFilter === "deleted";
  const open = cases?.find((c) => c.tc_id === openId) ?? null;
  const allShownChecked = paging.rows.length > 0 && paging.rows.every((c) => checked.has(c.tc_id));
  const someShownChecked = paging.rows.some((c) => checked.has(c.tc_id));
  const hiddenChecked = [...checked].filter((id) => !filtered.some((c) => c.tc_id === id)).length;

  useEffect(() => {
    if (headerBox.current) headerBox.current.indeterminate = someShownChecked && !allShownChecked;
  }, [someShownChecked, allShownChecked]);

  const toggleOne = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  const toggleAllShown = () =>
    setChecked((prev) => {
      const next = new Set(prev);
      paging.rows.forEach((c) => (allShownChecked ? next.delete(c.tc_id) : next.add(c.tc_id)));
      return next;
    });
  const selectAllMatching = () => setChecked(new Set(filtered.map((c) => c.tc_id)));

  const ids = [...checked];

  async function bulkStatus(status: Status) {
    try {
      const { updated } = await api.updateTestCaseStatus(ids, status);
      const what = plural(updated, "test case");
      setNotice(
        status === "deleted" ? `${what} deleted — find ${updated === 1 ? "it" : "them"} under the Deleted filter`
          : statusFilter === "deleted" ? `${what} restored` : `${what} marked ${status}`
      );
      setChecked(new Set());
      load();
    } catch (e) { setError((e as Error).message); }
  }

  async function bulkPurge() {
    try {
      const { purged } = await api.purgeTestCases(ids);
      setNotice(`${plural(purged, "test case")} permanently deleted`);
      setChecked(new Set());
      setConfirmDelete(false);
      load(); loadGroups();
    } catch (e) { setError((e as Error).message); setConfirmDelete(false); }
  }

  async function bulkRemoveFromGroup() {
    try {
      const { removed } = await api.removeFromGroup(realGroupId, ids);
      const name = groups.find((g) => g.group_id === realGroupId)?.name ?? "the group";
      setNotice(`${removed} test case${removed !== 1 ? "s" : ""} removed from "${name}"`);
      setChecked(new Set());
      load(); loadGroups();
    } catch (e) { setError((e as Error).message); }
  }

  // Dashboard > Test Cases, or Dashboard > Test Cases > Groups > <group> on a group's page.
  const groupName = groups.find((g) => g.group_id === realGroupId)?.name;
  const crumbs: Crumb[] = realGroupId
    ? [{ label: "Test Cases", to: "/test-cases" }, { label: "Groups", to: "/test-cases/groups" }, { label: groupName ?? "Group" }]
    : [{ label: "Test Cases" }];

  // links from before groups moved under Test Cases
  if (legacyGroup && !routeGroupId) return <Navigate to={`/test-cases/groups/${encodeURIComponent(legacyGroup)}`} replace />;

  return (
    <>
      <TopBar crumbs={crumbs} />
      <div className="mx-auto max-w-[1280px] px-6 pb-16 pt-5">
        <div className="mb-4 flex flex-wrap items-end gap-4">
          <div>
            <h1 className="font-serif text-[32px] font-medium leading-none tracking-tight">{realGroupId ? (groupName ?? "Group") : "Test Cases"}</h1>
            <p className="mono mt-2 text-xs text-muted">
              {realGroupId ? "A group of test cases: run it, or change who is in it" : "Questions and expected answers tracked across eval runs"}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={() => setGenerate({})}
              className="rounded border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-2">
              Generate from documents
            </button>
            <button onClick={() => setShowImport(true)}
              className="rounded border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-2">
              Import
            </button>
            <button
              onClick={() => setShowNew(true)}
              className="rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:brightness-110"
            >
              + New test case
            </button>
          </div>
        </div>

        <SectionTabs active={realGroupId ? "groups" : "all"} />

        <GenerationBanner refreshKey={bannerKey} onOpen={(id) => setGenerate({ resumeId: id })} />

        {realGroupId && <GroupHistory groupId={realGroupId} onRun={() => setShowGroupRun(true)} />}

        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select
            value={groupId}
            onChange={(e) => setGroupFilter(e.target.value)}
            aria-label="Filter by group"
            className="rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none"
          >
            <option value="">All groups</option>
            <option value={NO_GROUP}>No group</option>
            {groups.map((g) => (
              <option key={g.group_id} value={g.group_id}>{g.name}</option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value as StatusFilter); setChecked(new Set()); }}
            aria-label="Filter by status"
            className="rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none"
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="deleted">Deleted</option>
            <option value="all">Active + inactive</option>
          </select>

          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search questions, chats, groups…"
            className="w-72 rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand"
          />

          <span className="mono text-xs text-muted">{countText}</span>
        </div>

        {/* Bulk actions — appear once something is ticked */}
        {checked.size > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2 rounded border border-brand bg-brand-soft px-4 py-2.5 text-sm">
            <span className="font-medium">
              {checked.size} selected{hiddenChecked > 0 && <span className="font-normal text-muted"> ({hiddenChecked} hidden by search)</span>}
            </span>
            <span className="mx-1 h-4 w-px bg-line" />
            {!inTrash && <>
            <button onClick={() => setShowRun(true)}
              className="rounded bg-brand px-3 py-1 text-xs font-semibold text-white hover:brightness-110">
              Run {checked.size}…
            </button>
            <button onClick={() => setShowAdd(true)} className="rounded border border-line bg-surface px-3 py-1 text-xs font-medium hover:bg-surface-2">
              Add to group…
            </button>
            {realGroupId && (
              <button onClick={bulkRemoveFromGroup} className="rounded border border-line bg-surface px-3 py-1 text-xs font-medium hover:bg-surface-2">
                Remove from "{groupName}"
              </button>
            )}
            </>}
            {statusFilter !== "active" && (
              <button onClick={() => bulkStatus("active")} className="rounded border border-line bg-surface px-3 py-1 text-xs font-medium hover:border-good hover:text-good">{inTrash ? "Restore" : "Activate"}</button>
            )}
            {statusFilter !== "inactive" && !inTrash && (
              <button onClick={() => bulkStatus("inactive")} className="rounded border border-line bg-surface px-3 py-1 text-xs font-medium hover:bg-surface-2">Deactivate</button>
            )}
            {!inTrash ? (
              <button onClick={() => bulkStatus("deleted")} className="rounded border border-line bg-surface px-3 py-1 text-xs font-medium hover:border-bad hover:text-bad">Delete</button>
            ) : confirmDelete ? (
              <span className="flex items-center gap-2 text-xs">
                <span className="text-bad">Delete {checked.size} forever? This can't be undone.</span>
                <button onClick={bulkPurge} className="rounded bg-bad px-3 py-1 font-semibold text-white hover:brightness-110">Delete forever</button>
                <button onClick={() => setConfirmDelete(false)} className="text-muted hover:text-fg">Cancel</button>
              </span>
            ) : (
              <button onClick={() => setConfirmDelete(true)} className="rounded border border-line bg-surface px-3 py-1 text-xs font-medium hover:border-bad hover:text-bad">Delete forever…</button>
            )}
            {allShownChecked && filtered.length > paging.rows.length && checked.size < filtered.length && (
              <button onClick={selectAllMatching} className="text-xs text-brand hover:underline">Select all {filtered.length} matching</button>
            )}
            <button onClick={() => { setChecked(new Set()); setConfirmDelete(false); }} className="ml-auto text-xs text-muted hover:text-fg">Clear</button>
          </div>
        )}
        {notice && <p className="mb-3 text-sm text-good" role="status">{notice}</p>}
        {error && <p className="mb-4 text-sm text-bad">{error}</p>}

        <div className="card overflow-hidden">
          {!cases && !error && <p className="px-5 py-12 text-center text-muted">Loading…</p>}
          {cases && filtered.length === 0 && (
            <div className="px-5 py-16 text-center">
              <div className="font-serif text-lg">No test cases found</div>
              <div className="mt-1 text-sm text-muted">
                {cases.length === 0 && !realGroupId && statusFilter === "active"
                  ? "Add one with “New test case”, bring many in with Import, or write them from a document with “Generate from documents”."
                  : "Nothing matches the current filters."}
              </div>
            </div>
          )}
          {filtered.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
                  <tr>
                    <th className="w-10 py-3 pl-5 pr-2">
                      <input ref={headerBox} type="checkbox" checked={allShownChecked} onChange={toggleAllShown}
                        aria-label="Select all shown" className="accent-brand" />
                    </th>
                    <th className="px-3 py-3 font-medium">Chat</th>
                    <th className="px-3 py-3 font-medium">Turn</th>
                    <th className="px-3 py-3 font-medium">Question</th>
                    <th className="px-3 py-3 font-medium">Groups</th>
                    <th className="px-3 py-3 font-medium">Type</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="px-3 py-3 font-medium">v</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {paging.rows.map((tc) => (
                    <tr key={tc.tc_id} tabIndex={0}
                      className={`cursor-pointer align-top outline-none hover:bg-surface-2 focus-visible:bg-surface-2 ${checked.has(tc.tc_id) ? "bg-brand-soft" : ""}`}
                      onClick={() => setOpenId(tc.tc_id)}
                      onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) setOpenId(tc.tc_id); }}>
                      <td className="py-3.5 pl-5 pr-2" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={checked.has(tc.tc_id)} onChange={() => toggleOne(tc.tc_id)}
                          aria-label={`Select chat ${tc.chat_id} turn ${tc.turn_no}`} className="accent-brand" />
                      </td>
                      <td className="mono max-w-[140px] truncate px-3 py-3.5 text-xs" title={tc.chat_id}>{tc.chat_id}</td>
                      <td className="mono px-3 py-3.5 text-xs text-muted">{tc.turn_no}</td>
                      <td className="max-w-[380px] px-3 py-3.5">
                        <div className="line-clamp-2 font-medium">{tc.question}</div>
                        <div className="mt-1 line-clamp-1 text-xs text-muted">{tc.expected_answer}</div>
                      </td>
                      <td className="px-3 py-3.5"><GroupChips groups={tc.groups} /></td>
                      <td className="px-3 py-3.5">
                        <span className="mono text-[11px] text-muted">{tc.type}</span>
                      </td>
                      <td className="px-3 py-3.5">
                        <span className={`mono text-[11px] font-medium ${STATUS_COLORS[tc.status] ?? "text-muted"}`}>
                          {tc.status}
                        </span>
                      </td>
                      <td className="mono px-3 py-3.5 text-xs text-muted">v{tc.version}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager p={paging} sizes={[25, 50, 100, 200]} />
        </div>

        {open && (
          <TestCaseDrawer
            tc={open}
            groups={groups}
            onClose={() => setOpenId(null)}
            onChanged={(message) => { if (message) setNotice(message); load(); loadGroups(); }}
            onDeleted={() => { setOpenId(null); setNotice("Test case permanently deleted"); load(); loadGroups(); }}
          />
        )}
        {showNew && (
          <NewTestCaseModal
            groups={groups}
            defaultGroupId={realGroupId}
            onClose={() => setShowNew(false)}
            onSaved={() => { load(); loadGroups(); setShowNew(false); }}
          />
        )}
        {showAdd && (
          <AddToGroupModal
            groups={groups}
            tcIds={ids}
            onClose={() => setShowAdd(false)}
            onDone={(message) => { setShowAdd(false); setNotice(message); setChecked(new Set()); load(); loadGroups(); }}
          />
        )}
        {generate && (
          <GenerateDialog
            resumeId={generate.resumeId}
            onClose={() => { setGenerate(null); setBannerKey((k) => k + 1); load(); loadGroups(); }}
            onDone={(message) => { setGenerate(null); setBannerKey((k) => k + 1); setNotice(message); load(); loadGroups(); }}
          />
        )}
        {showImport && (
          <ImportDialog
            groups={groups}
            initialGroupId={realGroupId || undefined}
            onClose={() => setShowImport(false)}
            onDone={(message) => { setShowImport(false); setNotice(message); load(); loadGroups(); }}
          />
        )}
        {showRun && <ExecuteModal initial={{ mode: "cases", tcIds: ids }} onClose={() => setShowRun(false)} />}
        {showGroupRun && <ExecuteModal initial={{ mode: "groups", groupIds: [realGroupId] }} onClose={() => setShowGroupRun(false)} />}
      </div>
    </>
  );
}

function TestCaseDrawer({ tc, groups, onClose, onChanged, onDeleted }: {
  tc: TestCase;
  groups: Group[];
  onClose: () => void;
  onChanged: (message?: string) => void;
  onDeleted: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const initialForm = () => ({
    chat_id: tc.chat_id,
    turn_no: String(tc.turn_no),
    question: tc.question,
    expected_answer: tc.expected_answer,
    expected_sources: tc.expected_sources ?? "",
    type: tc.type,
  });
  const [history, setHistory] = useState<TestCase[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.testCaseHistory(tc.tc_id).then(setHistory).catch(() => undefined);
    setForm(initialForm());
    setEditing(false);
    setErr("");
  }, [tc.tc_id, tc.version]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async () => {
    const turn = Number(form.turn_no);
    if (!form.chat_id.trim()) { setErr("Chat ID is required."); return; }
    if (!Number.isInteger(turn) || turn < 1) { setErr("Turn must be a whole number, 1 or higher."); return; }
    if (!form.question.trim()) { setErr("Question is required."); return; }
    setSaving(true);
    setErr("");
    try {
      const updates: Parameters<typeof api.editTestCase>[1] = {};
      if (form.chat_id.trim() !== tc.chat_id) updates.chat_id = form.chat_id.trim();
      if (turn !== tc.turn_no) updates.turn_no = turn;
      if (form.question !== tc.question) updates.question = form.question;
      if (form.expected_answer !== tc.expected_answer) updates.expected_answer = form.expected_answer;
      if (form.expected_sources !== (tc.expected_sources ?? "")) updates.expected_sources = form.expected_sources;
      if (form.type !== tc.type) updates.type = form.type;
      if (Object.keys(updates).length === 0) { setEditing(false); return; }
      await api.editTestCase(tc.tc_id, updates);
      onChanged("Saved as a new version");
    } catch (e: unknown) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (status: Status) => {
    try {
      await api.updateTestCaseStatus([tc.tc_id], status);
      onChanged(
        status === "deleted" ? "Test case deleted — find it under the Deleted filter"
          : tc.status === "deleted" ? "Test case restored" : `Test case marked ${status}`
      );
    } catch (e: unknown) {
      setErr((e as Error).message);
    }
  };

  const remove = async () => {
    try {
      await api.purgeTestCases([tc.tc_id]);
      onDeleted();
    } catch (e: unknown) {
      setErr((e as Error).message);
      setConfirmDelete(false);
    }
  };

  const setLabels = async (groupIds: string[]) => {
    try {
      await api.setTestCaseGroups(tc.tc_id, groupIds);
      onChanged();
    } catch (e: unknown) {
      setErr((e as Error).message);
    }
  };

  const labelIds = tc.groups.map((g) => g.group_id);
  const addable = groups.filter((g) => !labelIds.includes(g.group_id));
  const input = "w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand";

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={onClose}>
      <aside
        className="slide-in h-full w-full max-w-[580px] overflow-y-auto border-l border-line bg-surface p-6"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <ChatTurn chatId={tc.chat_id} turnNo={tc.turn_no} />
            <div className="mono mt-2 text-[11px] text-muted">
              {tc.tc_id} · v{tc.version} · <span className={STATUS_COLORS[tc.status]}>{tc.status}</span>
            </div>
          </div>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        {editing ? (
          <div className="mt-5 space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <Field label="Chat ID">
                  <input value={form.chat_id} onChange={(e) => setForm((f) => ({ ...f, chat_id: e.target.value }))} className={input} />
                </Field>
              </div>
              <div className="w-24">
                <Field label="Turn #">
                  <input value={form.turn_no} type="number" min={1} step={1}
                    onChange={(e) => setForm((f) => ({ ...f, turn_no: e.target.value }))} className={input} />
                </Field>
              </div>
              <div className="w-28">
                <Field label="Type">
                  <input value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))} className={input} />
                </Field>
              </div>
            </div>
            <Field label="Question">
              <textarea value={form.question} rows={3}
                onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))}
                className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand" />
            </Field>
            <Field label="Expected answer">
              <textarea value={form.expected_answer} rows={4}
                onChange={(e) => setForm((f) => ({ ...f, expected_answer: e.target.value }))}
                className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand" />
            </Field>
            <Field label="Expected sources (| = AND, , = OR)">
              <input value={form.expected_sources} placeholder="doc_a.pdf|doc_b.pdf"
                onChange={(e) => setForm((f) => ({ ...f, expected_sources: e.target.value }))} className={input} />
            </Field>
            {err && <p className="text-xs text-bad">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button onClick={save} disabled={saving}
                className="rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110">
                {saving ? "Saving…" : "Save new version"}
              </button>
              <button onClick={() => { setEditing(false); setForm(initialForm()); setErr(""); }}
                className="rounded border border-line px-4 py-2 text-sm hover:bg-surface-2">
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-5 space-y-4">
            <ReadField label="Question">{tc.question}</ReadField>
            <ReadField label="Expected answer">{tc.expected_answer}</ReadField>
            {tc.expected_sources && <ReadField label="Expected sources">{tc.expected_sources}</ReadField>}
            {tc.origin?.kind === "generated" && (
              <div>
                <div className="label mb-1">Written from your document</div>
                <div className="space-y-2 rounded bg-surface-2 p-3 text-sm">
                  {tc.origin.evidence.map((e, i) => (
                    <blockquote key={i} className="border-l-2 border-line pl-3 italic text-muted">
                      “{e.quote}” <span className="not-italic">— {e.file}, {e.page}</span>
                    </blockquote>
                  ))}
                </div>
              </div>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              <button onClick={() => setEditing(true)}
                className="rounded border border-line px-4 py-2 text-sm font-medium hover:bg-surface-2">
                Edit
              </button>
              {tc.status !== "active" && (
                <button onClick={() => setStatus("active")} className="rounded border border-line px-4 py-2 text-sm hover:border-good hover:text-good">{tc.status === "deleted" ? "Restore" : "Activate"}</button>
              )}
              {tc.status === "active" && (
                <button onClick={() => setStatus("inactive")} className="rounded border border-line px-4 py-2 text-sm hover:bg-surface-2">Deactivate</button>
              )}
              {tc.status !== "deleted" ? (
                <button onClick={() => setStatus("deleted")} className="rounded border border-line px-4 py-2 text-sm hover:border-bad hover:text-bad">Delete</button>
              ) : confirmDelete ? (
                <span className="flex items-center gap-2 text-sm">
                  <span className="text-bad">Delete forever? This can't be undone.</span>
                  <button onClick={remove} className="rounded bg-bad px-3 py-2 text-sm font-semibold text-white hover:brightness-110">Delete forever</button>
                  <button onClick={() => setConfirmDelete(false)} className="text-muted hover:text-fg">Cancel</button>
                </span>
              ) : (
                <button onClick={() => setConfirmDelete(true)} className="rounded border border-line px-4 py-2 text-sm hover:border-bad hover:text-bad">Delete forever…</button>
              )}
            </div>
            {err && <p className="text-xs text-bad">{err}</p>}
          </div>
        )}

        {/* Group labels: edited in place, no save step */}
        <div className="mt-6">
          <div className="label mb-2">Groups</div>
          <div className="flex flex-wrap items-center gap-2">
            {tc.groups.map((g) => (
              <span key={g.group_id} className="inline-flex items-center gap-1 rounded bg-brand-soft px-2 py-1 text-xs font-medium">
                {g.name}
                <button onClick={() => setLabels(labelIds.filter((id) => id !== g.group_id))}
                  aria-label={`Remove from ${g.name}`} className="text-muted hover:text-bad">×</button>
              </span>
            ))}
            {tc.groups.length === 0 && <span className="text-xs text-muted">Not in any group.</span>}
            {addable.length > 0 && (
              <select value="" onChange={(e) => e.target.value && setLabels([...labelIds, e.target.value])}
                aria-label="Add to group"
                className="rounded border border-line bg-surface-2 px-2 py-1 text-xs outline-none">
                <option value="">+ Add to group…</option>
                {addable.map((g) => <option key={g.group_id} value={g.group_id}>{g.name}</option>)}
              </select>
            )}
          </div>
        </div>

        {history && history.length > 1 && (
          <div className="mt-8">
            <div className="label mb-3">Version history</div>
            <div className="space-y-2">
              {[...history].reverse().map((h) => (
                <div key={h.version} className={`rounded border p-3 text-xs ${h.version === tc.version ? "border-brand" : "border-line"}`}>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="mono font-medium">v{h.version} <span className="font-normal text-muted">· chat {h.chat_id} · turn {h.turn_no}</span></span>
                    <span className="text-muted">{fmtDate(h.updated_at ?? h.created_at)}</span>
                  </div>
                  <div className="line-clamp-2 text-muted">{h.question}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-muted">{label}</div>
      {children}
    </div>
  );
}

function ReadField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="label mb-1">{label}</div>
      <div className="whitespace-pre-wrap rounded bg-surface-2 p-3 text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function NewTestCaseModal({
  groups, defaultGroupId, onClose, onSaved
}: { groups: Group[]; defaultGroupId: string; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    group_id: defaultGroupId,
    chat_id: "",
    turn_no: "1",
    type: "rag",
    question: "",
    expected_answer: "",
    expected_sources: "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async () => {
    if (!form.chat_id.trim() || !form.question.trim() || !form.expected_answer.trim()) {
      setErr("Chat ID, question, and expected answer are required.");
      return;
    }
    const turn = Number(form.turn_no);
    if (!Number.isInteger(turn) || turn < 1) {
      setErr("Turn must be a whole number, 1 or higher.");
      return;
    }
    setSaving(true); setErr("");
    try {
      await api.createTestCase({
        group_id: form.group_id || undefined,
        chat_id: form.chat_id.trim(),
        turn_no: turn,
        type: form.type || "rag",
        question: form.question.trim(),
        expected_answer: form.expected_answer.trim(),
        expected_sources: form.expected_sources.trim(),
      });
      onSaved();
    } catch (e: unknown) {
      setErr((e as Error).message);
      setSaving(false);
    }
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={onClose}>
      <div className="card pop-in w-full max-w-lg bg-surface p-6" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <h2 className="font-serif text-2xl font-medium">New test case</h2>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>
        <div className="mt-5 space-y-4">
          <Field label="Group (optional)">
            <select value={form.group_id} onChange={set("group_id")}
              className="w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand">
              <option value="">None</option>
              {groups.map((g) => <option key={g.group_id} value={g.group_id}>{g.name}</option>)}
            </select>
          </Field>
          <div className="flex gap-3">
            <div className="flex-1">
              <Field label="Chat ID">
                <input value={form.chat_id} onChange={set("chat_id")} placeholder="e.g. chat_001"
                  className="w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
              </Field>
            </div>
            <div className="w-24">
              <Field label="Turn #">
                <input value={form.turn_no} onChange={set("turn_no")} type="number" min={1} step={1}
                  className="w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
              </Field>
            </div>
            <div className="w-28">
              <Field label="Type">
                <input value={form.type} onChange={set("type")} placeholder="rag"
                  className="w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
              </Field>
            </div>
          </div>
          <Field label="Question">
            <textarea value={form.question} onChange={set("question")} rows={3}
              className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand" />
          </Field>
          <Field label="Expected answer">
            <textarea value={form.expected_answer} onChange={set("expected_answer")} rows={3}
              className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand" />
          </Field>
          <Field label="Expected sources (optional; | = AND, , = OR)">
            <input value={form.expected_sources} onChange={set("expected_sources")} placeholder="doc_a.pdf|doc_b.pdf"
              className="w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
          </Field>
          {err && <p className="text-xs text-bad">{err}</p>}
          <div className="flex gap-2 pt-1">
            <button onClick={save} disabled={saving}
              className="rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110">
              {saving ? "Saving…" : "Create test case"}
            </button>
            <button onClick={onClose} className="rounded border border-line px-4 py-2 text-sm hover:bg-surface-2">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  );
}
