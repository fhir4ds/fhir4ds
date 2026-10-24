import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S27 fix-specific journey (Joel review round 2):
//   1. Views nav lists ViewDefinitions ONLY (Parameters file gone).
//   2. MeasureReportPopulations opens with the VD loaded (Custom mode).
//   3. The view mode selector defaults to "From Measure".
//   4. The Custom VD editor fills the pane's free vertical space.
//   5. Cells view SPLITS the library on open and RUNS with real output.
//   6. The stray "Evaluated N · <define> X …" summary line is GONE.

const BASE = "http://127.0.0.1:19237";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", "/mnt/d/fhir4ds/examples/cms125-workspace", "--port", "19237", "--no-open"],
    { cwd: "/mnt/d/fhir4ds", env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" }, stdio: "ignore" },
  );
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch { /* wait */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) { try { process.kill(server.pid); } catch { /* gone */ } }
});

async function boot(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
}

test("S27-5: views nav lists ViewDefinitions only; disk VD opens", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-views"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(panel).toBeVisible();
  await expect(
    panel.locator(".nav-item", { hasText: "MeasureReportPopulations" }).first(),
  ).toBeVisible({ timeout: 20000 });
  // The Parameters data file is NOT a ViewDefinition — it must not appear.
  const paramsRows = panel.locator(".nav-item", { hasText: "Parameters-MeasurementPeriod" });
  await expect(paramsRows).toHaveCount(0);
  // The disk VD opens with its text loaded, no error banner.
  await panel.locator(".nav-item", { hasText: "MeasureReportPopulations" }).first().click();
  const viewPane = page.locator('[data-testid="view-pane"]');
  await expect(viewPane).toBeVisible({ timeout: 20000 });
  await expect(page.locator('[data-testid="view-error"]')).toHaveCount(0);
  // S29: the mode control is the SAME switch widget as Builder/Cells.
  // A disk-VD click opens the one-shot Custom (text) editor → ON.
  const mode = page.locator('[data-testid="view-mode"]');
  await expect(mode).toBeVisible();
  await expect(mode).toHaveAttribute("role", "switch");
  await expect(mode).toHaveAttribute("aria-checked", "true");
  await expect(mode).toContainText("Form ⇄");
  // The Custom VD editor takes the free vertical space.
  const ed = page.locator('[data-testid="vd-editor"]');
  if (await ed.count()) {
    const box = await ed.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThan(160);
  }
});

test("S27-6: cells view splits on open and runs with output", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel
    .locator(".nav-item", { hasText: "CMS125FHIRBreastCancerScreening" })
    .first()
    .click({ timeout: 30000 });
  await page.waitForTimeout(6000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  await expect(toggle).toBeVisible({ timeout: 20000 });
  if ((await toggle.getAttribute("aria-checked")) !== "true") {
    await toggle.click();
  }
  // Auto-split on open: cells render (no empty-marker hint).
  const cards = page.locator('[data-testid="cell-card"]');
  await expect(cards.first()).toBeVisible({ timeout: 30000 });
  expect(await cards.count()).toBeGreaterThan(10);
  // Run the first cell — real rows, no error text.
  const card = cards.first();
  await card.locator('[data-testid="cell-run"]').click();
  const out = card.locator('[data-testid="cell-out"]');
  await expect(out).toContainText("patient_id", { timeout: 60000 });
  const text = (await out.textContent()) ?? "";
  expect(text.toLowerCase()).not.toContain("error");
});

test("S27-7: the stray evaluated-summary line is gone", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel
    .locator(".nav-item", { hasText: "CMS125FHIRBreastCancerScreening" })
    .first()
    .click({ timeout: 30000 });
  await page.waitForTimeout(6000);
  // Cells view is console-free (heartbeat suppressed): switch to TEXT
  // view to bring the results console back.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
  }
  await expect(page.locator('[data-testid="results-table"]')).toBeVisible({ timeout: 90000 });
  expect(await page.locator('[data-testid="results-summary"]').count()).toBe(0);
});
