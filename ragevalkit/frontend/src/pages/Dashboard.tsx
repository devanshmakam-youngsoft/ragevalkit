import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Delta, Mark, NodeTimings, ProgressBar, ScorePill, Stat } from "../components/ScoreWidgets";
import { Recommendation } from "../components/Recommendation";
import { TopBar } from "../components/TopBar";
import { fmt, fmtDate, fmtSeconds, nodeMeta, plural, scoreTone, unionNodes } from "../lib/format";
import { useRun } from "../context/RunContext";
import { GLOSSARY, Hint, Term } from "../components/Hint";
import { Pager, usePaging } from "../components/Pager";
import { type RecoResult, type VersionSummary } from "../api/types";

type SortKey = "version" | "date" | "questions" | "answer" | "material" | "time";

/** Tolerance / time-ceiling the user typed in. null = use the server's defaults from serve(). */
interface RecoOverrides { tolerance: number | null; maxTime: number | null }

function loadOverrides(): RecoOverrides {
  try {
    const raw = JSON.parse(localStorage.getItem("recoOverrides") ?? "null");
    if (raw) return {
      tolerance: typeof raw.tolerance === "number" ? raw.tolerance : null,
      maxTime: typeof raw.maxTime === "number" ? raw.maxTime : null,
    };
  } catch { /* storage unavailable or corrupt */ }
  return { tolerance: null, maxTime: null };
}

const tooltipStyle = {
  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, fontSize: 12, color: "var(--fg)", boxShadow: "none",
};

export default function Dashboard() {
  const nav = useNavigate();
  const { run, versionsKey, dismiss, requestStop } = useRun();
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [error, setError] = useState("");
  const [overrides, setOverrides] = useState<RecoOverrides>(loadOverrides);
  const updateOverrides = (o: RecoOverrides) => {
    setOverrides(o);
    try { localStorage.setItem("recoOverrides", JSON.stringify(o)); } catch { /* ignore */ }
  };
  const [refreshKey, setRefreshKey] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [compareSelected, setCompareSelected] = useState<Set<string>>(new Set());
  useEffect(() => { if (!compareMode) setCompareSelected(new Set()); }, [compareMode]);
  const toggleCompareRow = (runId: string) =>
    setCompareSelected((prev) => { const n = new Set(prev); n.has(runId) ? n.delete(runId) : n.add(runId); return n; });

  useEffect(() => {
    api.versions().then((v) => setVersions([...v].sort((a, b) => Date.parse(a.date) - Date.parse(b.date))))
      .catch((e) => setError(e.message));
  }, [versionsKey, refreshKey]);

  // Archived runs are out of the picture everywhere below: recommendation, trend, deltas, comparison.
  const activeVersions = useMemo(() => (versions ?? []).filter((v) => !v.archived), [versions]);
  const archivedVersions = useMemo(() => (versions ?? []).filter((v) => v.archived), [versions]);

  const compareRuns = useMemo(
    () => [...compareSelected].map((id) => activeVersions.find((v) => v.run_id === id)).filter(Boolean) as VersionSummary[],
    [compareSelected, activeVersions]
  );

  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const availableGroups = useMemo(() => {
    const s = new Set<string>();
    for (const v of activeVersions) for (const g of Object.keys(v.group_stats ?? {})) s.add(g);
    return [...s].sort();
  }, [activeVersions]);
  useEffect(() => {
    if (groupFilter && versions && !availableGroups.includes(groupFilter)) setGroupFilter(null);
  }, [availableGroups, groupFilter, versions]);

  const scoreOf = (v: VersionSummary, key: "avg_answer_marks" | "avg_material_marks" | "avg_total_time"): number | null => {
    if (!groupFilter) return (v[key] as number | null | undefined) ?? null;
    return (v.group_stats?.[groupFilter] as Record<string, number | null> | undefined)?.[key] ?? null;
  };

  // The recommendation is computed by the server from every non-archived run's saved scores each time
  // anything here changes, so archiving, deleting or re-running a version is reflected immediately.
  const [reco, setReco] = useState<RecoResult | null>(null);
  useEffect(() => {
    if (!versions) return;
    let stale = false;
    const t = window.setTimeout(() => {
      api.recommendation({ group: groupFilter, tolerance: overrides.tolerance, maxTime: overrides.maxTime })
        .then((r) => { if (!stale) setReco(r); })
        .catch(() => { if (!stale) setReco(null); });
    }, 250);
    return () => { stale = true; window.clearTimeout(t); };
  }, [versions, groupFilter, overrides]);
  const bestId = reco?.best ?? null;
  const isBest = (v: VersionSummary) => bestId !== null && String(v.version) === bestId;

  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 } | null>(null);
  // each header cycles: ascending, descending, back to default order
  const toggleSort = (key: SortKey) => setSort((s) => (s?.key !== key ? { key, dir: 1 } : s.dir === 1 ? { key, dir: -1 } : null));
  const prevOf = useMemo(() => {
    const m = new Map<VersionSummary, VersionSummary | undefined>();
    // deltas compare against the chronological predecessor among non-archived runs
    activeVersions.forEach((v, i, all) => m.set(v, i > 0 ? all[i - 1] : undefined));
    return m;
  }, [activeVersions]);
  const rows = useMemo(() => {
    if (!versions) return [];
    if (!sort) {
      // Default: newest first, with recommended pinned to top
      const byDate = [...activeVersions].sort((a, b) => Date.parse(b.date) - Date.parse(a.date));
      const idx = bestId === null ? -1 : byDate.findIndex((v) => String(v.version) === bestId);
      if (idx > 0) byDate.unshift(...byDate.splice(idx, 1));
      return byDate;
    }
    const val = (v: VersionSummary): number | null => {
      switch (sort.key) {
        case "version": return Number.isNaN(Number(v.version)) ? null : Number(v.version);
        case "date": return Date.parse(v.date);
        case "questions": return v.total_rows;
        case "answer": return v.avg_answer_marks;
        case "material": return v.avg_material_marks;
        case "time": return v.avg_total_time;
      }
    };
    return [...activeVersions].sort((a, b) => {
      const x = val(a), y = val(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x - y) * sort.dir;
    });
  }, [activeVersions, sort, bestId, versions]);

  const paging = usePaging(rows, `${sort?.key}${sort?.dir}${versionsKey}${groupFilter}`, 10);
  const archivedPaging = usePaging(archivedVersions, archivedVersions.length, 10);

  // best value per column, shown as a small "best" marker so the table can be scanned
  const bests = useMemo(() => {
    const ok = activeVersions.filter((v) => v.failed_rows === 0 && !v.stopped);
    const pick = (key: "avg_answer_marks" | "avg_material_marks" | "avg_total_time", fn: (...n: number[]) => number) => {
      const vals = ok.map((v) => scoreOf(v, key)).filter((x): x is number => x != null);
      return vals.length > 1 ? fn(...vals) : null;
    };
    return { answer: pick("avg_answer_marks", Math.max), material: pick("avg_material_marks", Math.max), time: pick("avg_total_time", Math.min) };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeVersions, groupFilter]);
  const latest = activeVersions[activeVersions.length - 1];

  // Changes and BEST marks are measured on the test cases the compared versions share, so a version that
  // ran extra cases is never judged on questions the others did not answer.
  type Metric = "answer" | "material" | "time";
  const hasShared = !!reco && Object.keys(reco.scores).length > 0;
  const sharedScore = (v: VersionSummary, key: Metric) => reco?.scores[String(v.version)]?.[key] ?? null;
  const partialOf = (v: VersionSummary) => reco?.partial.find((p) => p.version === String(v.version));
  const prevShared = (v: VersionSummary) => {
    for (let j = activeVersions.indexOf(v) - 1; j >= 0; j--) if (reco?.scores[String(activeVersions[j].version)]) return activeVersions[j];
    return undefined;
  };
  const deltaProps = (v: VersionSummary, key: Metric, field: "avg_answer_marks" | "avg_material_marks" | "avg_total_time") => {
    if (hasShared) {
      const p = prevShared(v);
      const cur = sharedScore(v, key);
      if (!p || cur == null) return { current: null, previous: null };
      return {
        current: cur, previous: sharedScore(p, key),
        title: `Change since v${p.version}, measured on the ${reco!.compared_cases} test cases both ran`,
      };
    }
    if (!reco) return { current: null, previous: null };
    const p = prevOf.get(v);
    return { current: scoreOf(v, field), previous: p ? scoreOf(p, field) : undefined };
  };
  const isBestFor = (v: VersionSummary, key: Metric, field: "avg_answer_marks" | "avg_material_marks" | "avg_total_time", legacy: number | null) => {
    if (hasShared) {
      const vals = Object.values(reco!.scores).map((x) => x[key]).filter((n): n is number => n != null);
      const cur = sharedScore(v, key);
      return vals.length > 1 && cur != null && cur === (key === "time" ? Math.min(...vals) : Math.max(...vals));
    }
    return v.failed_rows === 0 && legacy != null && scoreOf(v, field) === legacy;
  };
  /** For a version that ran more cases than were compared: what it scored on the shared ones, with the BEST
   *  mark beside it, because that mark was earned on the shared cases and not on the number shown above. */
  const sharedNote = (v: VersionSummary, key: Metric, best: boolean) => {
    const part = partialOf(v);
    const sc = sharedScore(v, key);
    if (!part || sc == null) return null;
    return (
      <span className="mono flex items-center gap-1.5 text-[10px] text-muted"
        title={`It ran ${part.ran} test cases; the comparison uses the ${part.compared} that every compared version ran`}>
        {key === "time" ? fmtSeconds(sc) : fmt(sc)} on the {part.compared} shared{best && <BestTag />}
      </span>
    );
  };
  const latestNote = !reco ? null : hasShared && !reco.scores[String(latest?.version)]
    ? "Not compared with earlier versions: it ran different test cases, so there is no change to show."
    : latest && partialOf(latest)
      ? `It ran ${partialOf(latest)!.ran} test cases; changes are measured on the ${partialOf(latest)!.compared} it shares with earlier versions.`
      : null;

  const trend = useMemo(() => activeVersions.map((v) => ({
    name: `v${v.version}`, "Answer quality": v.avg_answer_marks, "Context quality": v.avg_material_marks,
  })), [activeVersions]);
  const allNodes = useMemo(() => unionNodes(activeVersions), [activeVersions]);
  const timing = useMemo(() => activeVersions.map((v) => ({
    name: `v${v.version}`,
    // nodes a version did not run stay null so no bar is drawn for them
    ...Object.fromEntries(allNodes.map((n) => [nodeMeta(n).label, v.nodes.find((x) => x.name === n)?.avg ?? null])),
  })), [activeVersions, allNodes]);

  return (
    <>
      <TopBar />
    <div className="mx-auto max-w-[1280px] px-6 pb-16 pt-1">

      {run?.status === "failed" && (
        <div className="mt-6 flex items-center gap-3 border border-bad p-3.5 text-sm text-bad">
          Version {run.version} failed: {run.error}
          <button onClick={dismiss} className="mono ml-auto text-xs underline">dismiss</button>
        </div>
      )}

      {versions && versions.length > 0 && (
        <Recommendation
          reco={reco} versions={activeVersions} archivedCount={archivedVersions.length}
          overrides={overrides} onChange={updateOverrides} groupName={groupFilter}
        />
      )}

      {availableGroups.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">View by group:</span>
          {([null, ...availableGroups] as (string | null)[]).map((g) => (
            <button
              key={g ?? "__overall__"}
              onClick={() => setGroupFilter(g)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${groupFilter === g ? "border-brand bg-brand text-white" : "border-line text-muted hover:border-brand hover:text-brand"}`}
            >
              {g ?? "Overall"}
            </button>
          ))}
        </div>
      )}

      {latest && (
        <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="label">Latest run</h2>
          <span className="mono text-sm font-medium text-brand">v{latest.version}</span>
          <span className="text-xs text-muted">
            {plural(groupFilter ? latest.group_stats?.[groupFilter]?.total_rows ?? latest.total_rows : latest.total_rows, "test case")} · {fmtDate(latest.date)}
            {groupFilter ? ` · ${groupFilter}` : ""}
          </span>
          {latestNote && <span className="text-xs text-warn">{latestNote}</span>}
        </div>
      )}

      {latest && (
        <section className="mt-2 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label={<Term k="answer" />} accent="var(--brand)"
            value={<><Mark color="var(--hl-good)">{fmt(scoreOf(latest, "avg_answer_marks"))}</Mark><span className="mono text-xs text-muted">/10</span><Delta {...deltaProps(latest, "answer", "avg_answer_marks")} /></>}
            sub="average score out of 10, against the expected answers" />
          <Stat label={<Term k="context" />} accent="var(--sun)"
            value={<><Mark color="var(--hl)">{fmt(scoreOf(latest, "avg_material_marks"))}</Mark><span className="mono text-xs text-muted">/10</span><Delta {...deltaProps(latest, "material", "avg_material_marks")} /></>}
            sub="did it find the information it needed?" />
          <Stat label={<>Avg response time<Hint text={GLOSSARY.time.hint} /></>} accent="var(--coral)"
            value={<><Mark color="var(--hl-bad)">{fmtSeconds(scoreOf(latest, "avg_total_time"))}</Mark><Delta {...deltaProps(latest, "time", "avg_total_time")} invert digits={2} unit="s" /></>}
            sub="from question to final answer" />
          <Stat label="Versions evaluated" accent="var(--plum)" value={<Mark>{activeVersions.length}</Mark>}
            sub={`${plural(latest.total_rows, "test case")} in the latest run`} />
        </section>
      )}

      {activeVersions.length > 0 && (
        <section className="mt-3 grid gap-3 lg:grid-cols-2">
          <div className="card p-5">
            <h3 className="label">Quality trend{latest && (
              <> <span className="mono normal-case tracking-normal">· latest v{latest.version} · answer {fmt(scoreOf(latest, "avg_answer_marks"))} · context {fmt(scoreOf(latest, "avg_material_marks"))}</span></>
            )}</h3>
            <p className="mb-3 mt-1 text-xs text-muted">Average score out of 10 for each version</p>
            <div className="h-56">
              <ResponsiveContainer>
                <LineChart data={trend} margin={{ left: -20, right: 8, top: 8 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: "var(--muted)", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 10]} tick={{ fill: "var(--muted)", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend iconType="square" iconSize={9} wrapperStyle={{ fontSize: 12 }} />
                  <Line type="linear" dataKey="Answer quality" stroke="var(--coral)" strokeWidth={2.5} dot={{ r: 4, fill: "var(--coral)" }} />
                  <Line type="linear" dataKey="Context quality" stroke="var(--brand)" strokeWidth={2.5} dot={{ r: 4, fill: "var(--brand)" }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="card p-5">
            <h3 className="label">Where the time goes{latest && (
              <> <span className="mono normal-case tracking-normal">· latest v{latest.version} · avg {fmtSeconds(scoreOf(latest, "avg_total_time"))} per question</span></>
            )}</h3>
            <p className="mb-3 mt-1 text-xs text-muted">Average seconds each step of the assistant takes</p>
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={timing} margin={{ left: -20, right: 8, top: 8 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: "var(--muted)", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "var(--muted)", fontSize: 12 }} axisLine={false} tickLine={false} unit="s" />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--surface-2)" }} formatter={(v: number) => `${v.toFixed(2)}s`} />
                  <Legend iconType="square" iconSize={9} wrapperStyle={{ fontSize: 12 }} />
                  {allNodes.map((n) => <Bar key={n} dataKey={nodeMeta(n).label} fill={nodeMeta(n).color} radius={0} />)}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>
      )}

      {compareMode && compareRuns.length >= 2 && <ComparePanel runs={compareRuns} />}

      <section className="card mt-3 overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="font-serif text-xl font-medium">Versions</h2>
            <p className="text-xs text-muted">{compareMode ? "Click rows to select for comparison" : "Select a version to open the result for every question"}</p>
          </div>
          <div className="flex items-center gap-2">
            {compareMode && compareSelected.size >= 2 && (
              <span className="mono text-xs text-brand">{compareSelected.size} selected</span>
            )}
            <button
              onClick={() => setCompareMode((m) => !m)}
              className={`rounded border px-3 py-1.5 text-xs font-medium transition ${compareMode ? "border-brand bg-brand text-white" : "border-line text-muted hover:border-brand hover:text-brand"}`}
            >
              {compareMode ? "Exit compare" : "Compare"}
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
              <tr>
                {compareMode && <th className="w-10 px-3 py-3" />}
                <SortTh k="version" cur={sort} onSort={toggleSort} className="px-5">Version</SortTh>
                <SortTh k="date" cur={sort} onSort={toggleSort}>Executed</SortTh>
                <SortTh k="questions" cur={sort} onSort={toggleSort}>Questions</SortTh>
                <SortTh k="answer" cur={sort} onSort={toggleSort}><Term k="answer" avg /></SortTh>
                <SortTh k="material" cur={sort} onSort={toggleSort}><Term k="context" avg /></SortTh>
                <SortTh k="time" cur={sort} onSort={toggleSort}><Term k="time" avg /></SortTh>
                <th className="px-3 py-3 font-medium"><Term k="steps" /></th>
                <th className="px-3 py-3 font-medium">Actions</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {!versions && !error && <tr><td colSpan={9} className="px-5 py-12 text-center text-muted">Loading…</td></tr>}
              {error && <tr><td colSpan={9} className="px-5 py-12 text-center text-bad">Could not reach the evaluator backend: {error}</td></tr>}
              {versions && activeVersions.length === 0 && !run && (
                <tr><td colSpan={9} className="px-5 py-16 text-center">
                  <div className="font-serif text-lg">{versions.length === 0 ? "No runs yet" : "All versions are archived"}</div>
                  <div className="mt-1 text-sm text-muted">
                    {versions.length === 0 ? "Execute a session to record the first baseline." : "Unarchive one below, or execute a new session."}
                  </div>
                </td></tr>
              )}
              {paging.rows.map((v) => {
                const isSelected = compareSelected.has(v.run_id);
                return (
                  <tr key={String(v.version)}
                    onClick={compareMode ? () => toggleCompareRow(v.run_id) : () => nav(`/v/${v.version}`)}
                    className={`group cursor-pointer align-top transition hover:bg-surface-2 ${isSelected ? "bg-brand-soft" : ""}`}>
                    {compareMode && (
                      <td className="px-3 py-4 align-middle" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" className="accent-brand" checked={isSelected} onChange={() => toggleCompareRow(v.run_id)} />
                      </td>
                    )}
                    <td className="px-5 py-4" style={isBest(v) ? { boxShadow: "inset 5px 0 0 var(--brand)" } : undefined}>
                      <span className="mono text-[15px] font-medium text-brand">v{v.version}</span>
                      {isBest(v) && <div className="mono mt-1.5 text-[10px] uppercase tracking-wider text-brand">recommended</div>}
                      {v.stopped && <div className="mono mt-1.5 text-[11px] text-warn">stopped early</div>}
                      {v.failed_rows > 0 && <div className="mono mt-1.5 text-[11px] text-bad">{v.failed_rows} failed</div>}
                      {v.notes && <div className="mt-1 text-[12px] italic text-muted leading-snug max-w-[160px] line-clamp-2">{v.notes}</div>}
                    </td>
                    <td className="px-3 py-4 text-xs text-muted">
                      {fmtDate(v.date)}
                      {v.group_names && v.group_names.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {v.group_names.map((n) => (
                            <span key={n} className="inline-block rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-muted border border-line">{n}</span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="mono px-3 py-4">{v.total_rows}</td>
                    <td className="px-3 py-4"><div className="flex flex-col items-start gap-1"><ScorePill value={scoreOf(v, "avg_answer_marks")} /><Delta {...deltaProps(v, "answer", "avg_answer_marks")} />{sharedNote(v, "answer", isBestFor(v, "answer", "avg_answer_marks", bests.answer))}{!partialOf(v) && isBestFor(v, "answer", "avg_answer_marks", bests.answer) && <BestTag />}</div></td>
                    <td className="px-3 py-4"><div className="flex flex-col items-start gap-1"><ScorePill value={scoreOf(v, "avg_material_marks")} /><Delta {...deltaProps(v, "material", "avg_material_marks")} />{sharedNote(v, "material", isBestFor(v, "material", "avg_material_marks", bests.material))}{!partialOf(v) && isBestFor(v, "material", "avg_material_marks", bests.material) && <BestTag />}</div></td>
                    <td className="px-3 py-4"><div className="flex flex-col items-start gap-1"><div className="mono">{fmtSeconds(scoreOf(v, "avg_total_time"))}</div><Delta {...deltaProps(v, "time", "avg_total_time")} invert digits={2} unit="s" />{sharedNote(v, "time", isBestFor(v, "time", "avg_total_time", bests.time))}{!partialOf(v) && isBestFor(v, "time", "avg_total_time", bests.time) && <BestTag />}</div></td>
                    <td className="px-3 py-4"><NodeTimings v={v} compact /></td>
                    <td className="px-3 py-4 align-middle" onClick={(e) => e.stopPropagation()}>
                      {confirmDelete === v.run_id ? (
                        <span className="inline-flex items-center gap-1 text-xs">
                          <span className="text-muted">Sure?</span>
                          <button className="text-bad underline" onClick={() => { api.deleteRun(v.run_id).then(() => { setConfirmDelete(null); setRefreshKey((k) => k + 1); }).catch(() => {}); }}>Yes</button>
                          <span className="text-muted">/</span>
                          <button className="text-muted hover:text-fg" onClick={() => setConfirmDelete(null)}>No</button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2">
                          <button title="Hide from dashboard" className="text-xs text-muted hover:text-warn" onClick={() => { api.archiveRun(v.run_id).then(() => setRefreshKey((k) => k + 1)).catch(() => {}); }}>Archive</button>
                          <button className="text-xs text-bad hover:underline" onClick={() => setConfirmDelete(v.run_id)}>Delete</button>
                        </span>
                      )}
                    </td>
                    <td className="pr-4 text-lg text-muted group-hover:text-brand">›</td>
                  </tr>
                );
              })}
              {run?.status === "running" && (
                <tr className="bg-brand-soft align-middle">
                  <td className="px-5 py-5">
                    <span className="mono text-[15px] font-medium text-brand">v{run.version}</span>
                    <div className="mono mt-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-brand">
                      <span className="live-dot h-1.5 w-1.5 bg-brand" /> in progress
                    </div>
                  </td>
                  <td className="px-3 py-5 text-xs text-muted">{fmtDate(run.date)}<div className="mt-1 truncate">{run.dataset}</div></td>
                  <td colSpan={5} className="px-3 py-5">
                    <div className="mb-2 flex items-center justify-between text-sm">
                      <span className="mono">{run.done}/{run.total} graded</span>
                      <span className="mono text-muted">{run.total ? Math.round((run.done / run.total) * 100) : 0}%</span>
                    </div>
                    <ProgressBar done={run.done} total={run.total} />
                    <div className="mt-2 truncate text-xs text-muted">{run.current_question ? `now: ${run.current_question}` : "Starting…"}</div>
                  </td>
                  <td className="px-3 py-5 text-right">
                    <button onClick={requestStop}
                      className="rounded border border-bad px-3 py-1.5 text-xs font-medium text-bad hover:bg-bad hover:text-white transition">
                      Stop
                    </button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager p={paging} sizes={[10, 25, 50]} />
      </section>

      {archivedVersions.length > 0 && (
        <section className="mt-3">
          <button
            onClick={() => setShowArchived((s) => !s)}
            className="flex items-center gap-2 text-sm text-muted hover:text-fg mb-2"
          >
            <span>{showArchived ? "▼" : "▶"}</span>
            <span>Archived ({archivedVersions.length})</span>
          </button>
          {showArchived && (
            <div className="card overflow-hidden opacity-60">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] text-left text-sm">
                  <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
                    <tr>
                      <th className="px-5 py-3 font-medium">Version</th>
                      <th className="px-3 py-3 font-medium">Executed</th>
                      <th className="px-3 py-3 font-medium">Questions</th>
                      <th className="px-3 py-3 font-medium"><Term k="answer" avg /></th>
                      <th className="px-3 py-3 font-medium"><Term k="context" avg /></th>
                      <th className="px-3 py-3 font-medium"><Term k="time" avg /></th>
                      <th className="px-3 py-3 font-medium"><Term k="steps" /></th>
                      <th className="px-3 py-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {archivedPaging.rows.map((v) => (
                      <tr key={String(v.version)} onClick={() => nav(`/v/${v.version}`)} className="group cursor-pointer align-top transition hover:bg-surface-2">
                        <td className="px-5 py-4">
                          <span className="mono text-[15px] font-medium text-brand">v{v.version}</span>
                        </td>
                        <td className="px-3 py-4 text-xs text-muted">{fmtDate(v.date)}</td>
                        <td className="mono px-3 py-4">{v.total_rows}</td>
                        <td className="px-3 py-4"><ScorePill value={v.avg_answer_marks} /></td>
                        <td className="px-3 py-4"><ScorePill value={v.avg_material_marks} /></td>
                        <td className="px-3 py-4"><div className="mono">{fmtSeconds(v.avg_total_time)}</div></td>
                        <td className="px-3 py-4"><NodeTimings v={v} compact /></td>
                        <td className="px-3 py-4 align-middle" onClick={(e) => e.stopPropagation()}>
                          <button
                            title="Restore to dashboard"
                            className="text-xs text-muted hover:text-brand"
                            onClick={() => { api.unarchiveRun(v.run_id).then(() => setRefreshKey((k) => k + 1)).catch(() => {}); }}
                          >
                            Unarchive
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager p={archivedPaging} sizes={[10, 25, 50]} />
            </div>
          )}
        </section>
      )}

    </div>
    </>
  );
}

function SortTh({ k, cur, onSort, className = "px-3", children }: {
  k: SortKey; cur: { key: SortKey; dir: 1 | -1 } | null; onSort: (k: SortKey) => void; className?: string; children: React.ReactNode;
}) {
  const active = cur?.key === k;
  return (
    <th className={`${className} py-3 font-medium`} aria-sort={active ? (cur!.dir === 1 ? "ascending" : "descending") : "none"}>
      <button onClick={() => onSort(k)} className={`inline-flex items-center gap-1 uppercase tracking-[0.08em] hover:text-fg ${active ? "text-fg" : ""}`}>
        {children}
        <span className="mono w-3 text-[10px]">{active ? (cur!.dir === 1 ? "↑" : "↓") : "↕"}</span>
      </button>
    </th>
  );
}

const BestTag = () => <span className="mono text-[10px] uppercase tracking-wider text-brand">best</span>;

const TONE_COLOR = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)", none: "var(--muted)" } as const;

function ScoreCell({ value, star }: { value: number | null; star: boolean }) {
  if (value == null) return <span className="text-muted">—</span>;
  const color = TONE_COLOR[scoreTone(value)];
  return (
    <span className="mono text-sm font-medium" style={{ color }}>
      {value.toFixed(1)}
      {star && <span className="ml-1 text-[11px]" style={{ color: "var(--brand)" }}>★</span>}
    </span>
  );
}

function ComparePanel({ runs }: { runs: import("../api/types").VersionSummary[] }) {
  const allGroups = useMemo(() => {
    const s = new Set<string>();
    for (const v of runs) for (const g of (v.group_names ?? [])) s.add(g);
    return [...s].sort();
  }, [runs]);

  const commonGroups = useMemo(
    () => allGroups.filter((g) => runs.every((v) => v.group_stats?.[g] !== undefined)),
    [allGroups, runs]
  );

  const overallFor = (v: import("../api/types").VersionSummary): number | null => {
    if (commonGroups.length === 0) return v.avg_answer_marks;
    const vals = commonGroups.map((g) => v.group_stats?.[g]?.avg_answer_marks).filter((x): x is number => x != null);
    return vals.length > 0 ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : v.avg_answer_marks;
  };

  const bestVal = (vals: (number | null)[]) => {
    const ns = vals.filter((x): x is number => x != null);
    return ns.length >= 2 ? Math.max(...ns) : null;
  };

  const overallVals = runs.map(overallFor);
  const bestOverall = bestVal(overallVals);

  return (
    <section className="card mt-3 overflow-hidden">
      <div className="border-b border-line px-5 py-4">
        <h2 className="font-serif text-xl font-medium">Group Comparison</h2>
        <p className="mt-0.5 text-xs text-muted">
          Answer quality, out of 10 · ★ = best in row
          {commonGroups.length < allGroups.length && allGroups.length > 0 && " · Overall averages common groups only"}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
            <tr>
              <th className="min-w-[160px] px-5 py-3 font-medium">Group</th>
              {runs.map((v) => (
                <th key={v.run_id} className="px-5 py-3 text-center font-medium">
                  <div className="mono text-brand">v{v.version}</div>
                  {v.group_names && v.group_names.length > 0 && (
                    <div className="mt-0.5 text-[9px] normal-case tracking-normal text-muted">
                      {v.group_names.slice(0, 2).join(", ")}{v.group_names.length > 2 ? "…" : ""}
                    </div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {allGroups.map((group) => {
              const vals = runs.map((v) => v.group_stats?.[group]?.avg_answer_marks ?? null);
              const best = bestVal(vals);
              return (
                <tr key={group} className="align-middle">
                  <td className="px-5 py-3 text-[13px] font-medium">{group}</td>
                  {runs.map((v, i) => (
                    <td key={v.run_id} className="px-5 py-3 text-center">
                      <ScoreCell value={vals[i]} star={best != null && vals[i] === best} />
                    </td>
                  ))}
                </tr>
              );
            })}
            <tr className="align-middle bg-surface-2 font-medium">
              <td className="px-5 py-3 text-[13px]">
                Overall
                {commonGroups.length < allGroups.length && allGroups.length > 0 && (
                  <span className="ml-1.5 text-[10px] font-normal text-muted">(common groups)</span>
                )}
              </td>
              {runs.map((v, i) => (
                <td key={v.run_id} className="px-5 py-3 text-center">
                  <ScoreCell value={overallVals[i]} star={bestOverall != null && overallVals[i] === bestOverall} />
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
