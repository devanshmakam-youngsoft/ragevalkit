import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { fmt, fmtSeconds, nodeMeta, scoreTone } from "../lib/format";
import { type VersionSummary } from "../api/types";

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

export function Delta({ current, previous, invert = false, unit = "", digits = 1, title }: {
  current: number | null | undefined; previous: number | null | undefined; invert?: boolean; unit?: string; digits?: number;
  /** Explains what the change was measured on. */
  title?: string;
}) {
  if (current == null || previous == null) return null;
  const diff = current - previous;
  if (Math.abs(diff) < 0.05 * Math.pow(10, 1 - digits)) return <span className="mono text-[11px] text-muted" title={title}>±0</span>;
  const better = invert ? diff < 0 : diff > 0;
  return (
    <span className="mono text-[11px] font-medium" title={title} style={{ color: better ? "var(--good)" : "var(--bad)" }}>
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

export type Segment = {
  key: string;
  /** Relative size; the bar is divided in proportion to these. */
  weight: number;
  /** Written inside the segment when it is wide enough to show it. */
  text: string;
  /** Shown on hover. */
  title: string;
  /** Fill colour, or a class (for example "bg-good") when the colour comes from the theme. */
  color?: string;
  className?: string;
};

/**
 * One wide bar divided into segments, each with its text (a percentage) inside it. The text is shown whenever it
 * physically fits: the bar's width is measured, so a 5% segment on a wide screen still gets its label and a
 * narrow screen drops only the ones that would be cut off.
 */
export function SegmentBar({ segments }: { segments: Segment[] }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const watcher = new ResizeObserver(measure);
    watcher.observe(el);
    return () => watcher.disconnect();
  }, []);
  const total = segments.reduce((t, s) => t + s.weight, 0) || 1;
  return (
    <div ref={box} className="flex h-6 gap-px overflow-hidden rounded text-xs font-medium text-white">
      {segments.map((seg) => {
        const share = (seg.weight / total) * 100;
        const fits = (share / 100) * width >= seg.text.length * 7.5 + 12;     // about 7.5px a character at this size, plus padding
        return (
          <div key={seg.key} title={seg.title} style={{ width: `${share}%`, ...(seg.color ? { background: seg.color } : {}) }}
            className={`flex items-center justify-center overflow-hidden whitespace-nowrap ${seg.className ?? ""}`}>
            {fits && seg.text}
          </div>
        );
      })}
    </div>
  );
}

const REST_KEY = "__rest";

/**
 * The pieces of a question's response time: each step, plus whatever time was spent outside any step.
 * Percentages are shares of the whole response time, so a single tracked step that took half of it says 50%,
 * not 100%. A step records how long it took, not when, so steps running side by side can add up to more than
 * the response time; their percentages then add up to more than 100% and `overlapping` says so.
 */
function stepPieces(v: VersionSummary) {
  const steps = v.nodes.filter((n) => n.avg > 0);
  const sum = steps.reduce((t, n) => t + n.avg, 0);
  const total = v.avg_total_time != null && v.avg_total_time > 0 ? v.avg_total_time : sum;   // no total recorded: the steps are all we know
  const pct = (secs: number) => (secs / total) * 100;
  const pieces = steps.map((n) => ({ key: n.name, label: nodeMeta(n.name).label, secs: n.avg, pct: pct(n.avg), color: nodeShade(n.name), rest: false }));
  const rest = total - sum;
  if (rest > total * 0.02) pieces.push({ key: REST_KEY, label: "Not in a step", secs: rest, pct: pct(rest), color: "", rest: true });
  const span = pieces.reduce((t, p) => t + p.pct, 0) || 1;      // 100, or more when steps overlap: the bar then shows each piece's size relative to the others
  return { pieces: pieces.map((p) => ({ ...p, width: (p.pct / span) * 100 })), total, overlapping: sum > total * 1.05 };
}

/**
 * Timing of steps as one wide bar, like the score bar: each step's share of the whole response time is written
 * inside its segment and the legend gives the seconds. Time outside any step is its own grey segment.
 */
export function StepTimeBar({ v }: { v: VersionSummary }) {
  const { pieces, total, overlapping } = stepPieces(v);
  const steps = pieces.filter((p) => !p.rest);
  if (steps.length === 0) return null;
  const slowest = steps.reduce((a, b) => (b.secs > a.secs ? b : a));
  return (
    <>
      <SegmentBar segments={pieces.map((p) => ({
        key: p.key, weight: p.width, text: `${p.pct.toFixed(0)}%`,
        title: `${p.label}: ${fmtSeconds(p.secs)} (${p.pct.toFixed(0)}% of the response time)`,
        ...(p.rest ? { className: "bg-line text-muted" } : { color: p.color }),
      }))} />
      <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        {pieces.map((p) => (
          <span key={p.key} className="inline-flex items-center gap-1.5">
            <span className={`inline-block h-2 w-2 ${p.rest ? "bg-line" : ""}`} style={p.rest ? undefined : { background: p.color }} />
            {p.label}
            <span className={`mono ${p.key === slowest.key ? "hl font-medium text-fg" : "text-fg"}`}>{fmtSeconds(p.secs)}</span>
            <span className="mono">· {p.pct.toFixed(0)}%</span>
          </span>
        ))}
      </p>
      {pieces.some((p) => p.rest) && (
        <p className="mt-2 text-xs text-muted">
          “Not in a step” is time spent outside the steps above, such as code that is not wrapped in a step.
        </p>
      )}
      {overlapping && (
        <p className="mt-2 text-xs text-muted">
          Some steps run at the same time, so their percentages add up to more than 100% of the {fmtSeconds(total)} a question takes.
        </p>
      )}
    </>
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
