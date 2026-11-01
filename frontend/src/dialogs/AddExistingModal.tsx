import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { TestCase } from "../api/types";
import { GroupChips } from "../components/GroupChips";

const SHOWN = 150;   // rows drawn at once; searching narrows a long library down

/** Pick test cases from the library that are not in this group yet, and put them in it. */
export function AddExistingModal({ groupId, groupName, onClose, onDone }: {
  groupId: string;
  groupName: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [cases, setCases] = useState<TestCase[] | null>(null);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.testCases().then((all) => setCases(all.filter((c) => !c.groups.some((g) => g.group_id === groupId)))).catch((e) => setErr(e.message));
  }, [groupId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (cases ?? []).filter((c) => !q || `${c.chat_id} ${c.question} ${c.groups.map((g) => g.name).join(" ")}`.toLowerCase().includes(q));
  }, [cases, query]);
  const shown = matches.slice(0, SHOWN);
  const allShownPicked = shown.length > 0 && shown.every((c) => picked.has(c.tc_id));

  const toggle = (id: string) => setPicked((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleShown = () => setPicked((prev) => {
    const next = new Set(prev);
    shown.forEach((c) => (allShownPicked ? next.delete(c.tc_id) : next.add(c.tc_id)));
    return next;
  });

  async function save() {
    setSaving(true); setErr("");
    try {
      const { added } = await api.addToGroup(groupId, [...picked]);
      onDone(`${added} test case${added !== 1 ? "s" : ""} added to "${groupName}"`);
    } catch (e) {
      setErr((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={onClose}>
      <div className="card pop-in flex max-h-[85vh] w-full max-w-2xl flex-col bg-surface" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 px-6 pb-3 pt-5">
          <div>
            <h2 className="font-serif text-xl font-medium">Add existing test cases</h2>
            <p className="mt-0.5 text-sm text-muted">Pick the ones to put in “{groupName}”. Cases already in it are not listed.</p>
          </div>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        <div className="flex items-center gap-3 px-6 pb-3">
          <input value={query} onChange={(e) => setQuery(e.target.value)} autoFocus placeholder="Search questions, chats, groups…"
            className="w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
          <button onClick={toggleShown} disabled={shown.length === 0}
            className="shrink-0 text-xs font-medium text-brand hover:underline disabled:opacity-40">
            {allShownPicked ? "Clear shown" : `Select ${shown.length} shown`}
          </button>
        </div>

        <div className="min-h-[160px] flex-1 overflow-y-auto border-y border-line">
          {!cases && !err && <p className="px-6 py-10 text-center text-sm text-muted">Loading…</p>}
          {cases && cases.length === 0 && (
            <p className="px-6 py-10 text-center text-sm text-muted">Every test case is already in this group. Use “Create a new test case” to add another.</p>
          )}
          {cases && cases.length > 0 && matches.length === 0 && <p className="px-6 py-10 text-center text-sm text-muted">Nothing matches your search.</p>}
          <ul className="divide-y divide-line">
            {shown.map((c) => (
              <li key={c.tc_id}>
                <label className={`flex cursor-pointer items-start gap-3 px-6 py-2.5 hover:bg-surface-2 ${picked.has(c.tc_id) ? "bg-brand-soft" : ""}`}>
                  <input type="checkbox" checked={picked.has(c.tc_id)} onChange={() => toggle(c.tc_id)} className="mt-1 accent-brand" />
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-sm font-medium">{c.question}</span>
                    <span className="mono mt-0.5 block text-[11px] text-muted">
                      {c.chat_id} · turn {c.turn_no}{c.status === "inactive" && " · inactive"}
                    </span>
                  </span>
                  <span className="w-32 shrink-0"><GroupChips groups={c.groups} max={2} /></span>
                </label>
              </li>
            ))}
          </ul>
          {matches.length > SHOWN && (
            <p className="px-6 py-3 text-center text-xs text-muted">Showing {SHOWN} of {matches.length}. Search to narrow the list.</p>
          )}
        </div>

        {err && <p className="px-6 pt-3 text-xs text-bad">{err}</p>}
        <div className="flex items-center justify-between gap-3 px-6 py-4">
          <span className="text-sm text-muted">{picked.size} selected</span>
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded px-4 py-2 text-sm font-medium text-muted hover:bg-surface-2">Cancel</button>
            <button onClick={save} disabled={saving || picked.size === 0}
              className="rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110">
              {saving ? "Adding…" : picked.size > 0 ? `Add ${picked.size}` : "Add"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
