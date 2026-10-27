import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ThemeToggle } from "./ThemeToggle";
import { Breadcrumbs, type Crumb } from "./Breadcrumbs";
import { ExecuteModal } from "../dialogs/ExecuteModal";
import { useRun } from "../context/RunContext";

/**
 * Frozen header: title on the left; Execute button, theme switch and sign-out on the right.
 * Three sections: Dashboard (runs and versions), Test Cases (cases, groups and import) and Help (the guides).
 * Pass `crumbs` (the whole trail, starting from the page's own section) on any page below a top-level section.
 */
export function TopBar({ action, crumbs }: { action?: ReactNode; crumbs?: Crumb[] }) {
  const { user, logout } = useAuth();
  const { run } = useRun();
  const [modal, setModal] = useState(false);
  const { pathname } = useLocation();
  const inTestCases = pathname.startsWith("/test-cases");
  const inHelp = pathname.startsWith("/help");

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg pt-[5px]">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-x-4 gap-y-2 px-6 py-3">
        <div className="flex items-center gap-6">
          <Link to="/" className="block no-underline">
            <h1 className="font-serif text-[26px] font-medium leading-none tracking-tight text-fg">
              RAG <span className="hl">Evaluator</span>
            </h1>
            <p className="mt-1.5 text-xs text-muted">Evaluation runs, scored version by version</p>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-5">
            {([["Dashboard", "/", !inTestCases && !inHelp], ["Test Cases", "/test-cases", inTestCases], ["Help", "/help", inHelp]] as const).map(([label, to, on]) => (
              <Link key={to} to={to} aria-current={on ? "page" : undefined}
                className={`border-b-2 py-1 text-sm font-medium transition ${on ? "border-brand text-fg" : "border-transparent text-muted hover:text-fg"}`}>
                {label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {action}
          <button
            onClick={() => setModal(true)}
            disabled={run?.status === "running"}
            className="rounded bg-brand px-5 py-2 text-sm font-semibold text-white transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Execute session
          </button>
          <ThemeToggle />
          {user && user !== "_guest_" ? (
            <button onClick={logout} title={`Signed in as ${user}`} className="mono text-xs text-muted hover:text-fg">
              {user} · sign out
            </button>
          ) : user === "_guest_" ? (
            <span className="mono text-xs text-muted">guest</span>
          ) : null}
        </div>
      </div>
      {crumbs && <Breadcrumbs items={crumbs} />}
      {modal && <ExecuteModal onClose={() => setModal(false)} />}
    </header>
  );
}
