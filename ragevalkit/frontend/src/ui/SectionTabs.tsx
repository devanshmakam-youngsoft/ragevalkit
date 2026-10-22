import { Link } from "react-router-dom";

const TABS = [
  { key: "all", label: "All test cases", to: "/test-cases" },
  { key: "groups", label: "Groups", to: "/test-cases/groups" },
] as const;

/** The two views inside the Test Cases section: every case, or the groups that organise them. */
export function SectionTabs({ active }: { active: "all" | "groups" }) {
  return (
    <nav aria-label="Test cases sections" className="mb-5 flex gap-6 border-b border-line">
      {TABS.map((t) => (
        <Link key={t.key} to={t.to} aria-current={active === t.key ? "page" : undefined}
          className={`-mb-px border-b-2 px-0.5 pb-2.5 text-sm font-medium transition ${
            active === t.key ? "border-brand text-fg" : "border-transparent text-muted hover:text-fg"
          }`}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
