import { Link } from "react-router-dom";
import { fmt, fmtSeconds, plural } from "../lib";
import type { RecoResult, VersionSummary } from "../types";
import { GLOSSARY, Term } from "./Hint";
import { Mark } from "./parts";

/** Tolerance / time ceiling the user typed in; null means "use the server default from serve()". */
export interface RecoOverrides {
  tolerance: number | null;
  maxTime: number | null;
}

const figure = (label: React.ReactNode, value: string, unit: string, color: string) => (
  <div>
    <div className="label">{label}</div>
    <div className="num mt-1.5 text-[34px] leading-none">
      <Mark color={color}>{value}</Mark>
      {unit && <span className="mono ml-1 text-xs text-muted">{unit}</span>}
    </div>
  </div>
);

/** A version's scores, overall or — when a group is selected — for that group alone. */
function scoresOf(v: VersionSummary, group: string | null) {
  const g = group ? v.group_stats?.[group] : undefined;
  return {
    answer: g ? g.avg_answer_marks : v.avg_answer_marks,
    material: g ? g.avg_material_marks : v.avg_material_marks,
    time: (g ? g.avg_total_time : null) ?? v.avg_total_time,
  };
}

/** A version's scores as compared: on the shared test cases when the server compared on them. */
const describe = (v: VersionSummary, group: string | null, reco: RecoResult | null) => {
  const shared = reco?.scores[String(v.version)];
  const s = shared ? { answer: shared.answer, material: shared.material, time: shared.time } : scoresOf(v, group);
  return `answer ${fmt(s.answer)}, context ${fmt(s.material)}, ${fmtSeconds(s.time)}`;
};

function Side({ title, v, group, reco }: { title: string; v: VersionSummary; group: string | null; reco: RecoResult | null }) {
  return (
    <div className="text-[13px] leading-snug">
      <span className="label mr-2">{title}</span>
      <Link to={`/v/${v.version}`} className="mono font-medium text-brand hover:underline">v{v.version}</Link>
      <span className="text-muted"> · {describe(v, group, reco)}</span>
    </div>
  );
}

const pct = (n: number) => Math.round(n * 100);

/** The call-to-action panel: which version to ship, why, and what the alternatives trade away. */
export function Recommendation({ reco, versions, archivedCount, overrides, onChange, groupName }: {
  reco: RecoResult | null;
  /** Non-archived versions: the only ones that are ever compared. */
  versions: VersionSummary[];
  archivedCount: number;
  overrides: RecoOverrides;
  onChange: (o: RecoOverrides) => void;
  groupName: string | null;
}) {
  const find = (id: string | null) => (id ? versions.find((v) => String(v.version) === id) ?? null : null);
  const best = find(reco?.best ?? null);
  const fastest = find(reco?.fastest ?? null);
  const runnerUp = find(reco?.runner_up ?? null);
  const quality = best && reco ? reco.qualities[String(best.version)] : null;
  const own = best ? scoresOf(best, groupName) : null;
  const shared = best && reco ? reco.scores[String(best.version)] : undefined;
  // the numbers the recommendation was based on (the shared test cases), falling back to the run's own
  const bestScores = own ? { answer: shared?.answer ?? own.answer, material: shared ? shared.material : own.material, time: shared?.time ?? own.time } : null;
  const ranCases = best ? (groupName ? best.group_stats?.[groupName]?.total_rows ?? best.total_rows : best.total_rows) : 0;
  const ranGroups = best && !groupName ? best.group_names ?? [] : [];
  const alone = !reco?.runner_up;     // the only version that could be compared
  const list = (ids: string[]) => ids.map((id) => `v${id}`).join(", ");

  const weightsText = !reco ? "" : reco.basis === "answer_only"
    ? "Overall score = answer quality only."
    : `Overall score = ${pct(reco.weights.answer)}% ${GLOSSARY.answer.label.toLowerCase()} + ${pct(reco.weights.material)}% ${GLOSSARY.context.label.toLowerCase()}.`;

  return (
    <section className="card mt-4 overflow-hidden" style={{ borderLeft: "5px solid var(--brand)" }}>
      <div className="grid gap-6 p-5 lg:grid-cols-[auto_1fr_minmax(260px,340px)] lg:items-center">
        <div>
          <div className="label">Recommended version{groupName ? ` · ${groupName}` : ""}</div>
          {best ? (
            <>
              <div className="num mt-1.5 text-[56px] leading-none"><Mark>v{best.version}</Mark></div>
              <div className="mt-2 text-xs text-muted">
                <div>{plural(ranCases, "test case")} ran</div>
                {ranGroups.length > 0 && <div className="mt-0.5">{ranGroups.join(", ")}</div>}
              </div>
              <Link to={`/v/${best.version}`} className="mono mt-1 inline-block text-xs text-brand hover:underline">open full results ›</Link>
            </>
          ) : (
            <div className="num mt-2 text-[28px] leading-tight text-muted">{reco ? "None yet" : "…"}</div>
          )}
        </div>

        {best && bestScores && reco ? (
          <div>
            <div className="flex flex-wrap gap-x-8 gap-y-3">
              {figure(<Term k="answer" />, fmt(bestScores.answer), "/10", "var(--hl-good)")}
              {reco.basis === "weighted" && figure(<Term k="context" />, fmt(bestScores.material), "/10", "var(--hl)")}
              {figure(<Term k="time" />, fmtSeconds(bestScores.time), "", "var(--hl-bad)")}
            </div>
            {/* with nothing to compare against there is nothing to explain */}
            {!alone && (
              <p className="mt-3 text-[13px] text-muted">
                {reco.reason} <span className="mono">overall score {quality?.toFixed(2)}</span>
              </p>
            )}
            {/* only worth saying when versions ran different test cases, so the comparison used the ones they share */}
            {!alone && reco.compared_cases != null && reco.partial.length > 0 && (
              <p className="mt-1 text-xs text-muted">
                Compared on the {plural(reco.compared_cases, "test case")} every version ran ({reco.partial.map((p) => `v${p.version} ran ${p.ran}`).join(", ")}).
              </p>
            )}
            {reco.basis_note && <p className="mt-1 text-xs text-warn">{reco.basis_note}</p>}
          </div>
        ) : (
          <p className="text-sm text-muted">
            {reco?.budget_miss && reco.fastest
              ? `No version responds within ${reco.max_time}s. The fastest is v${reco.fastest}.`
              : reco ? "No comparable, fully graded version to recommend yet." : "Working it out…"}
          </p>
        )}

        <div className="space-y-1.5 border-line lg:border-l lg:pl-6">
          {fastest && best && <Side title="Fastest" v={fastest} group={groupName} reco={reco} />}
          {runnerUp && <Side title="Runner-up" v={runnerUp} group={groupName} reco={reco} />}
          {reco?.latest_gap && (
            <div className="text-[13px]" style={{ color: "var(--bad)" }}>
              Latest v{reco.latest_gap.version} scores {reco.latest_gap.gap.toFixed(1)} lower overall.
            </div>
          )}
          {reco?.not_comparable.map((id) => (
            <div key={`n${id}`} className="text-xs text-muted">Not compared: v{id} {reco.not_comparable_detail[id] ?? "ran different test cases"}.</div>
          ))}
          {reco?.excluded.map((id) => (
            <div key={`e${id}`} className="text-xs text-muted">Left out: v{id} — {reco.excluded_detail[id] ?? "failed rows or stopped early"}.</div>
          ))}
          {archivedCount > 0 && (
            <div className="text-xs text-muted">{archivedCount} archived version{archivedCount !== 1 ? "s are" : " is"} not part of this comparison.</div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line bg-surface-2 px-5 py-2.5 text-xs text-muted">
        <span>{weightsText} Speed only breaks ties.</span>
        <label className="ml-auto flex items-center gap-2">
          <span><Term k="tolerance" /></span>
          <input type="number" min={0} max={3} step={0.05} value={overrides.tolerance ?? ""}
            placeholder={reco ? String(reco.tolerance) : ""}
            onChange={(e) => onChange({
              ...overrides,
              tolerance: e.target.value === "" || Number.isNaN(e.target.valueAsNumber) ? null : Math.max(0, e.target.valueAsNumber),
            })}
            className="mono w-16 rounded border border-line bg-surface px-2 py-1 text-fg outline-none focus:border-brand" />
        </label>
        <label className="flex items-center gap-2">
          <span><Term k="maxTime" /></span>
          <input type="number" min={0} step={0.1} placeholder={reco?.max_time != null ? String(reco.max_time) : "none"}
            value={overrides.maxTime ?? ""}
            onChange={(e) => onChange({
              ...overrides,
              maxTime: e.target.value === "" || e.target.valueAsNumber <= 0 ? null : e.target.valueAsNumber,
            })}
            className="mono w-16 rounded border border-line bg-surface px-2 py-1 text-fg outline-none focus:border-brand" />
          s
        </label>
      </div>
    </section>
  );
}
