import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S26d REVIEW FIXBACK journeys — Joel's checkpoint words (2026-10-22):
// (1) "the measure lists one library and it's not the primary
//     CMS125FHIR library" — the adopted disk Measure resolves its
//     PRIMARY library (Measure.library[0] tail) for the entrypoint.
// (2) "data in the funnel tab but not the measure report tab" — with
//     the entrypoint fixed, the measure-context run materializes
//     MeasureReports (MR tab renders rows).
// (3) "cell view is still not taking up all of the vertical space" —
//     the cells-fullheight grid collapse (editor spans the column).
// (4) "a header cell for all of the declarations" — the declarations
//     card renders above the define cells.
// (6) "use the name or title instead of the id" for valuesets.
// (7) "cms125demo we don't need anymore" — gone from the libraries.
// (8) "expected results not populated" — the Expected surface lists
//     the fixture-official per-patient expectations.
// (9) "MeasureReportPopulations view errors" — the view opens and
//     executes without error.

const BASE = "http://127.0.0.1:19235";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    [
      "-m", "fhir4ds.cli", "dev",
      "/mnt/d/fhir4ds/examples/cms125-workspace",
      "--port", "19235", "--no-open",
    ],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 90; i++) {
    try {
      if ((await fetch(`${BASE}/health`)).ok) return;
    } catch { /* boot */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try { process.kill(server.pid); await new Promise((r) => setTimeout(r, 300)); } catch { /* gone */ }
  }
});

async function boot(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
}

test("S26d-1: measure resolves its PRIMARY library (not an include)", async ({ page }) => {
  await boot(page);
  // Open the measure tab: the primary library selector names CMS125FHIR.
  await page.locator('[data-testid="nav-toggle-config"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel.locator(".nav-item", { hasText: "CMS125" }).first().click({ timeout: 15000 });
  // The measure pane's library picker shows the primary library name.
  const picker = page.locator("select", { hasText: "CMS125FHIR" }).first();
  await expect(picker).toBeVisible({ timeout: 20000 });
  // And the heartbeat targets the primary: fill the required Measurement
  // Period (as a real user must), then the console shows the CMS125
  // define columns.
  await page.locator('[data-testid="nav-toggle-config"]').click();
  await page.locator('[data-testid^="nav-item-parameter-"]').first().click({ timeout: 15000 });
  const mpStart = page.locator('[data-testid="param-input-Measurement Period"]');
  await expect(mpStart).toBeVisible({ timeout: 30000 });
  await mpStart.fill("2026-01-01");
  await page.locator('[data-testid="param-end-Measurement Period"]').fill("2026-12-31");
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('[data-testid="results-table"] th')].some((th) =>
        th.textContent?.includes("Initial Population"),
      ),
    undefined,
    { timeout: 120000 },
  );
});

test("S26d-2: Measure Report tab renders rows (not just the funnel)", async ({ page }) => {
  await boot(page);
  // Fill the Measurement Period FIRST (a real user fills parameters
  // before inspecting the measure surfaces — the params tab has no
  // console, so the MR tab must be reached from the MEASURE surface).
  await page.locator('[data-testid="nav-toggle-config"]').click();
  await page.locator('[data-testid^="nav-item-parameter-"]').first().click({ timeout: 15000 });
  const mpStart = page.locator('[data-testid="param-input-Measurement Period"]');
  await expect(mpStart).toBeVisible({ timeout: 30000 });
  await mpStart.fill("2026-01-01");
  await page.locator('[data-testid="param-end-Measurement Period"]').fill("2026-12-31");
  // Let the heartbeat run with the parameter filled.
  await page.waitForTimeout(12000);
  // Open the measure surface: the console switches to the measure
  // context whose first-class tabs are Measure Report + Funnel.
  await page.locator('[data-testid="nav-toggle-config"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel.locator(".nav-item", { hasText: "CMS125" }).first().click({ timeout: 15000 });
  const mrTab = page.locator('[data-testid="console-tab-mr"]');
  await expect(mrTab).toBeVisible({ timeout: 30000 });
  await mrTab.click();
  // MR rows materialized: the pivot table (inside mr-reports) renders.
  await expect(page.locator('[data-testid="mr-table"]')).toBeVisible({ timeout: 90000 });
});

test("S26d-3+4: cells view spans full height and shows the declarations card", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "CMS125FHIRBreastCancerScreening" }).first().click({ timeout: 15000 });
  await expect(
    page.getByRole("tab", { name: /CMS125FHIR/i }),
  ).toBeVisible({ timeout: 30000 });
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) await gotIt.click();
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  try {
    await toggle.waitFor({ state: "visible", timeout: 10000 });
    if ((await toggle.getAttribute("aria-checked")) !== "true") {
      await toggle.click();
      await page.waitForTimeout(2000);
    }
  } catch { /* no cells */ }
  // Markerless buffer in cells view: the real user clicks Auto-split.
  const autoSplit = page.getByRole("button", { name: "Auto-split" });
  if (await autoSplit.isVisible().catch(() => false)) {
    await autoSplit.click();
    await page.waitForTimeout(2000);
  }
  // (4) declarations card renders with the library statement inside.
  const headerCard = page.locator('[data-testid="cell-header-card"]');
  await expect(headerCard).toBeVisible({ timeout: 15000 });
  await expect(headerCard).toContainText("declarations");
  // (3) the editor column carries the full-height class and no console.
  const col = page.locator(".editor-col.cells-fullheight");
  await expect(col).toBeVisible();
  await expect(page.locator('[data-testid="results-console"]')).toBeHidden();
});

test("S26d-6: valuesets label by name (not OID id)", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-valuesets"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(panel).toBeVisible();
  // FHIR name (HospiceEncounter) or title (Hospice Encounter) — either
  // beats the OID; assert the NAME form AND that no bare OID labels.
  await expect(
    panel.locator(".nav-item", { hasText: "HospiceEncounter" }).first(),
  ).toBeVisible({ timeout: 20000 });
  const labels = await panel.locator(".nav-item").allTextContents();
  expect(
    labels.filter((l) => /^[0-9.]{10,}/.test(l.trim())),
  ).toHaveLength(0);
});

test("S26d-7: CMS125Demo is gone from the libraries", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(panel).toBeVisible();
  await expect(
    panel.locator(".nav-item", { hasText: "CMS125Demo" }),
  ).toHaveCount(0, { timeout: 15000 });
});

test("S26d-8: Expected Results populated with the fixture cases", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-expected"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(panel).toContainText("66 patients", { timeout: 30000 });
});

test("S26d-9: MeasureReportPopulations view opens without error", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-views"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const item = panel.locator(".nav-item", { hasText: "MeasureReportPopulations" }).first();
  await expect(item).toBeVisible({ timeout: 20000 });
  await item.click();
  await page.waitForTimeout(8000);
  // The View tab opens; no error diagnostic banner.
  const err = page.locator('[data-testid="console-diags"], .diag-error');
  const count = await err.count().catch(() => 0);
  expect(count).toBe(0);
});
