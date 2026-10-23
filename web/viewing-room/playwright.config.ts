import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 180_000,
  retries: 0, // zero-flaky policy
  workers: 1, // pyodide boot is heavy; serialize
  use: {
    headless: true,
    baseURL: "http://localhost:5177",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || "/usr/bin/google-chrome",
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
  },
  expect: {
    timeout: 30_000,
  },
  webServer: {
    // AGENTS.md doctrine: serve the BUILT dist via vite preview — vite
    // dev misses drvfs file-watch events on WSL and serves stale
    // transforms; preview reads dist at boot. Build before testing.
    command: "npm run build && npm run preview -- --port 5177 --strictPort",
    port: 5177,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
