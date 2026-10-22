import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { ThemeToggle } from "../components/ThemeToggle";
import { Breadcrumbs, type Crumb } from "./Breadcrumbs";
import { ExecuteModal } from "./ExecuteModal";
import { useRun } from "../RunContext";

/**
 * Frozen header: title on the left; Execute button, theme switch and sign-out on the right.
 * Pass `crumbs` (everything after "Home") on any page below the dashboard to show the location trail.
 */
export function TopBar({ action, crumbs }: { action?: ReactNode; crumbs?: Crumb[] }) {
  const { user, logout } = useAuth();
  const { run } = useRun();
  const [modal, setModal] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg pt-[5px]">
      <div className="mx-auto flex max-w-[1280px] items-center justify-between gap-4 px-6 py-3">
        <div className="flex items-center gap-6">
          <Link to="/" className="block no-underline">
            <h1 className="font-serif text-[26px] font-medium leading-none tracking-tight text-fg">
              RAG <span className="hl">Evaluator</span>
            </h1>
            <p className="mt-1.5 text-xs text-muted">Evaluation runs, scored version by version</p>
          </Link>
          <nav className="hidden items-center gap-4 md:flex">
            <Link to="/groups" className="text-sm text-muted transition hover:text-fg">Groups</Link>
            <Link to="/test-cases" className="text-sm text-muted transition hover:text-fg">Test Cases</Link>
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
