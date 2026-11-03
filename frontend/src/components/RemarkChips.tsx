import type { RemarkTag } from "../api/types";

const TONE: Record<RemarkTag["tone"], string> = {
  good: "bg-good/10 text-good",
  warn: "bg-warn/10 text-warn",
  bad: "bg-bad/10 text-bad",
};

/**
 * The short reasons the judge gave for one score ("Wrong answer", "Context partial"), coloured by how good they are.
 * `reason` is the judge's full sentence, shown when the pointer rests on the chips.
 */
export function RemarkChips({ label, tags, reason }: { label: string; tags?: RemarkTag[]; reason?: string | null }) {
  if (!tags?.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1" title={reason || undefined}>
      <span className="text-[10px] uppercase tracking-wide text-muted">{label}</span>
      {tags.map((tag) => (
        <span key={tag.key} className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${TONE[tag.tone]}`}>
          {tag.label}
        </span>
      ))}
    </div>
  );
}
