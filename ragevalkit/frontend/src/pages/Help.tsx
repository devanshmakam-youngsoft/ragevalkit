import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { TopBar } from "../components/TopBar";
import { useFeatures } from "../hooks/features";

/** The guide, read inside the dashboard. It follows the dashboard's light or dark theme. */
export default function Help() {
  const features = useFeatures();
  const frame = useRef<HTMLIFrameElement>(null);
  const [loaded, setLoaded] = useState(false);

  const syncTheme = useCallback(() => {
    const root = frame.current?.contentDocument?.documentElement;
    const theme = document.documentElement.dataset.theme;
    if (root && theme) root.dataset.theme = theme;
  }, []);

  useEffect(() => {
    const watcher = new MutationObserver(syncTheme);
    watcher.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => watcher.disconnect();
  }, [syncTheme]);

  if (features && !features.guide) return <Navigate to="/" replace />;

  return (
    <>
      <TopBar />
      <div className="mx-auto max-w-[1280px] px-6 pb-6 pt-2">
        {features?.guide && (
          <iframe
            ref={frame} title="ragevalkit guide" src={api.guideUrl()}
            onLoad={() => { syncTheme(); setLoaded(true); }}
            className={`h-[calc(100vh-9.5rem)] min-h-[520px] w-full rounded-lg border border-line bg-bg transition-opacity duration-200 ${loaded ? "opacity-100" : "opacity-0"}`}
          />
        )}
      </div>
    </>
  );
}
