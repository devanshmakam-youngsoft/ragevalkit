// Picks the version to recommend. Self-contained (type-only imports) so it can be unit-tested with plain node.
import type { VersionSummary } from "./types";

/** Quality is a weighted mix of the two judge marks. Answer matters more: it is what the user reads. */
export const QUALITY_WEIGHTS = { answer: 0.6, material: 0.4 };
export const DEFAULT_TOLERANCE = 0.25;

export interface RecoSettings {
  /** Versions within this many quality points of the best count as tied; speed then breaks the tie. */
  tolerance: number;
  /** Optional response-time ceiling in seconds. */
  maxTime: number | null;
}

export interface Recommendation {
  best: VersionSummary | null;
  reason: string;
  /** Fastest eligible version, only when it differs from `best`. */
  fastest: VersionSummary | null;
  /** Next best eligible version by quality. */
  runnerUp: VersionSummary | null;
  /** Latest version if it is clearly worse than `best`. */
  latestGap: { version: string | number; gap: number } | null;
  /** Versions left out because their question set differs from the usual one, or they had failed rows. */
  notComparable: VersionSummary[];
  excluded: VersionSummary[];
  budgetMiss: boolean;
}

export function quality(v: VersionSummary): number | null {
  const a = v.avg_answer_marks;
  const m = v.avg_material_marks;
  if (a == null) return null;
  if (m == null) return a;
  return QUALITY_WEIGHTS.answer * a + QUALITY_WEIGHTS.material * m;
}

const time = (v: VersionSummary) => v.avg_total_time ?? Number.POSITIVE_INFINITY;

/** Most common question-set size; ties go to the most recent version. */
function referenceRows(versions: VersionSummary[]): number {
  const counts = new Map<number, number>();
  for (const v of versions) counts.set(v.total_rows, (counts.get(v.total_rows) ?? 0) + 1);
  let best = versions[versions.length - 1].total_rows;
  let bestCount = counts.get(best) ?? 0;
  for (const [rows, count] of counts) if (count > bestCount) { best = rows; bestCount = count; }
  return best;
}

export function recommend(versions: VersionSummary[], s: RecoSettings): Recommendation {
  const empty: Recommendation = { best: null, reason: "", fastest: null, runnerUp: null, latestGap: null, notComparable: [], excluded: [], budgetMiss: false };
  if (versions.length === 0) return empty;

  const rows = referenceRows(versions);
  const notComparable = versions.filter((v) => v.total_rows !== rows);
  const excluded = versions.filter((v) => v.total_rows === rows && (v.failed_rows > 0 || quality(v) == null));
  const eligible = versions.filter((v) => v.total_rows === rows && v.failed_rows === 0 && quality(v) != null);
  if (eligible.length === 0) return { ...empty, notComparable, excluded };

  const fits = s.maxTime == null ? eligible : eligible.filter((v) => time(v) <= s.maxTime!);
  if (fits.length === 0) {
    const fastest = [...eligible].sort((a, b) => time(a) - time(b))[0];
    return { ...empty, fastest, notComparable, excluded, budgetMiss: true };
  }

  const q = (v: VersionSummary) => quality(v) as number;
  const top = Math.max(...fits.map(q));
  const tied = fits.filter((v) => q(v) >= top - s.tolerance);
  // fastest of the tied versions; then higher quality; then the newer version
  const best = [...tied].sort((a, b) => time(a) - time(b) || q(b) - q(a) || Number(b.version) - Number(a.version))[0];

  let reason: string;
  if (fits.length === 1) reason = "Only version run on this question set.";
  else if (tied.length === 1) reason = `Highest quality of ${fits.length} comparable versions.`;
  else {
    const others = tied.filter((v) => v !== best).map((v) => `v${v.version}`).join(", ");
    reason = `Quality is within ${s.tolerance} of the top (also ${others}) and it is the fastest of those.`;
  }

  const fastestAll = [...fits].sort((a, b) => time(a) - time(b))[0];
  const rest = fits.filter((v) => v !== best);
  const runnerUp = rest.length ? [...rest].sort((a, b) => q(b) - q(a) || time(a) - time(b))[0] : null;

  const latest = versions[versions.length - 1];
  const gap = fits.includes(latest) && latest !== best ? q(best) - q(latest) : 0;

  return {
    best, reason,
    fastest: fastestAll !== best ? fastestAll : null,
    runnerUp,
    latestGap: gap > s.tolerance ? { version: latest.version, gap } : null,
    notComparable, excluded, budgetMiss: false,
  };
}
