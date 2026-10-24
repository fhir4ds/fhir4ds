import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S27 fix-specific journey: the Expected Results COMPARE tab resolves each
// population through the measure's own define mapping. Repro (before the
// fix): the server heartbeat returns define-keyed rows, the compare read
// snake_case population columns, every cell came back null → "0/264
// passed" with every row red. After the fix the 66 official CMS125 cases
// compare green against the fixture-official expected values.

const BASE = "http://127.0.0.1:19233";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    [
      "-m",
      "fhir4ds.cli",
      "dev",
      "/mnt/d/fhir4ds/examples/cms125-workspace",
      "--port",
      "19233",
      "--no-open",
    ],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
      await new Promise((r) => setTimeout(r, 300));
    } catch {
      /* already gone */
    }
  }
});

test("S27-1: expected-results compare resolves populations via the measure mapping", async ({
  page,
}) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  // Expected Results surface → the CMS125 measure's expectations.
  await page.locator('[data-testid="nav-toggle-expected"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel.locator(".nav-item", { hasText: "CMS125" }).first().click({ timeout: 30000 });
  // Compare tab: 66 official cases × 4 populations, every one passing.
  await page.locator('[data-testid="console-tab-compare"]').click({ timeout: 30000 });
  const chip = page.locator('[data-testid="tests-summary"]');
  await expect(chip).toContainText("264/264 passed", { timeout: 90000 });
});
