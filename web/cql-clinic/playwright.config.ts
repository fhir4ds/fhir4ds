import { defineConfig } from "@playwright/test";

/**
 * CQL Clinic e2e config (FHIR4-49).
 *
 * Port 5177 + `reuseExistingServer: false` + build-then-preview, following the
 * cleanroom's QA doctrine: a stale preview squatting on a shared port silently
 * serves an old build, so tests would judge code that is not in the browser.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 180_000,
  retries: 0,
  workers: 1,
  use: {
    headless: true,
    baseURL: "http://localhost:5177",
    launchOptions: {
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
  },
  expect: {
    timeout: 30_000,
  },
  webServer: {
    command: "npm run build && npm run preview -- --port 5177 --strictPort",
    port: 5177,
    reuseExistingServer: false,
    timeout: 240_000,
  },
});
