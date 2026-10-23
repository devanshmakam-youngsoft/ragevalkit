import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { plural } from "../lib";
import type { GenBatch, GenItem, GenLimits } from "../types";

const DESCRIPTIONS: Record<string, string> = {
  direct: "The answer is stated plainly in one place.",
  indirect: "Asked in everyday words, or as a situation, rather than the document's own wording.",
  multipart: "One question with several parts, answered from different places in the document.",
  multiturn: "A short conversation: each follow-up only makes sense with the earlier answers.",
};

/** A model-facing rejection reason, in words a person can act on. */
function friendly(reason: string): string {
  const r = reason.toLowerCase();
  if (r.includes("does not point at any sentence") || r.includes("appears in the passages")) return "it could not show which sentences of the document the answer comes from, even after retries";
  if (r.includes("on its own, so") || r.includes("repeats the earlier question") || r.includes("depends_on")) return "it could not write a follow-up that really depends on the earlier answers, even after retries";
  if (r.includes("too similar")) return "it kept repeating a question that had already been written";
  if (r.includes("stand on its own")) return "it kept referring to “the document” instead of asking a self-contained question";
  if (r.includes("four or more words") || r.includes("evidence's own words")) return "it could not phrase the question indirectly enough";
  if (r.includes("both passage")) return "it could not combine two different parts of the document";
  if (r.includes("could not be reached")) return `the AI model returned an error (${reason.replace(/^.*could not be reached:\s*/i, "").slice(0, 160)})`;
  return reason;
}

const mb = (bytes: number) => (bytes / (1024 * 1024)).toFixed(bytes > 10 * 1024 * 1024 ? 0 : 1);

function timeLeft(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.parse(iso) - Date.now()) / 60000));
  return minutes >= 120 ? `${Math.round(minutes / 60)} hours` : minutes >= 60 ? "an hour" : `${minutes} minutes`;
}

/** One generated item: a question, or a whole conversation, with its evidence. Text is editable in place. */
function ItemCard({ item, locked, onSave, onRemove }: {
  item: GenItem;
  locked: boolean;
  onSave: (turns: { question: string; expected_answer: string }[]) => Promise<void>;
  onRemove: () => void;
}) {
  const [draft, setDraft] = useState(item.turns.map((t) => ({ question: t.question, expected_answer: t.expected_answer })));
  const [state, setState] = useState<"" | "saved" | string>("");
  useEffect(() => setDraft(item.turns.map((t) => ({ question: t.question, expected_answer: t.expected_answer }))), [item]);

  const dirty = draft.some((d, i) => d.question !== item.turns[i].question || d.expected_answer !== item.turns[i].expected_answer);
  async function save() {
    if (!dirty) return;
    try {
      await onSave(draft);
      setState("saved");
      window.setTimeout(() => setState(""), 1800);
    } catch (e) {
      setState((e as Error).message);
    }
  }
  const set = (i: number, key: "question" | "expected_answer", value: string) =>
    setDraft((d) => d.map((t, j) => (j === i ? { ...t, [key]: value } : t)));
  const box = "w-full resize-y rounded border border-transparent bg-surface-2 px-2.5 py-1.5 text-sm outline-none hover:border-line focus:border-brand";

  return (
    <article className="rounded border border-line p-4">
      <div className="mb-2 flex items-center gap-3 text-xs text-muted">
        <span className="mono">{item.file}</span>
        {item.turns.length > 1 && <span>conversation · {item.turns.length} turns</span>}
        <span className="ml-auto" aria-live="polite">
          {state === "saved" ? <span className="text-good">Saved</span> : state ? <span className="text-bad">{state}</span> : null}
        </span>
        <button onClick={onRemove} disabled={locked} className="text-bad hover:underline disabled:opacity-40">Remove</button>
      </div>
      <div className="space-y-3">
        {item.turns.map((turn, i) => (
          <div key={i}>
            {item.turns.length > 1 && (
              <div className="mb-1 flex flex-wrap items-baseline gap-x-3">
                <span className="label">Turn {i + 1}</span>
                {turn.needs_context && <span className="text-xs text-muted">builds on: {turn.needs_context}</span>}
              </div>
            )}
            <label className="sr-only" htmlFor={`${item.item_id}-q${i}`}>Question</label>
            <textarea id={`${item.item_id}-q${i}`} value={draft[i]?.question ?? ""} rows={2} disabled={locked}
              onChange={(e) => set(i, "question", e.target.value)} onBlur={save}
              className={`${box} font-medium`} />
            <label className="sr-only" htmlFor={`${item.item_id}-a${i}`}>Expected answer</label>
            <textarea id={`${item.item_id}-a${i}`} value={draft[i]?.expected_answer ?? ""} rows={2} disabled={locked}
              onChange={(e) => set(i, "expected_answer", e.target.value)} onBlur={save}
              className={`${box} mt-1 text-muted`} />
            <details className="mt-1 text-xs">
              <summary className="cursor-pointer select-none text-brand hover:underline">
                Evidence · {[...new Set(turn.evidence.map((e) => `${e.file} ${e.page}`))].join(", ")}
              </summary>
              <div className="mt-1.5 space-y-1.5">
                {turn.evidence.map((e, k) => (
                  <blockquote key={k} className="border-l-2 border-line pl-3 italic text-muted">
                    “{e.quote}” <span className="not-italic">— {e.page}</span>
                  </blockquote>
                ))}
              </div>
            </details>
          </div>
        ))}
      </div>
    </article>
  );
}

/**
 * Write test cases from documents. Pick files and how many questions, wait while they are written (they are
 * saved on the server as they appear, so closing this or losing the network loses nothing), then review and
 * approve. Anything not approved is deleted after a day.
 */
export function GenerateDialog({ resumeId, onClose, onDone }: {
  resumeId?: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [limits, setLimits] = useState<GenLimits | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [perCategory, setPerCategory] = useState(3);
  const [cats, setCats] = useState<Set<string>>(new Set(["direct", "indirect", "multipart", "multiturn"]));
  const [turns, setTurns] = useState(3);
  const [drag, setDrag] = useState(false);
  const [batchId, setBatchId] = useState<string | null>(resumeId ?? null);
  const [batch, setBatch] = useState<GenBatch | null>(null);
  const [offline, setOffline] = useState(false);
  const [gone, setGone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<string>("");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.generateLimits().then((l) => { setLimits(l); setPerCategory(l.per_category_default); setTurns(l.turns_default); })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, busy]);

  // Follow the job. A failed request never stops this: the server keeps working and keeps what it has.
  useEffect(() => {
    if (!batchId) return;
    let stop = false;
    let timer = 0;
    const tick = async () => {
      try {
        const b = await api.generateGet(batchId);
        if (stop) return;
        setBatch(b);
        setOffline(false);
        if (b.status === "running") timer = window.setTimeout(tick, 1500);
      } catch (e) {
        if (stop) return;
        if (/no longer available/i.test((e as Error).message)) { setGone(true); return; }
        setOffline(true);
        timer = window.setTimeout(tick, 3000);
      }
    };
    tick();
    return () => { stop = true; window.clearTimeout(timer); };
  }, [batchId]);

  useEffect(() => {
    if (batch && !tab) setTab(batch.options.categories[0] ?? "");
  }, [batch, tab]);

  const labels = useMemo(() => Object.fromEntries((limits?.categories ?? []).map((c) => [c.key, c.label])), [limits]);
  const fileProblems = useMemo(() => {
    if (!limits) return [];
    const out: string[] = [];
    if (files.length > limits.max_files) out.push(`Choose at most ${limits.max_files} documents.`);
    for (const f of files) {
      if (!limits.formats.some((ext) => f.name.toLowerCase().endsWith("." + ext) || (ext === "md" && f.name.toLowerCase().endsWith(".markdown")))) {
        out.push(`${f.name}: only PDF, Word (.docx), TXT and Markdown files can be used.`);
      } else if (f.size > limits.max_file_mb * 1024 * 1024) {
        out.push(`${f.name} is ${mb(f.size)} MB; the limit is ${limits.max_file_mb} MB per file.`);
      }
    }
    return out;
  }, [files, limits]);

  const total = [...cats].reduce((n, c) => n + perCategory * (c === "multiturn" ? turns : 1), 0);
  const addFiles = (list: FileList | null) => {
    if (!list) return;
    // copy now: the input's FileList empties as soon as the input is reset, before React runs the updater below
    const picked = Array.from(list);
    setFiles((prev) => [...prev, ...picked.filter((f) => !prev.some((p) => p.name === f.name && p.size === f.size))]);
  };

  async function start() {
    setBusy(true); setError("");
    try {
      const b = await api.generateStart(files, { perCategory, categories: [...cats], turns });
      setBatch(null); setTab(""); setGone(false);
      setBatchId(b.batch_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!batchId) return;
    setBusy(true); setError("");
    try {
      const r = await api.generateApprove(batchId);
      onDone(`${plural(r.cases, "test case")} added to ${r.groups.join(", ")}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function discard() {
    if (!batchId) return;
    setBusy(true);
    try { await api.generateDiscard(batchId); onDone("Generated test cases discarded"); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  }

  const status = batch?.status;
  const items = batch?.items ?? [];
  const cases = items.reduce((n, i) => n + i.turns.length, 0);
  const tabs = batch?.options.categories ?? [];
  const progress = batch && batch.total_tasks ? Math.round((batch.done_tasks / batch.total_tasks) * 100) : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={() => !busy && onClose()}>
      <div className="card pop-in flex max-h-[94vh] w-full max-w-4xl flex-col bg-surface" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 className="font-serif text-2xl font-medium">Generate test cases from documents</h2>
            <p className="mt-0.5 text-sm text-muted">
              {!batchId ? "Upload documents and choose what to write." : status === "running" ? "Writing questions…" : status === "failed" ? "Nothing could be written." : "Review the questions, then add them to the library."}
            </p>
          </div>
          <button onClick={onClose} disabled={busy} className="mono text-xs text-muted hover:text-fg">esc</button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {/* ---------- 1. documents and settings ---------- */}
          {!batchId && limits && (
            <>
              <div
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
                onClick={() => input.current?.click()}
                className={`flex cursor-pointer flex-col items-center gap-1 rounded border-2 border-dashed p-7 text-center transition ${drag ? "border-brand bg-brand-soft" : "border-line hover:border-brand/60"}`}
              >
                <span className="text-base font-medium">Drop documents here, or click to choose</span>
                <span className="text-xs text-muted">PDF, Word, TXT or Markdown · up to {limits.max_files} files · {limits.max_file_mb} MB each</span>
                <input ref={input} type="file" multiple hidden accept=".pdf,.docx,.txt,.md,.markdown"
                  onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
              </div>
              {files.length > 0 && (
                <ul className="mt-3 divide-y divide-line rounded border border-line text-sm">
                  {files.map((f) => (
                    <li key={f.name + f.size} className="flex items-center gap-3 px-3 py-2">
                      <span className="flex-1 truncate">{f.name}</span>
                      <span className="mono text-xs text-muted">{mb(f.size)} MB</span>
                      <button onClick={() => setFiles((p) => p.filter((x) => x !== f))} className="text-xs text-bad hover:underline">Remove</button>
                    </li>
                  ))}
                </ul>
              )}
              {fileProblems.length > 0 && <ul className="mt-2 space-y-0.5 text-xs text-bad" role="alert">{fileProblems.map((p) => <li key={p}>{p}</li>)}</ul>}

              <div className="label mb-2 mt-6">What to write</div>
              <div className="grid gap-2 sm:grid-cols-2">
                {limits.categories.map((c) => (
                  <label key={c.key} className={`flex cursor-pointer items-start gap-3 rounded border p-3 text-sm ${cats.has(c.key) ? "border-brand bg-brand-soft" : "border-line"}`}>
                    <input type="checkbox" checked={cats.has(c.key)} className="mt-0.5 accent-brand"
                      onChange={() => setCats((prev) => { const n = new Set(prev); if (n.has(c.key)) n.delete(c.key); else n.add(c.key); return n; })} />
                    <span><span className="font-medium">{c.label}</span><span className="block text-xs text-muted">{DESCRIPTIONS[c.key]}</span></span>
                  </label>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
                <label className="flex items-center gap-2">
                  Questions in each category
                  <input type="number" min={1} max={limits.per_category_max} value={perCategory}
                    onChange={(e) => setPerCategory(Math.min(limits.per_category_max, Math.max(1, Number(e.target.value) || 1)))}
                    className="mono w-16 rounded border border-line bg-surface-2 px-2 py-1.5 outline-none focus:border-brand" />
                </label>
                {cats.has("multiturn") && (
                  <label className="flex items-center gap-2">
                    Turns per conversation
                    <select value={turns} onChange={(e) => setTurns(Number(e.target.value))}
                      className="rounded border border-line bg-surface-2 px-2 py-1.5 outline-none">
                      {[2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </label>
                )}
              </div>
              <p className="mt-3 text-sm">
                This will write about <b>{plural(total, "test case")}</b>
                {cats.has("multiturn") && <span className="text-muted"> ({plural(perCategory, "conversation")} of {turns} turns count as {perCategory * turns})</span>},
                shared across your {plural(Math.max(1, files.length), "document")} and grouped by category.
              </p>
              <p className="mt-2 rounded bg-surface-2 px-3 py-2 text-xs text-muted">
                The text of your documents is sent to <b className="text-fg">{limits.model}</b> to write the questions. The files themselves are not kept.
              </p>
            </>
          )}

          {/* ---------- 2. writing ---------- */}
          {batchId && !gone && (!batch || status === "running") && (
            <div className="py-4">
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-medium">{batch && batch.total_tasks ? `Writing questions · ${batch.done_tasks} of ${batch.total_tasks}` : "Reading your documents…"}</span>
                <span className="mono text-muted">{progress}%</span>
              </div>
              <div className="mt-2 h-2 w-full bg-line"><div className="h-full bg-brand transition-all duration-500" style={{ width: `${Math.max(progress, 3)}%` }} /></div>
              {offline && <p className="mt-3 rounded border border-warn/60 px-3 py-2 text-sm text-warn" role="status">Connection lost — nothing is lost: your questions are being saved on the server. Reconnecting…</p>}
              {batch && (
                <ul className="mt-4 space-y-1 text-sm">
                  {batch.files.map((f) => (
                    <li key={f.name} className={f.error ? "text-bad" : "text-muted"}>
                      <span className="text-fg">{f.name}</span>{" "}
                      {f.error ? `— ${f.error}` : `— ${f.pages ? `${f.pages} pages, ` : ""}${plural(f.passages ?? 0, "passage")} read`}
                    </li>
                  ))}
                </ul>
              )}
              {items.length > 0 && (
                <p className="mt-4 text-sm text-muted">
                  Written so far: {tabs.map((c) => `${labels[c] ?? c} ${items.filter((i) => i.category === c).length}`).join(" · ")}
                </p>
              )}
              <p className="mt-4 text-xs text-muted">You can close this window: the questions keep being written and are saved, and a banner on the Test Cases page brings you back to review them.</p>
            </div>
          )}

          {gone && <p className="py-8 text-center text-sm text-muted">These generated test cases are no longer available — unapproved ones are deleted after {limits?.ttl_hours ?? 24} hours.</p>}

          {/* ---------- failed ---------- */}
          {batch && !gone && status === "failed" && (
            <div className="py-4 text-sm">
              <p className="rounded border border-bad p-3 text-bad" role="alert">{batch.error || "Nothing could be written."}</p>
              {batch.files.some((f) => f.error) && (
                <ul className="mt-3 space-y-1">{batch.files.filter((f) => f.error).map((f) => <li key={f.name}><b>{f.name}</b> — {f.error}</li>)}</ul>
              )}
            </div>
          )}

          {/* ---------- 3. review ---------- */}
          {batch && !gone && status !== "running" && status !== "failed" && (
            <>
              {status !== "ready" && (
                <p className="mb-3 rounded bg-surface-2 px-3 py-2 text-sm text-muted">
                  {status === "cancelled" ? "Writing was stopped." : "Writing was interrupted."} What was already written is below.
                </p>
              )}
              <div className="mb-3 flex flex-wrap gap-1 border-b border-line">
                {tabs.map((c) => {
                  const n = items.filter((i) => i.category === c).length;
                  return (
                    <button key={c} onClick={() => setTab(c)}
                      className={`-mb-px border-b-2 px-3 pb-2 text-sm font-medium ${tab === c ? "border-brand text-fg" : "border-transparent text-muted hover:text-fg"}`}>
                      {labels[c] ?? c} <span className="mono text-xs text-muted">{n}</span>
                    </button>
                  );
                })}
              </div>
              <p className="mb-3 text-xs text-muted">{DESCRIPTIONS[tab]} Edit any text directly; open “Evidence” to check it against the document.</p>
              <div className="space-y-3">
                {items.filter((i) => i.category === tab).map((item) => (
                  <ItemCard key={item.item_id} item={item} locked={busy}
                    onSave={async (t) => {
                      const updated = await api.generateEditItem(batch.batch_id, item.item_id, t);
                      setBatch((b) => b && { ...b, items: b.items.map((x) => (x.item_id === item.item_id ? { ...x, turns: updated.turns } : x)) });
                    }}
                    onRemove={async () => {
                      await api.generateRemoveItem(batch.batch_id, item.item_id);
                      setBatch((b) => b && { ...b, items: b.items.filter((x) => x.item_id !== item.item_id) });
                    }} />
                ))}
                {items.filter((i) => i.category === tab).length === 0 && <p className="py-6 text-center text-sm text-muted">Nothing in this category.</p>}
              </div>
              {batch.errors.length > 0 && (
                <details className="mt-4 text-xs text-muted">
                  <summary className="cursor-pointer text-warn">{plural(batch.errors.length, "question")} could not be written</summary>
                  <ul className="mt-1.5 space-y-1">{batch.errors.map((e, i) => <li key={i}>{labels[e.category] ?? e.category} · {e.file}: {friendly(e.reason)}</li>)}</ul>
                </details>
              )}
            </>
          )}

          {error && <p className="mt-4 rounded border border-bad p-3 text-sm text-bad" role="alert">{error}</p>}
        </div>

        {/* ---------- footer ---------- */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-6 py-4">
          {!batchId && (
            <>
              <span className="text-xs text-muted">{files.length === 0 ? "Add at least one document." : `${plural(files.length, "document")} ready.`}</span>
              <button onClick={start} disabled={busy || files.length === 0 || fileProblems.length > 0 || cats.size === 0}
                className="rounded bg-brand px-5 py-2 text-sm font-medium text-white disabled:opacity-40 enabled:hover:brightness-110">
                {busy ? "Uploading…" : "Generate"}
              </button>
            </>
          )}
          {batchId && !gone && (!batch || status === "running") && (
            <>
              <button onClick={onClose} className="rounded px-4 py-2 text-sm font-medium text-muted hover:bg-surface-2">Close and keep going</button>
              <button onClick={() => api.generateCancel(batchId).catch(() => undefined)} className="rounded border border-line px-4 py-2 text-sm hover:bg-surface-2">Stop writing</button>
            </>
          )}
          {gone && <button onClick={onClose} className="ml-auto rounded bg-brand px-5 py-2 text-sm font-medium text-white">Close</button>}
          {batch && !gone && status === "failed" && (
            <>
              <button onClick={discard} disabled={busy} className="rounded px-4 py-2 text-sm text-muted hover:bg-surface-2">Discard</button>
              <button onClick={() => { setBatchId(null); setBatch(null); setTab(""); }} className="rounded bg-brand px-5 py-2 text-sm font-medium text-white">Try again</button>
            </>
          )}
          {batch && !gone && status !== "running" && status !== "failed" && (
            <>
              <div className="flex items-center gap-3 text-xs text-muted">
                {confirmDiscard ? (
                  <span className="flex items-center gap-2">
                    <span className="text-bad">Delete all {plural(cases, "test case")} you haven't added?</span>
                    <button onClick={discard} disabled={busy} className="font-semibold text-bad hover:underline">Delete</button>
                    <button onClick={() => setConfirmDiscard(false)} className="hover:underline">Keep</button>
                  </span>
                ) : (
                  <button onClick={() => setConfirmDiscard(true)} disabled={busy} className="text-bad hover:underline">Discard all</button>
                )}
                <span>Not added within {timeLeft(batch.expires_at)}? They are deleted.</span>
              </div>
              <button onClick={approve} disabled={busy || cases === 0}
                className="rounded bg-brand px-5 py-2 text-sm font-medium text-white disabled:opacity-40 enabled:hover:brightness-110">
                {busy ? "Adding…" : `Add ${plural(cases, "test case")}`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
