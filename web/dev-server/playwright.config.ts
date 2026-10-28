import { defineConfig, devices } from "@playwright/test";

// Dev-server e2e: the Python server itself serves the committed UI from
// fhir4ds/devserver/static (built before tests run), so no vite webServer.
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL: "http://127.0.0.1:18901",
    trace: "on-first-retry",
    launchOptions: { args: ["--no-sandbox", "--disable-setuid-sandbox"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
