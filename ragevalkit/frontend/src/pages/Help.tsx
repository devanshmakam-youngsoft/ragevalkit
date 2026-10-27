import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Guide } from "../api/types";
import { TopBar } from "../components/TopBar";

/** The guides, read inside the dashboard. */
export default function Help() {
  const { guideId } = useParams();
  const [guides, setGuides] = useState<Guide[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.guides().then(setGuides).catch((e) => setError(e.message));
  }, []);

  const current = guides?.find((g) => g.id === guideId) ?? guides?.[0];

  return (
    <>
      <TopBar />
      <div className="mx-auto max-w-[1280px] px-6 pb-10 pt-4">
        <h2 className="font-serif text-[26px] font-medium tracking-tight">Help</h2>
        {error && <p className="mt-4 text-sm text-bad" role="alert">{error}</p>}
        {guides && current && (
          <>
            <nav aria-label="Guides" className="mt-4 flex flex-wrap gap-3">
              {guides.map((g) => (
                <Link key={g.id} to={`/help/${g.id}`} aria-current={g.id === current.id ? "page" : undefined}
                  className={`rounded border px-4 py-2.5 text-left text-sm no-underline transition ${g.id === current.id ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-2"}`}>
                  <span className="block font-medium text-fg">{g.title}</span>
                  <span className="mt-0.5 block max-w-[34ch] text-xs text-muted">{g.description}</span>
                </Link>
              ))}
            </nav>
            <iframe
              key={current.id} title={current.title} src={api.guideUrl(current.id)}
              className="mt-4 h-[calc(100vh-15rem)] min-h-[480px] w-full rounded border border-line bg-white"
            />
          </>
        )}
      </div>
    </>
  );
}
