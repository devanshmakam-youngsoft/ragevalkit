import type { VersionSummary } from "../api/types";

const KNOWN_NODES: Record<string, { label: string; color: string }> = {
  query_decider: { label: "Query decider", color: "var(--brand)" },
  query_rewriter: { label: "Query rewriter", color: "#2f7fb5" },
  retriever: { label: "Retriever", color: "var(--sun)" },
  answer_generator: { label: "Answer generator", color: "var(--coral)" },
  replier: { label: "Replier", color: "var(--plum)" },
  summarizer: { label: "Summarizer", color: "var(--muted)" },
};
// colours for nodes we have never seen; picked by name so a node keeps its colour on every page
const EXTRA_COLORS = ["#2b8a9e", "#8a9a2f", "#c2528b", "#e0852b", "#4f6bd6", "#3d9970", "#b5651d", "#7d5ba6"];

export function nodeMeta(name: string): { label: string; color: string } {
  const known = KNOWN_NODES[name];
  if (known) return known;
  const hash = [...name].reduce((h, c) => h + c.charCodeAt(0), 0);
  const label = name.replace(/_/g, " ");
  return { label: label.charAt(0).toUpperCase() + label.slice(1), color: EXTRA_COLORS[hash % EXTRA_COLORS.length] };
}

/** Union of nodes across versions in pipeline order (a new node is placed right after its predecessor). */
export function unionNodes(versions: VersionSummary[]): string[] {
  const order: string[] = [];
  for (const v of versions) {
    v.nodes.forEach((n, i) => {
      if (order.includes(n.name)) return;
      if (i === 0) order.unshift(n.name);
      else order.splice(order.indexOf(v.nodes[i - 1].name) + 1, 0, n.name);
    });
  }
  return order;
}

export const fmt = (n: number | null | undefined, digits = 1) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(digits);

export const fmtSeconds = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n < 10 ? `${n.toFixed(2)}s` : `${n.toFixed(1)}s`;

export function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) +
    " · " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** "22 Oct 2026" — the day alone, for places where the date should stand out. */
export function fmtDay(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** "05:03 PM" */
export function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** "1 case" / "2 cases" */
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export function scoreTone(score: number | null | undefined): "good" | "warn" | "bad" | "none" {
  if (score === null || score === undefined) return "none";
  return score >= 8 ? "good" : score >= 5 ? "warn" : "bad";
}

export function compareVersions(a: string | number, b: string | number) {
  const na = Number(a), nb = Number(b);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export function nextVersion(versions: VersionSummary[]): string {
  const nums = versions.map((v) => Number(v.version)).filter((n) => Number.isInteger(n));
  return String((nums.length ? Math.max(...nums) : 0) + 1);
}
