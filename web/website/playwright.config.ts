import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000/";
const serverURL = new URL(baseURL);
const serverHost = serverURL.hostname || "127.0.0.1";
const serverPort = serverURL.port || (serverURL.protocol === "https:" ? "443" : "80");

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
    // Keep this in sync with webServer so tests never reuse an unrelated app.
    baseURL,
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
  webServer: {
    command: `npm run serve -- --host ${serverHost} --port ${serverPort}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
