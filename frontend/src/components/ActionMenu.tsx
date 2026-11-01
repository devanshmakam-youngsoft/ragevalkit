import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export type MenuItem = {
  label: string;
  /** A short second line under the label. */
  hint?: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
};

const ITEM_HEIGHT = 40;   // used only to decide whether the menu opens upwards near the bottom of the window

/**
 * A button that opens a small menu of actions. Without `label` it is the "more actions" (three dots) button used
 * at the end of a table row; with `label` it is a full button (`primary` for the brand colour).
 *
 * The menu is drawn on the page itself, not inside its parent, so a table or card that clips its content cannot
 * cut it off. It closes on outside click, Escape, scroll or resize, and works with the arrow keys.
 */
export function ActionMenu({ items, label, primary = false, ariaLabel = "More actions" }: {
  items: MenuItem[];
  label?: ReactNode;
  primary?: boolean;
  ariaLabel?: string;
}) {
  const [place, setPlace] = useState<{ top?: number; bottom?: number; right: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const open = place !== null;

  const close = () => setPlace(null);
  const toggle = () => {
    if (open || !button.current) return close();
    const r = button.current.getBoundingClientRect();
    const right = document.documentElement.clientWidth - r.right;      // not innerWidth: that includes the page scrollbar
    const flip = r.bottom + items.length * ITEM_HEIGHT + 16 > window.innerHeight && r.top > window.innerHeight - r.bottom;
    setPlace(flip ? { bottom: window.innerHeight - r.top + 4, right } : { top: r.bottom + 4, right });
  };

  useEffect(() => {
    if (!open) return;
    const enabled = () => Array.from(menu.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([disabled])") ?? []);
    enabled()[0]?.focus();
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !button.current?.contains(t)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); close(); button.current?.focus(); return; }
      if (e.key === "Tab") return close();
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const list = enabled();
      const at = list.indexOf(document.activeElement as HTMLElement);
      list[(at + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length]?.focus();
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);

  const triggerClass = label === undefined
    ? "rounded p-1.5 text-muted transition hover:bg-surface-2 hover:text-fg"
    : primary
      ? "inline-flex items-center gap-2 rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:brightness-110"
      : "inline-flex items-center gap-2 rounded border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-2";

  return (
    <>
      <button ref={button} type="button" onClick={toggle} aria-haspopup="menu" aria-expanded={open}
        aria-label={label === undefined ? ariaLabel : undefined} className={triggerClass}>
        {label === undefined ? (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <circle cx="3" cy="8" r="1.4" /><circle cx="8" cy="8" r="1.4" /><circle cx="13" cy="8" r="1.4" />
          </svg>
        ) : (
          <>
            {label}
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M2 3.5 5 6.5 8 3.5" />
            </svg>
          </>
        )}
      </button>
      {place && createPortal(
        <div ref={menu} role="menu" style={{ position: "fixed", ...place }}
          className="pop-in z-[70] min-w-[210px] overflow-hidden rounded border border-line bg-surface py-1 shadow-lg">
          {items.map((item) => (
            <button key={item.label} role="menuitem" type="button" disabled={item.disabled}
              onClick={() => { close(); item.onSelect(); }}
              className={`block w-full px-4 py-2 text-left text-sm outline-none transition focus:bg-surface-2 enabled:hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40 ${
                item.danger ? "text-bad" : "text-fg"
              }`}>
              <span className="block font-medium">{item.label}</span>
              {item.hint && <span className="mt-0.5 block text-xs font-normal text-muted">{item.hint}</span>}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
