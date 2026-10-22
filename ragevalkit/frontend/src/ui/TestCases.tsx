import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { Crumb } from "./Breadcrumbs";
import { TopBar } from "./TopBar";
import { fmtDate } from "../lib";
import type { Group, TestCase } from "../types";

type StatusFilter = "active" | "inactive" | "deleted" | "all";

const STATUS_COLORS: Record<string, string> = {
  active: "text-good",
  inactive: "text-muted",
  deleted: "text-bad",
};

export default function TestCases() {
  const [searchParams] = useSearchParams();
  const initGroupId = searchParams.get("group_id") ?? searchParams.get("dataset_id") ?? "";

  const [cases, setCases] = useState<TestCase[] | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupId, setGroupId] = useState(initGroupId);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<TestCase | null>(null);
  const [showNew, setShowNew] = useState(false);

  const load = () => {
    setCases(null);
    api.testCases(groupId || undefined, statusFilter === "all" ? undefined : statusFilter)
      .then(setCases)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    api.groups().then(setGroups).catch(() => undefined);
  }, []);

  useEffect(() => { load(); }, [groupId, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    if (!cases) return [];
    if (!query.trim()) return cases;
    const q = query.toLowerCase();
    return cases.filter((c) =>
      c.question.toLowerCase().includes(q) ||
      c.expected_answer.toLowerCase().includes(q) ||
      c.chat_id.toLowerCase().includes(q)
    );
  }, [cases, query]);

  // Home > Test Cases, or Home > Groups > <group> while a group is selected in the filter.
  const groupName = groups.find((g) => g.group_id === groupId)?.name;
  const crumbs: Crumb[] = groupId
    ? [{ label: "Groups", to: "/groups" }, { label: groupName ?? "Group" }]
    : [{ label: "Test Cases" }];

  const handleStatus = async (tc: TestCase, status: "active" | "inactive" | "deleted") => {
    try {
      await api.updateTestCaseStatus(tc.tc_id, status);
      load();
      if (selected?.tc_id === tc.tc_id) setSelected(null);
    } catch (e: unknown) {
      alert((e as Error).message);
    }
  };

  return (
    <>
      <TopBar crumbs={crumbs} />
      <div className="mx-auto max-w-[1280px] px-6 pb-16 pt-5">
        <div className="mb-6 flex flex-wrap items-end gap-4">
          <div>
            <h1 className="font-serif text-[32px] font-medium leading-none tracking-tight">Test Cases</h1>
            <p className="mono mt-2 text-xs text-muted">Questions and expected answers tracked across eval runs</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setShowNew(true)}
              className="rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:brightness-110"
            >
              + New test case
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
            className="rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none"
          >
            <option value="">All groups</option>
            {groups.map((g) => (
              <option key={g.group_id} value={g.group_id}>{g.name}</option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none"
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="deleted">Deleted</option>
            <option value="all">All statuses</option>
          </select>

          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search questions…"
            className="w-60 rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand"
          />

          <span className="mono text-xs text-muted">{filtered.length} case{filtered.length !== 1 ? "s" : ""}</span>
        </div>
        {!groupId && cases && (
          <p className="mb-3 text-xs text-muted">Showing all {cases.length} test cases</p>
        )}

        {error && <p className="mb-4 text-sm text-bad">{error}</p>}

        <div className="card overflow-hidden">
          {!cases && !error && <p className="px-5 py-12 text-center text-muted">Loading…</p>}
          {cases?.length === 0 && (
            <div className="px-5 py-16 text-center">
              <div className="font-serif text-lg">No test cases found</div>
              <div className="mt-1 text-sm text-muted">Run an eval to import test cases from your dataset.</div>
            </div>
          )}
          {filtered.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px] text-left text-sm">
                <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
                  <tr>
                    <th className="px-5 py-3 font-medium">Chat · Turn</th>
                    <th className="px-3 py-3 font-medium">Question</th>
                    <th className="px-3 py-3 font-medium">Type</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="px-3 py-3 font-medium">v</th>
                    <th className="px-3 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {filtered.map((tc) => (
                    <tr key={tc.tc_id} className="cursor-pointer align-top hover:bg-surface-2" onClick={() => setSelected(tc)}>
                      <td className="mono px-5 py-3.5 text-xs text-muted">{tc.chat_id}.{tc.turn_no}</td>
                      <td className="max-w-[360px] px-3 py-3.5">
                        <div className="line-clamp-2 cursor-pointer font-medium text-brand hover:underline">{tc.question}</div>
                        <div className="mt-1 line-clamp-1 text-xs text-muted">{tc.expected_answer}</div>
                      </td>
                      <td className="px-3 py-3.5">
                        <span className="mono text-[11px] text-muted">{tc.type}</span>
                      </td>
                      <td className="px-3 py-3.5">
                        <span className={`mono text-[11px] font-medium ${STATUS_COLORS[tc.status] ?? "text-muted"}`}>
                          {tc.status}
                        </span>
                      </td>
                      <td className="mono px-3 py-3.5 text-xs text-muted">v{tc.version}</td>
                      <td className="px-3 py-3.5" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-2">
                          {tc.status !== "active" && (
                            <button onClick={() => handleStatus(tc, "active")}
                              className="rounded border border-line px-2 py-0.5 text-[11px] hover:border-good hover:text-good">
                              Activate
                            </button>
                          )}
                          {tc.status === "active" && (
                            <button onClick={() => handleStatus(tc, "inactive")}
                              className="rounded border border-line px-2 py-0.5 text-[11px] hover:border-muted">
                              Deactivate
                            </button>
                          )}
                          {tc.status !== "deleted" && (
                            <button onClick={() => handleStatus(tc, "deleted")}
                              className="rounded border border-line px-2 py-0.5 text-[11px] hover:border-bad hover:text-bad">
                              Delete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {selected && (
          <TestCaseDrawer
            tc={selected}
            onClose={() => setSelected(null)}
            onSaved={() => { load(); setSelected(null); }}
          />
        )}
        {showNew && (
          <NewTestCaseModal
            groups={groups}
            defaultGroupId={groupId || (groups[0]?.group_id ?? "")}
            onClose={() => setShowNew(false)}
            onSaved={() => { load(); setShowNew(false); }}
          />
        )}
      </div>
    </>
  );
}

function TestCaseDrawer({ tc, onClose, onSaved }: { tc: TestCase; onClose: () => void; onSaved: () => void }) {
  const [history, setHistory] = useState<TestCase[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ question: tc.question, expected_answer: tc.expected_answer, expected_sources: tc.expected_sources ?? "", type: tc.type });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.testCaseHistory(tc.tc_id).then(setHistory).catch(() => undefined);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tc.tc_id, onClose]);

  const save = async () => {
    setSaving(true);
    setErr("");
    try {
      const updates: Record<string, string> = {};
      if (form.question !== tc.question) updates.question = form.question;
      if (form.expected_answer !== tc.expected_answer) updates.expected_answer = form.expected_answer;
      if (form.expected_sources !== (tc.expected_sources ?? "")) updates.expected_sources = form.expected_sources;
      if (form.type !== tc.type) updates.type = form.type;
      if (Object.keys(updates).length === 0) { setEditing(false); return; }
      await api.editTestCase(tc.tc_id, updates);
      onSaved();
    } catch (e: unknown) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={onClose}>
      <aside
        className="slide-in h-full w-full max-w-[580px] overflow-y-auto border-l border-line bg-surface p-6"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium text-muted">
              Chat {tc.chat_id} · turn {tc.turn_no}
            </div>
            <div className="mono mt-0.5 text-[11px] text-muted">
              {tc.tc_id} · v{tc.version} · <span className={STATUS_COLORS[tc.status]}>{tc.status}</span>
            </div>
          </div>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        {editing ? (
          <div className="mt-5 space-y-4">
            <Field label="Question">
              <textarea
                value={form.question}
                onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))}
                rows={3}
                className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand"
              />
            </Field>
            <Field label="Expected answer">
              <textarea
                value={form.expected_answer}
                onChange={(e) => setForm((f) => ({ ...f, expected_answer: e.target.value }))}
                rows={4}
                className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand"
              />
            </Field>
            <Field label="Expected sources (| = AND, , = OR)">
              <input
                value={form.expected_sources}
                onChange={(e) => setForm((f) => ({ ...f, expected_sources: e.target.value }))}
                placeholder="doc_a.pdf|doc_b.pdf"
                className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand"
              />
            </Field>
            <Field label="Type">
              <input
                value={form.type}
                onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                className="w-full rounded border border-line bg-surface-2 p-2.5 text-sm outline-none focus:border-brand"
              />
            </Field>
            {err && <p className="text-xs text-bad">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button onClick={save} disabled={saving}
                className="rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110">
                {saving ? "Saving…" : "Save new version"}
              </button>
              <button onClick={() => setEditing(false)} className="rounded border border-line px-4 py-2 text-sm hover:bg-surface-2">
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-5 space-y-4">
            <ReadField label="Question">{tc.question}</ReadField>
            <ReadField label="Expected answer">{tc.expected_answer}</ReadField>
            {tc.expected_sources && <ReadField label="Expected sources">{tc.expected_sources}</ReadField>}
            <div className="flex gap-2 pt-1">
              <button onClick={() => setEditing(true)}
                className="rounded border border-line px-4 py-2 text-sm font-medium hover:bg-surface-2">
                Edit
              </button>
            </div>
          </div>
        )}

        {history && history.length > 1 && (
          <div className="mt-8">
            <div className="label mb-3">Version history</div>
            <div className="space-y-2">
              {[...history].reverse().map((h) => (
                <div key={h.version} className={`rounded border p-3 text-xs ${h.version === tc.version ? "border-brand" : "border-line"}`}>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="mono font-medium">v{h.version}</span>
                    <span className="text-muted">{fmtDate(h.created_at)}</span>
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
    setSaving(true); setErr("");
    try {
      await api.createTestCase({
        group_id: form.group_id || undefined,
        chat_id: form.chat_id.trim(),
        turn_no: parseInt(form.turn_no) || 1,
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
                <input value={form.turn_no} onChange={set("turn_no")} type="number" min={1}
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
