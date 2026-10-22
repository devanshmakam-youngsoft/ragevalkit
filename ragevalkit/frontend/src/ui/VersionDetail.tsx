import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { Mark, NodeTimings, ScorePill, Stat } from "./parts";
import { ChatTurn } from "./GroupChips";
import { TopBar } from "./TopBar";
import { fmt, fmtDate, fmtSeconds, nodeMeta } from "../lib";
import { type ResultRow, type VersionDetail as Detail } from "../types";

type SortKey = "order" | "answer_marks" | "material_marks" | "total_time_taken";
type ScoreTier = "all" | "high" | "mid" | "low";

export default function VersionDetail() {
  const { version = "" } = useParams();
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
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

  const rows = useMemo(() => {
    const filtered = (data?.rows ?? []).map((r, i) => ({ r, i })).filter(({ r }) => {
      const score = r.answer_marks ?? 0;
      const tierOk = scoreTier === "all" || (scoreTier === "high" && score >= 8) || (scoreTier === "mid" && score >= 5 && score < 8) || (scoreTier === "low" && score < 5);
      return (type === "all" || r.type === type) && tierOk &&
        (!query || `${r.question} ${r.generated_answer} ${r.expected_answer}`.toLowerCase().includes(query.toLowerCase()));
    });
    const k = sort.key;
    if (k !== "order") {
      filtered.sort((a, b) => ((a.r[k] ?? -1) - (b.r[k] ?? -1)) * sort.dir);
    }
    return filtered;
  }, [data, type, scoreTier, query, sort]);

  if (error) return <Shell version={version}><p className="text-bad">{error}</p></Shell>;
  if (!data) return <Shell version={version}><p className="text-muted">Loading…</p></Shell>;
  const s = data.summary;

  const th = (key: SortKey, label: string) => (
    <th className="px-3 py-3 font-medium">
      <button className="inline-flex items-center gap-1 uppercase hover:text-fg" onClick={() => setSort((p) => ({ key, dir: p.key === key ? (-p.dir as 1 | -1) : 1 }))}>
        {label}{sort.key === key && (sort.dir === 1 ? "↑" : "↓")}
      </button>
    </th>
  );

  return (
    <Shell version={version}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-[32px] font-medium leading-none tracking-tight">Version {s.version}</h1>
          <p className="mono mt-2 text-xs text-muted">{fmtDate(s.date)} · {s.dataset} · {s.total_rows} questions · ran for {Math.round(s.duration_seconds)}s</p>
        </div>
        <a href={api.downloadUrl(version)} className="inline-flex items-center gap-2 rounded border border-line bg-surface px-4 py-2.5 text-sm font-medium hover:bg-surface-2">
          Download .xlsx
        </a>
      </div>

      <section className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label="Answer marks" value={<ScorePill value={s.avg_answer_marks} />} />
        <Stat label="Material marks" value={<ScorePill value={s.avg_material_marks} />} />
        <Stat label="Keyword recall" accent="var(--sun)" value={<Mark>{fmt(s.avg_keyword_recall, 2)}</Mark>} sub="expected keywords found" />
        <Stat label="BM25 match" accent="var(--coral)" value={<Mark>{fmt(s.avg_bm25_score, 2)}</Mark>} sub="lexical, 0–1" />
        <Stat label="Semantic similarity" accent="var(--plum)" value={<Mark>{fmt(s.avg_semantic_similarity, 2)}</Mark>} sub="embedding cosine" />
      </section>

      {bands.total > 0 && (
        <div className="card mt-4 px-5 py-4">
          <h3 className="label mb-3">Answer score distribution</h3>
          <div className="flex h-6 overflow-hidden rounded text-xs font-medium text-white">
            {bands.high > 0 && <div style={{ width: `${(bands.high / bands.total) * 100}%` }} className="flex items-center justify-center bg-good">{bands.high}</div>}
            {bands.mid > 0 && <div style={{ width: `${(bands.mid / bands.total) * 100}%` }} className="flex items-center justify-center bg-warn">{bands.mid}</div>}
            {bands.low > 0 && <div style={{ width: `${(bands.low / bands.total) * 100}%` }} className="flex items-center justify-center bg-bad">{bands.low}</div>}
          </div>
          <p className="mt-2 text-xs text-muted">🟢 High ≥8 ({bands.high}) · 🟡 Mid 5–7 ({bands.mid}) · 🔴 Low &lt;5 ({bands.low})</p>
        </div>
      )}

      <section className="mt-4 grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="card p-5">
          <h3 className="label">How this version behaved</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted">{s.comment}</p>
        </div>
        <div className="card p-5">
          <h3 className="label mb-3">Node timings <span className="mono normal-case tracking-normal">· avg {fmtSeconds(s.avg_total_time)}</span></h3>
          <NodeTimings v={s} />
        </div>
      </section>

      <section className="card mt-4 overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-4">
          <h2 className="mr-auto font-serif text-xl font-medium">
            Results <span className="mono text-xs text-muted">{rows.length}</span>
            <span className="ml-3 text-xs font-normal text-muted">· click a row for full details</span>
          </h2>
          <div className="relative">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search questions & answers"
              className="w-52 rounded border border-line bg-surface-2 py-2 px-3 text-sm outline-none focus:border-brand" />
          </div>
          <select value={type} onChange={(e) => setType(e.target.value)} className="rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none">
            {types.map((t) => <option key={t} value={t}>{t === "all" ? "All types" : t}</option>)}
          </select>
          <div className="flex gap-1">
            {([["all", "All"], ["high", "🟢 High"], ["mid", "🟡 Mid"], ["low", "🔴 Low"]] as [ScoreTier, string][]).map(([tier, label]) => (
              <button key={tier} onClick={() => setScoreTier(tier)}
                className={`rounded border px-2.5 py-1.5 text-xs font-medium transition ${
                  scoreTier === tier ? "border-brand bg-brand text-white" : "border-line text-muted hover:border-brand hover:text-brand"
                }`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
              <tr>
                <th className="px-3 py-3 font-medium">Chat</th>
                <th className="px-3 py-3 font-medium">Turn</th>
                <th className="px-3 py-3 font-medium">Question</th>
                <th className="px-3 py-3 font-medium">Type</th>
                {th("answer_marks", "Answer")}
                {th("material_marks", "Material")}
                {th("total_time_taken", "Time")}
                <th className="px-3 py-3 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map(({ r, i }) => (
                <tr key={i} onClick={() => setOpen(r)} className="cursor-pointer align-top hover:bg-surface-2">
                  <td className="mono max-w-[120px] truncate px-3 py-3.5 text-xs" title={r.chat_id}>{r.chat_id}</td>
                  <td className="mono px-3 py-3.5 text-xs text-muted">{r.turn_no}</td>
                  <td className="max-w-[400px] px-3 py-3.5">
                    <div className="line-clamp-2 font-medium">{r.question}</div>
                    <div className="mt-1 line-clamp-1 text-xs text-muted">{r.generated_answer ?? "No answer generated"}</div>
                  </td>
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
              {rows.length === 0 && <tr><td colSpan={8} className="px-5 py-12 text-center text-muted">No rows match the filters.</td></tr>}
            </tbody>
          </table>
        </div>
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

function Block({ title, children, mono = false }: { title: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="mt-5">
      <div className="label mb-1.5">{title}</div>
      <div className={`whitespace-pre-wrap rounded bg-surface-2 p-3.5 text-sm leading-relaxed ${mono ? "max-h-72 overflow-auto font-mono text-xs" : ""}`}>{children}</div>
    </div>
  );
}

function RowDrawer({ row, onClose }: { row: ResultRow; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={onClose}>
      <aside className="slide-in h-full w-full max-w-[640px] overflow-y-auto border-l border-line bg-surface p-6 " onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-end gap-4 text-xs font-medium text-muted">
              <ChatTurn chatId={row.chat_id} turnNo={row.turn_no} />
              <span>{row.type}</span>
            </div>
            <h2 className="mt-1 font-serif text-xl font-medium leading-snug">{row.question}</h2>
          </div>
          <button onClick={onClose} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded border border-line p-3.5">
            <div className="mb-1.5 text-xs text-muted">Answer marks</div><ScorePill value={row.answer_marks} digits={0} />
            <p className="mt-2 text-xs leading-relaxed text-fg">{row.answer_remarks}</p>
          </div>
          <div className="rounded border border-line p-3.5">
            <div className="mb-1.5 text-xs text-muted">Material marks</div>
            {row.material_marks == null ? <span className="text-sm text-muted">n/a</span> : <ScorePill value={row.material_marks} digits={0} />}
            <p className="mt-2 text-xs leading-relaxed text-fg">{row.material_remarks}</p>
          </div>
        </div>

        {row.material && <Block title="Retrieved context" mono>{row.material}</Block>}

        <Block title="Generated answer">{row.generated_answer ?? "Generation failed"}</Block>
        <Block title="Expected answer">{row.expected_answer || "—"}</Block>
        {row.sources?.length > 0 && <Block title="Sources">{row.sources.join("\n")}</Block>}

        {row.source_match != null && (
          <div className="mt-5">
            <div className="label mb-1.5">Source check</div>
            <div className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-sm font-medium ${row.source_match ? "bg-surface-2 text-good" : "bg-surface-2 text-bad"}`}>
              {row.source_match ? "✓ All expected sources retrieved" : "✗ Missing expected sources"}
            </div>
            {(row.matched_sources?.length ?? 0) > 0 && (
              <div className="mt-2 text-xs text-muted">Matched: {row.matched_sources!.join(", ")}</div>
            )}
            {(row.missing_sources?.length ?? 0) > 0 && (
              <div className="mt-1 text-xs text-bad">Missing: {row.missing_sources!.join(", ")}</div>
            )}
          </div>
        )}

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

        <div className="mt-5 grid grid-cols-3 gap-3 text-center">
          {[["Keyword recall", row.keyword_recall], ["BM25", row.bm25_score], ["Semantic sim.", row.semantic_similarity]].map(([l, v]) => (
            <div key={l as string} className="rounded border border-line p-3"><div className="num text-xl">{fmt(v as number | null, 2)}</div><div className="text-[11px] text-muted">{l as string}</div></div>
          ))}
        </div>

        <div className="mt-5">
          <div className="label mb-1.5">Node timings · {fmtSeconds(row.total_time_taken)} total</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(row.node_timings ?? {}).map(([n, secs]) => (
              <span key={n} className="inline-flex items-center gap-1.5 rounded bg-surface-2 px-2.5 py-1 text-xs">
                <span className="h-2 w-2" style={{ background: nodeMeta(n).color }} />{nodeMeta(n).label}
                <b className="tabular-nums">{fmtSeconds(secs)}</b>
              </span>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
