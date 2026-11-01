import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: frontend on :8003 proxying /api to the evaluator backend on :8002 (SSE passes through).
// Deployed: VITE_BASE_PATH=/charon/dolly/ makes every asset, route and API call live under that prefix.
export default defineConfig({
  base: process.env.VITE_BASE_PATH || "/",
  plugins: [react(), tailwindcss()],
  // The server serves the dashboard from the package, so the build goes straight there.
  build: { outDir: "../ragevalkit/web/dashboard", emptyOutDir: true },
  server: { port: 8003, strictPort: true, proxy: { "/api": "http://127.0.0.1:8002" } },
});
