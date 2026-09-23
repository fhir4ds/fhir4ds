import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Unit tests only — Playwright e2e specs (tests/e2e/*) run via
    // `npm run e2e`, never under vitest.
    include: ["tests/unit/**/*.test.ts"],
    environment: "node",
  },
});
