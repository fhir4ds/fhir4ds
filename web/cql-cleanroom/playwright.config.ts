import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 180_000,
  retries: 0, // zero-flaky policy
  workers: 1, // pyodide boot is heavy; serialize
  use: {
    headless: true,
    baseURL: "http://localhost:5176",
    launchOptions: {
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
  },
  expect: {
    timeout: 30_000,
  },
  webServer: {
    command: "npm run dev -- --port 5176 --strictPort",
    port: 5176,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
