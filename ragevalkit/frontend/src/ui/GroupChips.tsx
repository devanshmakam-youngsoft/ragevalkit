import type { GroupRef } from "../types";

/** The group labels on a test case, as compact chips. Shows `max` and a "+n" for the rest. */
export function GroupChips({ groups, max = 3 }: { groups: GroupRef[]; max?: number }) {
  if (groups.length === 0) return <span className="text-[11px] text-muted">—</span>;
  const shown = groups.slice(0, max);
  const rest = groups.slice(max);
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((g) => (
        <span key={g.group_id} title={g.name}
          className="max-w-[140px] truncate rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-medium text-fg">
          {g.name}
        </span>
      ))}
      {rest.length > 0 && (
        <span title={rest.map((g) => g.name).join(", ")} className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">
          +{rest.length}
        </span>
      )}
    </div>
  );
}

/** Chat and turn as two labelled values, so they read the same everywhere they appear. */
export function ChatTurn({ chatId, turnNo }: { chatId: string; turnNo: number }) {
  return (
    <div className="flex items-center gap-4">
      <div>
        <div className="label">Chat</div>
        <div className="mono mt-0.5 text-sm text-fg">{chatId}</div>
      </div>
      <div>
        <div className="label">Turn</div>
        <div className="mono mt-0.5 text-sm text-fg">{turnNo}</div>
      </div>
    </div>
  );
}
