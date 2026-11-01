import { useEffect, useState } from "react";

export interface Paging<T> {
  rows: T[];
  page: number;
  pages: number;
  size: number;
  total: number;
  setPage: (p: number) => void;
  setSize: (s: number) => void;
}

/**
 * Client-side paging for a list. `resetKey` sends the list back to page 1 whenever it changes
 * (a new filter, sort or search), so you never land on a page that no longer exists.
 */
export function usePaging<T>(items: T[], resetKey: unknown, initialSize = 25): Paging<T> {
  const [size, setSize] = useState(initialSize);
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(items.length / size));
  useEffect(() => setPage(1), [resetKey, size]);
  const current = Math.min(page, pages);
  return {
    rows: items.slice((current - 1) * size, current * size),
    page: current, pages, size, total: items.length, setPage, setSize,
  };
}

/** "1–25 of 140", a page-size picker and Prev / Next. Hidden while everything fits on one small page. */
export function Pager<T>({ p, sizes = [10, 25, 50, 100] }: { p: Paging<T>; sizes?: number[] }) {
  if (p.total <= Math.min(...sizes)) return null;
  const from = (p.page - 1) * p.size + 1;
  const to = Math.min(p.page * p.size, p.total);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3 text-sm">
      <span className="mono text-xs text-muted">{from}–{to} of {p.total}</span>
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-xs text-muted">
          Rows per page
          <select value={p.size} onChange={(e) => p.setSize(Number(e.target.value))}
            className="rounded border border-line bg-surface-2 px-2 py-1 text-xs text-fg outline-none">
            {sizes.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <button disabled={p.page === 1} onClick={() => p.setPage(p.page - 1)}
          className="text-muted hover:text-fg disabled:cursor-not-allowed disabled:opacity-30">← Prev</button>
        <span className="mono text-xs text-muted">{p.page} / {p.pages}</span>
        <button disabled={p.page === p.pages} onClick={() => p.setPage(p.page + 1)}
          className="text-muted hover:text-fg disabled:cursor-not-allowed disabled:opacity-30">Next →</button>
      </div>
    </div>
  );
}
