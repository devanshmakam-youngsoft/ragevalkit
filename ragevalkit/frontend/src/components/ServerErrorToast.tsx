import { useEffect, useState } from "react";
import { apiEvents, type ApiError } from "../api/client";
import { TechnicalDetails } from "./TechnicalDetails";

/** When the server fails in a way nobody planned for: a plain message, a reference to quote, details on request. */
export function ServerErrorToast() {
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    const onError = (event: Event) => setError((event as CustomEvent<ApiError>).detail);
    apiEvents.addEventListener("server-error", onError);
    return () => apiEvents.removeEventListener("server-error", onError);
  }, []);

  if (!error) return null;
  return (
    <div role="alert" className="fixed bottom-4 right-4 z-[60] w-[min(26rem,calc(100vw-2rem))] rounded border border-bad bg-surface p-4 text-sm shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <p className="leading-relaxed">{error.message}</p>
        <button onClick={() => setError(null)} aria-label="Dismiss" className="mono text-xs text-muted hover:text-fg">close</button>
      </div>
      <TechnicalDetails text={[error.reference && `Reference: ${error.reference}`, error.technical].filter(Boolean).join("\n")} />
    </div>
  );
}
