import { Fragment } from "react";
import { Link } from "react-router-dom";

export type Crumb = { label: string; to?: string };

/**
 * Location trail shown under the header: Home > Groups > <name>.
 * "Home" is always the first crumb; the last crumb is the current page (plain text, not a link).
 */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const trail: Crumb[] = [{ label: "Home", to: "/" }, ...items];
  return (
    <nav aria-label="Breadcrumb" className="mx-auto max-w-[1280px] px-6 pb-3">
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {trail.map((c, i) => {
          const last = i === trail.length - 1;
          return (
            <Fragment key={`${i}-${c.label}`}>
              {i > 0 && <li aria-hidden="true" className="text-muted">&gt;</li>}
              <li className="min-w-0">
                {last || !c.to ? (
                  <span aria-current={last ? "page" : undefined} className="block max-w-[320px] truncate font-medium text-fg" title={c.label}>
                    {c.label}
                  </span>
                ) : (
                  <Link to={c.to} className="block max-w-[240px] truncate text-muted transition hover:text-brand hover:underline" title={c.label}>
                    {c.label}
                  </Link>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
