import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Group } from "../api/types";

const NEW = "__new__";

/** Put a group label on the given test cases: pick an existing group or create one on the spot. */
export function AddToGroupModal({ groups, tcIds, onClose, onDone }: {
  groups: Group[];
  tcIds: string[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [choice, setChoice] = useState(groups[0]?.group_id ?? NEW);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const creating = choice === NEW;
  const canSave = !saving && (!creating || name.trim().length > 0);

  async function save() {
    setSaving(true); setErr("");
    try {
      const target = creating ? await api.createGroup(name.trim()) : groups.find((g) => g.group_id === choice)!;
      const { added } = await api.addToGroup(target.group_id, tcIds);
      const skipped = tcIds.length - added;
      onDone(`${added} test case${added !== 1 ? "s" : ""} added to "${target.name}"` +
        (skipped > 0 ? ` (${skipped} already in it)` : ""));
    } catch (e) {
      setErr((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={onClose}>
      <div className="card pop-in w-full max-w-sm bg-surface p-6" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-serif text-xl font-medium">Add to group</h2>
            <p className="mt-0.5 text-sm text-muted">{tcIds.length} test case{tcIds.length !== 1 ? "s" : ""} selected</p>
          </div>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        <div className="mt-4 max-h-56 divide-y divide-line overflow-y-auto rounded border border-line">
          {groups.map((g) => (
            <label key={g.group_id}
              className={`flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm hover:bg-surface-2 ${choice === g.group_id ? "bg-brand-soft" : ""}`}>
              <input type="radio" name="grp" checked={choice === g.group_id} onChange={() => setChoice(g.group_id)} className="accent-brand" />
              <span className="flex-1 truncate font-medium">{g.name}</span>
              <span className="mono text-xs text-muted">{g.member_count}</span>
            </label>
          ))}
          <label className={`flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm hover:bg-surface-2 ${creating ? "bg-brand-soft" : ""}`}>
            <input type="radio" name="grp" checked={creating} onChange={() => setChoice(NEW)} className="accent-brand" />
            <span className="font-medium">New group…</span>
          </label>
        </div>

        {creating && (
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="Group name"
            onKeyDown={(e) => e.key === "Enter" && canSave && save()}
            className="mt-3 w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand" />
        )}
        {err && <p className="mt-3 text-xs text-bad">{err}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-4 py-2 text-sm font-medium text-muted hover:bg-surface-2">Cancel</button>
          <button onClick={save} disabled={!canSave}
            className="rounded bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 enabled:hover:brightness-110">
            {saving ? "Adding…" : "Add"}
          </button>
        </div>
      </div>
    </div>
  );
}
