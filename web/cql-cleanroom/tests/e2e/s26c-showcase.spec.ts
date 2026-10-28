import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S26c slice-3 SHOWCASE journey (item 10 second half) — the plan's own
// words: "each full example workspace carries expected results authored
// from the fixture's official expected values + a ViewDefinition over
// the MeasureReports; e2e proving Results -> Evidence -> Expected
// compare -> View."
//
// Journey on the REAL cms125-workspace (connected): open the CMS125
// library, the server heartbeat renders real results; the Expected
// Results surface lists the FIXTURE-official per-patient expectations;
// the View tab lists the MeasureReportPopulations ViewDefinition.

const BASE = "http://127.0.0.1:19232";
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
      "19232",
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
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
      await new Promise((r) => setTimeout(r, 300));
    } catch { /* already gone */ }
  }
});

async function boot(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  // Open the CMS125 MAIN library (the boot opens the first disk
  // library alphabetically — an include).
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel
    .locator(".nav-item", { hasText: "CMS125FHIRBreastCancerScreening" })
    .first()
    .click({ timeout: 15000 });
  await expect(
    page.getByRole("tab", { name: /CMS125FHIR/i }),
  ).toBeVisible({ timeout: 30000 });
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) await gotIt.click();
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  try {
    await toggle.waitFor({ state: "visible", timeout: 10000 });
    if ((await toggle.getAttribute("aria-checked")) === "true") {
      await toggle.click();
      await page.waitForFunction(
        () =>
          (document
            .querySelector('[data-testid="parse-status"]')
            ?.textContent ?? "").includes("parsed ✓"),
        { timeout: 30000 },
      );
    }
  } catch { /* cell toggle absent */ }
  // Let the server heartbeat fire (it may fail on the missing
  // Measurement Period — the parameter fills below and auto-heals).
  await page.waitForTimeout(4000);
  // Fill the Measurement Period (the fixture pins' 2026 reporting
  // year) — the heartbeat auto-heals once the parameter exists.
  await page.locator('[data-testid="nav-toggle-config"]').click();
  await page.locator('[data-testid^="nav-item-parameter-"]').first().click({ timeout: 15000 });
  const mpStart = page.locator('[data-testid="param-input-Measurement Period"]');
  await expect(mpStart).toBeVisible({ timeout: 30000 });
  await mpStart.fill("2026-01-01");
  await page
    .locator('[data-testid="param-end-Measurement Period"]')
    .fill("2026-12-31");
  await page.waitForTimeout(8000);
}

test("S26c-1: expected results surface the fixture-official pins", async () => {
  const r = await fetch(
    `${BASE}/api/tests/expected?measure=${encodeURIComponent("CMS125FHIRBreastCancerScreening")}`,
  );
  const b = (await r.json()) as { patients?: unknown[]; count?: number };
  expect(b.count ?? 0).toBeGreaterThanOrEqual(6);
});

test("S26c-2: journey — results render, expectations compare, View lists the VD", async ({ page }) => {
  await boot(page);
  // 1. RESULTS: the server heartbeat renders real rows (official 2025 case ids).
  const results = page.locator('[data-testid="results-table"]');
  await expect(results).toBeVisible({ timeout: 60000 });
  await expect(results).toContainText("01c88972-84e2-4594-835b-924481b9990a", { timeout: 60000 });

  // 2. EXPECTED: the Expected Results nav section carries the disk
  //    measure with the fixture-official patient count (66 official 2025 cases).
  await page.locator('[data-testid="nav-toggle-expected"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("CMS125FHIRBreastCancerScreening", { timeout: 30000 });
  await expect(panel).toContainText("66 patients", { timeout: 30000 });

  // 3. VIEW: the Views nav section lists the shipped
  //    MeasureReportPopulations ViewDefinition (disk file).
  await page.locator('[data-testid="nav-toggle-views"]').click();
  await expect(panel).toContainText("MeasureReportPopulations", { timeout: 30000 });
});
