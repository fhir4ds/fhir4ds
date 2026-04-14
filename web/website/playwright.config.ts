import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    // baseUrl defaults to '/' for fhir4ds.com; serve runs on port 3000.
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000/",
    trace: "on-first-retry",
    launchOptions: {
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH,
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
