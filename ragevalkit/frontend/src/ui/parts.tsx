import { type ReactNode } from "react";
import { fmt, fmtSeconds, nodeMeta, scoreTone } from "../lib";
import { type VersionSummary } from "../types";

const TONE_VAR = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)", none: "var(--muted)" };
const TONE_HL = { good: "var(--hl-good)", warn: "var(--hl-warn)", bad: "var(--hl-bad)", none: "transparent" };

/** A score: serif numeral on a marker-pen highlight in its tone colour, with a thin gauge underneath. */
export function ScorePill({ value, suffix = "/10", digits = 1 }: { value: number | null | undefined; suffix?: string; digits?: number }) {
  const tone = scoreTone(value);
  const pct = value == null ? 0 : Math.max(0, Math.min(100, (value / 10) * 100));
  return (
    <span className="inline-block w-[72px]">
      <span className="num hl text-[24px] leading-none" style={{ ["--hl-c" as string]: TONE_HL[tone] }}>{fmt(value, digits)}</span>
      {value != null && <span className="mono ml-1 text-[10px] text-muted">{suffix}</span>}
      <span className="mt-1.5 block h-[3px] bg-line">
        <span className="block h-full" style={{ width: `${pct}%`, background: TONE_VAR[tone] }} />
      </span>
    </span>
  );
}

export function Delta({ current, previous, invert = false, unit = "", digits = 1 }: {
  current: number | null | undefined; previous: number | null | undefined; invert?: boolean; unit?: string; digits?: number;
}) {
  if (current == null || previous == null) return null;
  const diff = current - previous;
  if (Math.abs(diff) < 0.05 * Math.pow(10, 1 - digits)) return <span className="mono text-[11px] text-muted">±0</span>;
  const better = invert ? diff < 0 : diff > 0;
  return (
    <span className="mono text-[11px] font-medium" style={{ color: better ? "var(--good)" : "var(--bad)" }}>
      {diff > 0 ? "+" : "−"}{Math.abs(diff).toFixed(digits)}{unit}
    </span>
  );
}

export const nodeShade = (name: string) => nodeMeta(name).color;

export function NodeTimings({ v, compact = false }: { v: VersionSummary; compact?: boolean }) {
  const items = v.nodes.filter((n) => n.avg > 0).map((n) => ({ n: n.name, val: n.avg }));
  const total = items.reduce((s, i) => s + i.val, 0) || 1;
  const slowest = items.reduce((a, b) => (b.val > a.val ? b : a), items[0]);
  return (
    <div className="min-w-[220px]">
      <div className="flex h-2.5 gap-px overflow-hidden">
        {items.map((i) => (
          <div key={i.n} title={`${nodeMeta(i.n).label}: ${fmtSeconds(i.val)}`}
            style={{ width: `${(i.val / total) * 100}%`, background: nodeShade(i.n) }} />
        ))}
      </div>
      <div className={`mt-2 grid gap-x-4 gap-y-0.5 text-[11px] ${compact ? "grid-cols-2" : "grid-cols-1 sm:grid-cols-2"}`}>
        {items.map((i) => (
          <div key={i.n} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-muted">
              <span className="h-2 w-2" style={{ background: nodeShade(i.n) }} />
              {nodeMeta(i.n).label}
            </span>
            <span className={`mono ${slowest?.n === i.n ? "hl font-medium" : "text-fg"}`}>{fmtSeconds(i.val)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** KPI card with a coloured top edge; the figure sits on a marker highlight. */
export function Mark({ children, color = "var(--hl)" }: { children: ReactNode; color?: string }) {
  return <span className="hl" style={{ ["--hl-c" as string]: color }}>{children}</span>;
}

export function Stat({ label, value, sub, accent = "var(--brand)" }: {
  label: ReactNode; value: ReactNode; sub?: ReactNode; accent?: string;
}) {
  return (
    <div className="card px-4 pb-3.5 pt-3" style={{ borderTop: `4px solid ${accent}` }}>
      <div className="label">{label}</div>
      <div className="num mt-2 flex items-baseline gap-2 text-[36px] leading-none">
        {value}
      </div>
      {sub && <div className="mt-2 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="h-2 w-full bg-line">
      <div className="h-full bg-brand transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%` }} />
    </div>
  );
}
