import { defineConfig } from "@playwright/test";

/**
 * QA-campaign config: identical to playwright.config.ts but on port 5179
 * with reuseExistingServer DISABLED. Reason (it1 lesson): a stale preview
 * from a different checkout (e.g. /mnt/d/fhir4ds) squatting on 5176 gets
 * silently reused, so code fixes under test never reach the browser and
 * probes "fail" or "pass" against weeks-old builds. QA runs must always
 * build + serve their own tree.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 180_000,
  retries: 0,
  workers: Number(process.env.PW_WORKERS ?? 1),
  use: {
    headless: true,
    baseURL: "http://localhost:5179",
    launchOptions: {
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
  },
  expect: {
    timeout: 30_000,
  },
  webServer: {
    command: "npm run build && npm run preview -- --port 5179 --strictPort",
    port: 5179,
    reuseExistingServer: false,
    timeout: 240_000,
  },
});
