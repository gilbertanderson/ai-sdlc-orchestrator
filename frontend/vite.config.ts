import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `--mode demo` builds the browser demo for GitHub Pages: recorded runs, no server.
export default defineConfig(({ mode }) => ({
  base: mode === "demo" ? "/ai-sdlc-orchestrator/" : "/",
  plugins: [react()],
  build: { outDir: mode === "demo" ? "dist-demo" : "dist" },
  preview: { port: 4173, strictPort: true },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  test: { environment: "jsdom", globals: true, setupFiles: ["src/setupTests.ts"], include: ["src/**/*.test.{ts,tsx}"] },
}));
