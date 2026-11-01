import type { Issue } from "../api/types";
import { TechnicalDetails } from "./TechnicalDetails";

/** What went wrong, in plain words, one entry per kind of problem. Warnings carried on with a fallback. */
export function IssueList({ issues }: { issues: Issue[] }) {
  return (
    <ul className="space-y-3 text-sm">
      {issues.map((issue, i) => (
        <li key={i} className="flex gap-2.5">
          <span className={`mt-[7px] h-2 w-2 shrink-0 rounded-full ${issue.severity === "error" ? "bg-bad" : "bg-warn"}`} aria-hidden />
          <div className="min-w-0">
            <p className="leading-relaxed">
              {issue.message}
              {issue.count > 1 && <span className="mono ml-2 text-xs text-muted">× {issue.count}</span>}
            </p>
            {issue.where && <p className="text-xs text-muted">{issue.where}{issue.count > 1 ? " (first time)" : ""}</p>}
            <TechnicalDetails text={issue.technical} />
          </div>
        </li>
      ))}
    </ul>
  );
}
