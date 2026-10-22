import { Link } from "react-router-dom";
import { fmt, fmtSeconds } from "../lib";
import { DEFAULT_TOLERANCE, quality, type Recommendation as Reco, type RecoSettings } from "../recommend";
import type { VersionSummary } from "../types";
import { Mark } from "./parts";

const figure = (label: string, value: string, unit: string, color: string) => (
  <div>
    <div className="label">{label}</div>
    <div className="num mt-1.5 text-[34px] leading-none">
      <Mark color={color}>{value}</Mark>
      {unit && <span className="mono ml-1 text-xs text-muted">{unit}</span>}
    </div>
  </div>
);

function Side({ title, v, note }: { title: string; v: VersionSummary; note: string }) {
  return (
    <div className="text-[13px] leading-snug">
      <span className="label mr-2">{title}</span>
      <Link to={`/v/${v.version}`} className="mono font-medium text-brand hover:underline">v{v.version}</Link>
      <span className="text-muted"> · {note}</span>
    </div>
  );
}

const describe = (v: VersionSummary) =>
  `answer ${fmt(v.avg_answer_marks)}, material ${fmt(v.avg_material_marks)}, ${fmtSeconds(v.avg_total_time)}`;

/** The call-to-action panel: which version to ship, why, and what the alternatives trade away. */
export function Recommendation({ reco, settings, onChange }: {
  reco: Reco; settings: RecoSettings; onChange: (s: RecoSettings) => void;
}) {
  const { best } = reco;
  const q = best ? quality(best) : null;
  return (
    <section className="card mt-4 overflow-hidden" style={{ borderLeft: "5px solid var(--brand)" }}>
      <div className="grid gap-6 p-5 lg:grid-cols-[auto_1fr_minmax(260px,340px)] lg:items-center">
        <div>
          <div className="label">Recommended version</div>
          {best ? (
            <>
              <div className="num mt-1.5 text-[56px] leading-none"><Mark>v{best.version}</Mark></div>
              <Link to={`/v/${best.version}`} className="mono mt-2 inline-block text-xs text-brand hover:underline">open full results ›</Link>
            </>
          ) : (
            <div className="num mt-2 text-[28px] leading-tight text-muted">None yet</div>
          )}
        </div>

        {best ? (
          <div>
            <div className="flex flex-wrap gap-x-8 gap-y-3">
              {figure("Answer", fmt(best.avg_answer_marks), "/10", "var(--hl-good)")}
              {figure("Material", fmt(best.avg_material_marks), "/10", "var(--hl)")}
              {figure("Time", fmtSeconds(best.avg_total_time), "", "var(--hl-bad)")}
            </div>
            <p className="mt-3 text-[13px] text-muted">
              {reco.reason} <span className="mono">quality {q?.toFixed(2)}</span>
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted">
            {reco.budgetMiss && reco.fastest
              ? `No version responds within ${settings.maxTime}s. The fastest is v${reco.fastest.version} at ${fmtSeconds(reco.fastest.avg_total_time)}.`
              : "No comparable, fully graded version to recommend yet."}
          </p>
        )}

        <div className="space-y-1.5 border-line lg:border-l lg:pl-6">
          {reco.fastest && best && <Side title="Fastest" v={reco.fastest} note={`${describe(reco.fastest)}`} />}
          {reco.runnerUp && <Side title="Runner-up" v={reco.runnerUp} note={describe(reco.runnerUp)} />}
          {reco.latestGap && (
            <div className="text-[13px]" style={{ color: "var(--bad)" }}>
              Latest v{reco.latestGap.version} is {reco.latestGap.gap.toFixed(1)} below on quality.
            </div>
          )}
          {reco.notComparable.length > 0 && (
            <div className="text-xs text-muted">
              Not compared (different question set): {reco.notComparable.map((v) => `v${v.version}`).join(", ")}
            </div>
          )}
          {reco.excluded.length > 0 && (
            <div className="text-xs text-muted">
              Left out (failed rows): {reco.excluded.map((v) => `v${v.version}`).join(", ")}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line bg-surface-2 px-5 py-2.5 text-xs text-muted">
        <span>Quality = 60% answer + 40% material. Speed only breaks ties.</span>
        <label className="ml-auto flex items-center gap-2">
          Tie tolerance
          <input type="number" min={0} max={3} step={0.05} value={settings.tolerance}
            onChange={(e) => onChange({ ...settings, tolerance: Number.isNaN(e.target.valueAsNumber) ? DEFAULT_TOLERANCE : Math.max(0, e.target.valueAsNumber) })}
            className="mono w-16 rounded border border-line bg-surface px-2 py-1 text-fg outline-none focus:border-brand" />
        </label>
        <label className="flex items-center gap-2">
          Max response time
          <input type="number" min={0} step={0.1} placeholder="none" value={settings.maxTime ?? ""}
            onChange={(e) => onChange({ ...settings, maxTime: e.target.value === "" || e.target.valueAsNumber <= 0 ? null : e.target.valueAsNumber })}
            className="mono w-16 rounded border border-line bg-surface px-2 py-1 text-fg outline-none focus:border-brand" />
          s
        </label>
      </div>
    </section>
  );
}
