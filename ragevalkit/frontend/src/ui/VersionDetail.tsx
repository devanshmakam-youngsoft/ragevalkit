import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { Mark, NodeTimings, ScorePill, Stat } from "./parts";
import { ChatTurn, GroupChips } from "./GroupChips";
import { GLOSSARY, Hint, Term } from "./Hint";
import { Pager, usePaging } from "./Pager";
import { TopBar } from "./TopBar";
import { fmt, fmtDay, fmtSeconds, fmtTime, nodeMeta, plural } from "../lib";
import { type ResultRow, type VersionDetail as Detail, type VersionSummary } from "../types";

type SortKey = "order" | "answer_marks" | "material_marks" | "total_time_taken";
type ScoreTier = "all" | "high" | "mid" | "low";

const ALL = "__all__";
const NONE = "__none__";

const avg = (values: (number | null | undefined)[]): number | null => {
  const v = values.filter((x): x is number => x != null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
};

function duration(seconds: number) {
  const s = Math.round(seconds);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

export default function VersionDetail() {
  const { version = "" } = useParams();
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [group, setGroup] = useState(ALL);
  const [scoreTier, setScoreTier] = useState<ScoreTier>("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "order", dir: 1 });
  const [open, setOpen] = useState<ResultRow | null>(null);

  useEffect(() => {
    api.version(version).then(setData).catch((e) => setError(e.message));
  }, [version]);

  const types = useMemo(() => ["all", ...Array.from(new Set((data?.rows ?? []).map((r) => r.type)))], [data]);

  const bands = useMemo(() => {
    const rows = data?.rows ?? [];
    const high = rows.filter((r) => (r.answer_marks ?? 0) >= 8).length;
    const mid = rows.filter((r) => (r.answer_marks ?? 0) >= 5 && (r.answer_marks ?? 0) < 8).length;
    const low = rows.filter((r) => (r.answer_marks ?? 0) < 5).length;
    return { high, mid, low, total: rows.length };
  }, [data]);

  // Per-group scores straight from the results: a test case in several groups counts in each of them.
  const groupScores = useMemo(() => {
    const rows = data?.rows ?? [];
    const names = [...new Set(rows.flatMap((r) => r.groups ?? []))].sort((a, b) => a.localeCompare(b));
    const summarise = (rs: ResultRow[]) => ({
      cases: rs.length,
      answer: avg(rs.map((r) => r.answer_marks)),
      material: avg(rs.map((r) => r.material_marks)),
      time: avg(rs.map((r) => r.total_time_taken)),
    });
    const list = names.map((name) => ({ key: name, name, ...summarise(rows.filter((r) => r.groups?.includes(name))) }));
    const ungrouped = rows.filter((r) => !(r.groups?.length));
    if (list.length > 0 && ungrouped.length > 0) list.push({ key: NONE, name: "No group", ...summarise(ungrouped) });
    return list;
  }, [data]);

  const rows = useMemo(() => {
    const filtered = (data?.rows ?? []).map((r, i) => ({ r, i })).filter(({ r }) => {
      const score = r.answer_marks ?? 0;
      const tierOk = scoreTier === "all" || (scoreTier === "high" && score >= 8) || (scoreTier === "mid" && score >= 5 && score < 8) || (scoreTier === "low" && score < 5);
      const groupOk = group === ALL || (group === NONE ? !(r.groups?.length) : !!r.groups?.includes(group));
      return (type === "all" || r.type === type) && tierOk && groupOk &&
        (!query || `${r.question} ${r.generated_answer} ${r.expected_answer}`.toLowerCase().includes(query.toLowerCase()));
    });
    const k = sort.key;
    if (k !== "order") {
      filtered.sort((a, b) => ((a.r[k] ?? -1) - (b.r[k] ?? -1)) * sort.dir);
    }
    return filtered;
  }, [data, type, scoreTier, query, sort, group]);
  const paging = usePaging(rows, `${type}|${scoreTier}|${query}|${group}|${sort.key}${sort.dir}`, 25);

  if (error) return <Shell version={version}><p className="text-bad">{error}</p></Shell>;
  if (!data) return <Shell version={version}><p className="text-muted">Loading…</p></Shell>;
  const s = data.summary;
  const filtering = rows.length !== data.rows.length;

  const th = (key: SortKey, label: React.ReactNode) => (
    <th className="px-3 py-3 font-medium">
      <button className="inline-flex items-center gap-1 uppercase hover:text-fg" onClick={() => setSort((p) => ({ key, dir: p.key === key ? (-p.dir as 1 | -1) : 1 }))}>
        {label}{sort.key === key && (sort.dir === 1 ? "↑" : "↓")}
      </button>
    </th>
  );

  return (
    <Shell version={version}>
      {/* Which run is this? The date gets its own prominent place. */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-[32px] font-medium leading-none tracking-tight">Version {s.version}</h1>
          <div className="mt-4">
            <div className="label">Executed</div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
              <span className="font-serif text-[26px] leading-none">{fmtDay(s.date)}</span>
              <span className="text-sm text-muted">at {fmtTime(s.date)}</span>
              {s.stopped && <span className="rounded bg-surface-2 px-2 py-0.5 text-xs font-medium text-warn">stopped early</span>}
            </div>
          </div>
        </div>
        <a href={api.downloadUrl(version)} className="inline-flex items-center gap-2 rounded border border-line bg-surface px-4 py-2.5 text-sm font-medium hover:bg-surface-2">
          Download .xlsx
        </a>
      </div>

      <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-3 border-y border-line py-3.5 text-sm">
        <Meta label="Test set">
          {s.group_names && s.group_names.length > 0
            ? <span className="flex flex-wrap gap-1">{s.group_names.map((n) => (
                <span key={n} className="rounded border border-line bg-surface-2 px-1.5 py-0.5 text-xs font-medium">{n}</span>))}</span>
            : s.dataset}
        </Meta>
        <Meta label="Questions">{s.total_rows}</Meta>
        <Meta label="Ran for">{duration(s.duration_seconds)}</Meta>
        {s.notes && <Meta label="Run note"><span className="italic">{s.notes}</span></Meta>}
      </dl>

      <section className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label={<Term k="answer" />} value={<ScorePill value={s.avg_answer_marks} />} />
        <Stat label={<Term k="context" />} value={<ScorePill value={s.avg_material_marks} />} />
        <Stat label={<Term k="keywords" />} accent="var(--sun)" value={<Mark>{fmt(s.avg_keyword_recall, 2)}</Mark>} sub="of the key words are present" />
        <Stat label={<Term k="wording" />} accent="var(--coral)" value={<Mark>{fmt(s.avg_bm25_score, 2)}</Mark>} sub="similar phrasing · 0 to 1" />
        <Stat label={<Term k="meaning" />} accent="var(--plum)" value={<Mark>{fmt(s.avg_semantic_similarity, 2)}</Mark>} sub="similar meaning · 0 to 1" />
      </section>

      {bands.total > 0 && (
        <div className="card mt-4 px-5 py-4">
          <h3 className="label mb-3"><Term k="tiers" /></h3>
          <div className="flex h-6 overflow-hidden rounded text-xs font-medium text-white">
            {bands.high > 0 && <div style={{ width: `${(bands.high / bands.total) * 100}%` }} className="flex items-center justify-center bg-good">{bands.high}</div>}
            {bands.mid > 0 && <div style={{ width: `${(bands.mid / bands.total) * 100}%` }} className="flex items-center justify-center bg-warn">{bands.mid}</div>}
            {bands.low > 0 && <div style={{ width: `${(bands.low / bands.total) * 100}%` }} className="flex items-center justify-center bg-bad">{bands.low}</div>}
          </div>
          <p className="mt-2 flex flex-wrap gap-x-4 text-xs text-muted">
            <span><span className="mr-1 inline-block h-2 w-2 bg-good" />Strong (8–10): {bands.high}</span>
            <span><span className="mr-1 inline-block h-2 w-2 bg-warn" />Fair (5–7): {bands.mid}</span>
            <span><span className="mr-1 inline-block h-2 w-2 bg-bad" />Weak (0–4): {bands.low}</span>
          </p>
        </div>
      )}

      <section className="mt-4 grid gap-4 lg:grid-cols-[1fr_360px]">
        <Insights summary={s} />
        <div className="card p-5">
          <h3 className="label mb-3"><Term k="steps" /> <span className="mono normal-case tracking-normal">· avg {fmtSeconds(s.avg_total_time)} per question</span></h3>
          <NodeTimings v={s} />
        </div>
      </section>

      {groupScores.length > 0 && (
        <section className="card mt-4 overflow-hidden">
          <div className="border-b border-line px-5 py-4">
            <h3 className="label"><Term k="groupScores" /></h3>
            <p className="mt-1 text-xs text-muted">
              Click a group to show only its results. A test case that is in several groups counts in each of them, and once in the scores above.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
                <tr>
                  <th className="px-5 py-2.5 font-medium">Group</th>
                  <th className="px-3 py-2.5 font-medium">Test cases</th>
                  <th className="px-3 py-2.5 font-medium"><Term k="answer" /></th>
                  <th className="px-3 py-2.5 font-medium"><Term k="context" /></th>
                  <th className="px-3 py-2.5 font-medium"><Term k="time" /></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {groupScores.map((g) => (
                  <tr key={g.key} onClick={() => setGroup(group === g.key ? ALL : g.key)}
                    className={`cursor-pointer hover:bg-surface-2 ${group === g.key ? "bg-brand-soft" : ""}`}>
                    <td className="px-5 py-2.5 font-medium">{g.name}</td>
                    <td className="mono px-3 py-2.5 text-xs">{g.cases}</td>
                    <td className="mono px-3 py-2.5">{fmt(g.answer)}</td>
                    <td className="mono px-3 py-2.5">{fmt(g.material)}</td>
                    <td className="mono px-3 py-2.5">{fmtSeconds(g.time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card mt-4 overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-4">
          <h2 className="mr-auto font-serif text-xl font-medium">
            Results <span className="mono text-xs text-muted">{rows.length}{filtering ? ` of ${data.rows.length}` : ""}</span>
            <span className="ml-3 text-xs font-normal text-muted">· click a row for full details</span>
          </h2>
          <div className="relative">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search questions & answers"
              className="w-52 rounded border border-line bg-surface-2 py-2 px-3 text-sm outline-none focus:border-brand" />
          </div>
          {groupScores.length > 0 && (
            <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Filter by group"
              className="rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none">
              <option value={ALL}>All groups</option>
              {groupScores.map((g) => <option key={g.key} value={g.key}>{g.name} ({g.cases})</option>)}
            </select>
          )}
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter by question type"
            className="rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none">
            {types.map((t) => <option key={t} value={t}>{t === "all" ? "All types" : t}</option>)}
          </select>
          <div className="flex gap-1">
            {([["all", "All"], ["high", "Strong"], ["mid", "Fair"], ["low", "Weak"]] as [ScoreTier, string][]).map(([tier, label]) => (
              <button key={tier} onClick={() => setScoreTier(tier)}
                className={`rounded border px-2.5 py-1.5 text-xs font-medium transition ${
                  scoreTier === tier ? "border-brand bg-brand text-white" : "border-line text-muted hover:border-brand hover:text-brand"
                }`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        {filtering && rows.length > 0 && (
          <p className="border-b border-line bg-surface-2 px-5 py-2 text-xs text-muted">
            Average for these {plural(rows.length, "result")}:{" "}
            <b className="text-fg">{GLOSSARY.answer.label} {fmt(avg(rows.map(({ r }) => r.answer_marks)))}</b> ·{" "}
            <b className="text-fg">{GLOSSARY.context.label} {fmt(avg(rows.map(({ r }) => r.material_marks)))}</b> ·{" "}
            <b className="text-fg">{fmtSeconds(avg(rows.map(({ r }) => r.total_time_taken)))}</b>
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] text-left text-sm">
            <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
              <tr>
                <th className="px-3 py-3 font-medium">Chat</th>
                <th className="px-3 py-3 font-medium">Turn</th>
                <th className="px-3 py-3 font-medium">Question</th>
                <th className="px-3 py-3 font-medium">Groups</th>
                <th className="px-3 py-3 font-medium">Type</th>
                {th("answer_marks", <Term k="answer" />)}
                {th("material_marks", <Term k="context" />)}
                {th("total_time_taken", <Term k="time" />)}
                <th className="px-3 py-3 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {paging.rows.map(({ r, i }) => (
                <tr key={i} onClick={() => setOpen(r)} className="cursor-pointer align-top hover:bg-surface-2">
                  <td className="mono max-w-[120px] truncate px-3 py-3.5 text-xs" title={r.chat_id}>{r.chat_id}</td>
                  <td className="mono px-3 py-3.5 text-xs text-muted">{r.turn_no}</td>
                  <td className="max-w-[360px] px-3 py-3.5">
                    <div className="line-clamp-2 font-medium">{r.question}</div>
                    <div className="mt-1 line-clamp-1 text-xs text-muted">{r.generated_answer ?? "No answer generated"}</div>
                  </td>
                  <td className="px-3 py-3.5"><GroupChips groups={(r.groups ?? []).map((name) => ({ group_id: name, name }))} max={2} /></td>
                  <td className="px-3 py-3.5"><span className="mono text-[11px] text-muted">{r.type}</span></td>
                  <td className="px-3 py-3.5">
                    <div className="flex items-center gap-1">
                      {(r.answer_marks ?? 0) < 4 && <span className="text-bad text-xs" title="Needs attention">⚠</span>}
                      <ScorePill value={r.answer_marks} digits={0} />
                    </div>
                  </td>
                  <td className="px-3 py-3.5">
                    {r.material_marks == null ? <span className="text-xs text-muted">n/a</span> : <ScorePill value={r.material_marks} digits={0} />}
                    {r.source_match != null && (
                      <div className={`mt-1 text-[10px] font-medium ${r.source_match ? "text-good" : "text-bad"}`}>
                        {r.source_match ? "✓ sources" : "✗ sources"}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3.5 tabular-nums text-muted">{fmtSeconds(r.total_time_taken)}</td>
                  <td className="px-3 py-3.5">
                    {r.flags && Object.keys(r.flags).length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(r.flags).map(([k, v]) => (
                          <span key={k} className="inline-flex items-center rounded bg-surface-2 px-1.5 py-0.5 text-[10px]">
                            <span className="text-muted">{k}:</span>&nbsp;<span className="font-medium">{v}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={9} className="px-5 py-12 text-center text-muted">No rows match the filters.</td></tr>}
            </tbody>
          </table>
        </div>
        <Pager p={paging} sizes={[25, 50, 100]} />
      </section>

      {open && <RowDrawer row={open} onClose={() => setOpen(null)} />}
    </Shell>
  );
}

function Shell({ version, children }: { version: string; children: React.ReactNode }) {
  return (
    <>
      <TopBar crumbs={[{ label: `v${version}` }]} />
      <div className="mx-auto max-w-[1280px] px-6 pb-16 pt-5">
      {children}
      </div>
    </>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}

/** What went wrong and what to try next. Runs saved before structured summaries show their text as bullets. */
function Insights({ summary }: { summary: VersionSummary }) {
  const ins = summary.insights;
  const legacy = !ins && summary.comment
    ? summary.comment.split(/\n+|(?<=[.!?])\s+/).map((t) => t.replace(/^[•\-*]\s*/, "").trim()).filter(Boolean)
    : [];
  if (!ins && legacy.length === 0) return <div className="card p-5 text-sm text-muted">No summary was written for this run.</div>;

  const list = (items: string[], dot: string) => (
    <ul className="mt-2 space-y-2 text-sm leading-relaxed">
      {items.map((t, i) => (
        <li key={i} className="flex gap-2.5"><span className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: dot }} /><span>{t}</span></li>
      ))}
    </ul>
  );
  return (
    <div className="card p-5">
      <h3 className="label">Watch-outs &amp; suggestions</h3>
      {ins ? (
        <div className="mt-3 grid gap-5 sm:grid-cols-2">
          <div>
            <div className="text-sm font-semibold" style={{ color: "var(--warn)" }}>Watch-outs</div>
            {ins.pitfalls.length ? list(ins.pitfalls, "var(--warn)") : <p className="mt-2 text-sm text-muted">Nothing stood out.</p>}
          </div>
          <div>
            <div className="text-sm font-semibold text-brand">Suggestions</div>
            {ins.suggestions.length ? list(ins.suggestions, "var(--brand)") : <p className="mt-2 text-sm text-muted">None.</p>}
          </div>
        </div>
      ) : (
        <>
          {list(legacy, "var(--muted)")}
          <p className="mt-3 text-xs text-muted">This run was saved before watch-outs and suggestions were separated.</p>
        </>
      )}
    </div>
  );
}

function Block({ title, children, mono = false }: { title: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="mt-5">
      <div className="label mb-1.5">{title}</div>
      <div className={`whitespace-pre-wrap rounded bg-surface-2 p-3.5 text-sm leading-relaxed ${mono ? "max-h-72 overflow-auto font-mono text-xs" : ""}`}>{children}</div>
    </div>
  );
}

/**
 * One question's result, in the order a reviewer reads it: the question, how it scored at a glance,
 * what was answered against what was expected, why it scored that way, then the supporting evidence
 * (sources, retrieved text) and the technical detail last.
 */
function RowDrawer({ row, onClose }: { row: ResultRow; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const sourcesLine = row.source_match == null ? null : row.source_match;
  const hasRemarks = !!(row.answer_remarks || row.material_remarks);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={onClose}>
      <aside className="slide-in h-full w-full max-w-[640px] overflow-y-auto border-l border-line bg-surface p-6 " onMouseDown={(e) => e.stopPropagation()}>
        {/* 1. The question */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-end gap-4 text-xs font-medium text-muted">
              <ChatTurn chatId={row.chat_id} turnNo={row.turn_no} />
              <span className="pb-0.5">{row.type}</span>
              {(row.groups?.length ?? 0) > 0 && (
                <span className="pb-0.5"><GroupChips groups={row.groups!.map((name) => ({ group_id: name, name }))} max={4} /></span>
              )}
            </div>
            <h2 className="mt-2 font-serif text-xl font-medium leading-snug">{row.question}</h2>
          </div>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        {/* 2. The verdict at a glance */}
        <div className="mt-5 grid grid-cols-3 gap-3">
          <div className="rounded border border-line p-3.5">
            <div className="mb-1.5 text-xs text-muted"><Term k="answer" /></div>
            <ScorePill value={row.answer_marks} digits={0} />
          </div>
          <div className="rounded border border-line p-3.5">
            <div className="mb-1.5 text-xs text-muted"><Term k="context" /></div>
            {row.material_marks == null ? <span className="text-sm text-muted">n/a</span> : <ScorePill value={row.material_marks} digits={0} />}
          </div>
          <div className="rounded border border-line p-3.5">
            <div className="mb-1.5 text-xs text-muted"><Term k="sources" /></div>
            {sourcesLine == null
              ? <span className="text-sm text-muted">not checked</span>
              : <span className={`text-sm font-medium ${sourcesLine ? "text-good" : "text-bad"}`}>{sourcesLine ? "✓ all found" : "✗ some missing"}</span>}
          </div>
        </div>

        {/* 3. What was answered, against what was expected */}
        <Block title="Generated answer">{row.generated_answer ?? "Generation failed"}</Block>
        <Block title="Expected answer">{row.expected_answer || "—"}</Block>

        {/* 4. Why it scored that way */}
        {hasRemarks && (
          <div className="mt-5">
            <div className="label mb-1.5">Why these scores</div>
            <div className="space-y-2 rounded border border-line p-3.5 text-sm leading-relaxed">
              {row.answer_remarks && <p><span className="font-semibold">{GLOSSARY.answer.label}:</span> {row.answer_remarks}</p>}
              {row.material_remarks && <p><span className="font-semibold">{GLOSSARY.context.label}:</span> {row.material_remarks}</p>}
            </div>
          </div>
        )}

        {/* 5. Evidence: sources, then the retrieved text itself */}
        {(row.source_match != null || (row.sources?.length ?? 0) > 0) && (
          <div className="mt-5">
            <div className="label mb-1.5">Sources</div>
            {row.source_match != null && (
              <div className="space-y-1 text-sm">
                {(row.matched_sources?.length ?? 0) > 0 && <div className="text-good">✓ Found: <span className="text-fg">{row.matched_sources!.join(", ")}</span></div>}
                {(row.missing_sources?.length ?? 0) > 0 && <div className="text-bad">✗ Missing: <span className="text-fg">{row.missing_sources!.join(", ")}</span></div>}
              </div>
            )}
            {(row.sources?.length ?? 0) > 0 && (
              <div className="mt-2 whitespace-pre-wrap rounded bg-surface-2 p-3 text-xs leading-relaxed text-muted">
                <span className="font-medium text-fg">Retrieved by the assistant:</span>{"\n"}{row.sources.join("\n")}
              </div>
            )}
          </div>
        )}
        {row.material && (
          <details className="mt-5 rounded border border-line">
            <summary className="cursor-pointer select-none px-3.5 py-2.5 text-sm font-medium hover:bg-surface-2">
              Retrieved text <span className="font-normal text-muted">· the passages the assistant was given ({row.material.length.toLocaleString()} characters)</span>
            </summary>
            <div className="max-h-72 overflow-auto whitespace-pre-wrap border-t border-line bg-surface-2 p-3.5 font-mono text-xs leading-relaxed">{row.material}</div>
          </details>
        )}

        {/* 6. Technical detail */}
        <div className="mt-5 grid grid-cols-3 gap-3 text-center">
          {([["keywords", row.keyword_recall], ["wording", row.bm25_score], ["meaning", row.semantic_similarity]] as const).map(([k, v]) => (
            <div key={k} className="rounded border border-line p-3">
              <div className="num text-xl">{fmt(v, 2)}</div>
              <div className="text-[11px] text-muted"><Term k={k} /></div>
            </div>
          ))}
        </div>

        <div className="mt-5">
          <div className="label mb-1.5"><Term k="steps" /> · {fmtSeconds(row.total_time_taken)} total</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(row.node_timings ?? {}).map(([n, secs]) => (
              <span key={n} className="inline-flex items-center gap-1.5 rounded bg-surface-2 px-2.5 py-1 text-xs">
                <span className="h-2 w-2" style={{ background: nodeMeta(n).color }} />{nodeMeta(n).label}
                <b className="tabular-nums">{fmtSeconds(secs)}</b>
              </span>
            ))}
          </div>
        </div>

        {row.flags && Object.keys(row.flags).length > 0 && (
          <div className="mt-5">
            <div className="label mb-1.5">Notes</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(row.flags).map(([k, v]) => (
                <span key={k} className="inline-flex items-center gap-1 rounded border border-line bg-surface-2 px-2.5 py-1 text-xs">
                  <span className="text-muted">{k}</span>
                  <span className="mx-1 text-border">·</span>
                  <span className="font-medium">{v}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
