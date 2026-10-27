import { useState } from "react";

/** The technical version of a problem, hidden until someone asks for it. */
export function TechnicalDetails({ text, label = "technical details" }: { text: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  if (!text) return null;

  const copy = () => {
    navigator.clipboard?.writeText(text).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); }).catch(() => undefined);
  };
  return (
    <div className="mt-1.5">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="text-xs text-muted underline decoration-dotted hover:text-fg">
        {open ? `Hide ${label}` : `Show ${label}`}
      </button>
      {open && (
        <div className="mt-1.5">
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-2 p-3 text-[11px] leading-relaxed text-fg">{text}</pre>
          <button onClick={copy} className="mt-1 text-xs text-muted hover:text-fg">{copied ? "Copied" : "Copy"}</button>
        </div>
      )}
    </div>
  );
}
