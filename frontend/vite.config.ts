/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
// Optional sub-path the app is served under (BASE_PATH=/results). Empty = the site root.
const sub = (process.env.BASE_PATH ?? "").trim().replace(/^\/+|\/+$/g, "");
const base = sub ? `/${sub}/` : "/";

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // One origin in dev, same as production behind Caddy. Django never sees the prefix, as behind the proxy.
    proxy: { [`${base}api`]: { target: backend, changeOrigin: false, rewrite: (p) => (sub ? p.slice(sub.length + 1) : p) } },
  },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", include: ["src/**/*.test.ts?(x)"] },
});
