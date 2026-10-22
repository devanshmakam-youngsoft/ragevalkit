import { useEffect, useState } from "react";

type Mode = "light" | "dark";

function systemMode(): Mode {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function stored(): Mode | null {
  try {
    const v = localStorage.getItem("theme");
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null; // storage can be blocked
  }
}

/** Light/Dark switch (lives in the frozen top bar). Follows the OS until the user picks one. */
export function ThemeToggle() {
  const [mode, setMode] = useState<Mode>(() => stored() ?? systemMode());

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  const pick = (m: Mode) => {
    setMode(m);
    try {
      localStorage.setItem("theme", m);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="flex overflow-hidden rounded border border-line bg-surface text-xs" role="group" aria-label="Colour theme">
      {(["light", "dark"] as Mode[]).map((m) => (
        <button key={m} onClick={() => pick(m)} aria-pressed={mode === m}
          className={`mono px-3 py-1.5 capitalize transition ${mode === m ? "bg-fg text-bg" : "text-muted hover:text-fg"}`}>
          {m}
        </button>
      ))}
    </div>
  );
}

/** Applies the saved (or OS) theme on pages that have no toggle, e.g. the login page. */
export function ThemeFollower() {
  useEffect(() => {
    document.documentElement.dataset.theme = stored() ?? systemMode();
  }, []);
  return null;
}
