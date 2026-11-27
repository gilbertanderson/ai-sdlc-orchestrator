import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// GitHub Pages can't send headers, so the demo's policy ships as a meta tag. Only the demo
// build gets it: Vite's dev server injects inline scripts, and the local app talks to the
// FastAPI server over HTTP and WebSocket. The demo loads its recorded runs from this site.
const DEMO_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "base-uri 'none'",
  "form-action 'none'",
  "object-src 'none'",
].join("; ");

function demoContentSecurityPolicy() {
  return {
    name: "demo-content-security-policy",
    apply: "build" as const,
    transformIndexHtml(html: string) {
      return html.replace(
        '<meta charset="UTF-8" />',
        `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${DEMO_CSP}" />`,
      );
    },
  };
}

// `--mode demo` builds the browser demo for GitHub Pages: recorded runs, no server.
export default defineConfig(({ mode }) => ({
  base: mode === "demo" ? "/ai-sdlc-orchestrator/" : "/",
  plugins: mode === "demo" ? [react(), demoContentSecurityPolicy()] : [react()],
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
