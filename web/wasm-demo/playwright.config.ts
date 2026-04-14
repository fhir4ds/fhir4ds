import { defineConfig, devices } from "@playwright/test";
import path from "path";
import dotenv from "dotenv";

// Load .env from project root
dotenv.config({ path: path.resolve(import.meta.dirname, "../../.env") });

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  timeout: 180_000,
  expect: {
    timeout: 30_000,
  },
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    launchOptions: {
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npx vite preview --port 5173",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
