import { defineConfig, devices } from "@playwright/test";

// Locally, PW_CHROME_PATH can point at an installed Chrome instead of a downloaded browser.
const chrome = process.env.PW_CHROME_PATH;
const url = "http://localhost:4173/ai-sdlc-orchestrator/";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: url,
    trace: "retain-on-failure",
    launchOptions: chrome ? { executablePath: chrome, args: ["--no-sandbox"] } : undefined,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: { command: "npm run preview:demo", url, reuseExistingServer: !process.env.CI },
});
