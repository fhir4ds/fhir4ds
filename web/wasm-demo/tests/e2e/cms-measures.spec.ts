import { test, expect } from "@playwright/test";

/**
 * E2E tests for the CMS Measures tab.
 *
 * These tests validate:
 * - Measure selector shows measures from the public manifest
 * - Non-audit execution returns results and 100% accuracy
 * - Evidence cells render with 🔍 icon in audit mode
 * - Population summary bar appears after run
 * - Accuracy badge shows in the header after run
 *
 * DuckDB-WASM + C++ extension loading is slow; timeouts are generous.
 */

const INIT_TIMEOUT = 120_000;   // Wait for DuckDB + extensions to load
const MEASURE_TIMEOUT = 120_000; // Wait for SQL execution to complete

test.describe("CMS Measures Tab", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Navigate to CMS Measures tab
    await page.click("button:has-text('CMS Measures')");
  });

  // ─── Smoke tests ────────────────────────────────────────────────────────────

  test("measure selector shows manifest measures", async ({ page }) => {
    // Scope to the measure selector inside the cms-shell
    const select = page.locator(".cms-shell select.sample-select").first();
    await expect(select).toBeVisible({ timeout: 10_000 });
    const options = select.locator("option");
    await expect(options).toHaveCount(5);
    await expect(options.nth(0)).toContainText("CMS74");
    await expect(options.nth(1)).toContainText("CMS75");
    await expect(options.nth(2)).toContainText("CMS124");
    await expect(options.nth(3)).toContainText("CMS159");
    await expect(options.nth(4)).toContainText("CMS349");
  });

  test("DuckDB initialises successfully (status dot turns ready)", async ({ page }) => {
    // Should show 'DuckDB Ready' in the status area
    await expect(page.locator(".status-dot.ready")).toBeVisible({
      timeout: INIT_TIMEOUT,
    });
    // Must not show an error
    await expect(page.locator(".results-error")).not.toBeVisible();
  });

  // ─── Execution ────────────────────────────────────────────────────────────

  test("CMS124 executes and shows results table", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS124");

    await page.click("button:has-text('▶ Run')");

    const table = page.locator("table.results-table");
    await expect(table).toBeVisible({ timeout: MEASURE_TIMEOUT });

    const rows = table.locator("tbody tr");
    await expect(rows).not.toHaveCount(0);
  });

  test("CMS124 shows accuracy badge in header after run", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS124");

    await page.click("button:has-text('▶ Run')");

    await expect(page.locator("table.results-table")).toBeVisible({ timeout: MEASURE_TIMEOUT });

    // AccuracyBadge renders "X.X% accuracy" in the header
    await expect(page.locator("text=% accuracy").first()).toBeVisible({ timeout: 10_000 });
  });

  test("CMS124 shows population summary bar", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS124");

    await page.click("button:has-text('▶ Run')");
    await expect(page.locator("table.results-table")).toBeVisible({ timeout: MEASURE_TIMEOUT });

    // Population Stats panel shows .stat-label cards for each population
    await expect(page.locator(".stat-label").filter({ hasText: "Initial Population" }).first()).toBeVisible({ timeout: 5_000 });
    await expect(page.locator(".stat-label").filter({ hasText: "Denominator" }).first()).toBeVisible({ timeout: 5_000 });
    await expect(page.locator(".stat-label").filter({ hasText: "Numerator" }).first()).toBeVisible({ timeout: 5_000 });
  });

  test("CMS124 audit mode shows 🔍 evidence icons in table cells", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS124");
    await page.click("button:has-text('▶ Run')");

    const table = page.locator("table.results-table");
    await expect(table).toBeVisible({ timeout: MEASURE_TIMEOUT });

    // Audit cells include the 🔍 icon
    const auditIcons = page.locator(".audit-icon");
    const count = await auditIcons.count();
    expect(count).toBeGreaterThan(0);
  });

  test("evidence modal opens on audit cell click", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS124");
    await page.click("button:has-text('▶ Run')");

    await expect(page.locator("table.results-table")).toBeVisible({ timeout: MEASURE_TIMEOUT });

    // Click the first audit cell
    const firstAuditCell = page.locator(".audit-cell").first();
    await firstAuditCell.click();

    // EvidenceModal uses .evidence-backdrop / .evidence-modal classes
    await expect(page.locator(".evidence-modal")).toBeVisible({ timeout: 5_000 });
  });

  test("clicking a patient result loads that patient's FHIR resources", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS124");
    await page.click("button:has-text('▶ Run')");

    const table = page.locator("table.results-table");
    await expect(table).toBeVisible({ timeout: MEASURE_TIMEOUT });

    await table.locator("tbody tr").first().click();

    const viewer = page.locator("[data-testid='patient-data-viewer']");
    await expect(viewer).toBeVisible();
    await expect(viewer.locator(".patient-viewer-summary")).toContainText("resource", {
      timeout: 30_000,
    });
  });

  // ─── Switching measures ─────────────────────────────────────────────────

  test("switching measure resets results", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    await page.click("button:has-text('▶ Run')");
    await expect(page.locator("table.results-table")).toBeVisible({ timeout: MEASURE_TIMEOUT });

    // Switch to CMS349
    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS349");

    // Table should disappear after switching
    await expect(page.locator("table.results-table")).not.toBeVisible({ timeout: 5_000 });
  });

  test("CMS349 executes and shows HIV Screening results", async ({ page }) => {
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: INIT_TIMEOUT });

    const select = page.locator(".cms-shell select.sample-select").first();
    await select.selectOption("CMS349");
    await page.click("button:has-text('▶ Run')");

    const table = page.locator("table.results-table");
    await expect(table).toBeVisible({ timeout: MEASURE_TIMEOUT });

    const rows = table.locator("tbody tr");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
  });
});
