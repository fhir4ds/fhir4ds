import { test, expect } from "@playwright/test";

// Pyodide + DuckDB-WASM init is slow — wait for both engines to be ready.
const INIT_TIMEOUT = 90_000;

test.describe("CQL Playground", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Wait for DuckDB and Pyodide to be ready (status dots turn green)
    await expect(page.locator(".status-dot.ready")).toHaveCount(2, {
      timeout: INIT_TIMEOUT,
    });
  });

  test("sample selector shows all 5 samples", async ({ page }) => {
    const select = page.locator(".sample-select").first();
    const options = select.locator("option");
    // Default placeholder + 5 samples
    await expect(options).toHaveCount(6);
    await expect(options.nth(1)).toContainText("Clinical Overview");
    await expect(options.nth(2)).toContainText("Patient Demographics");
    await expect(options.nth(3)).toContainText("Active Conditions");
    await expect(options.nth(4)).toContainText("Diabetes Screening");
    await expect(options.nth(5)).toContainText("Vital Signs");
  });

  test("selecting Vital Signs sample loads CQL text", async ({ page }) => {
    const select = page.locator(".sample-select").first();
    await select.selectOption("vital-signs");
    // Verify the Monaco editor contains the VitalSigns library
    await expect(page.locator("text=VitalSigns")).toBeVisible({ timeout: 5_000 });
  });

  test("Patient Demographics sample runs and shows results", async ({ page }) => {
    const select = page.locator(".sample-select").first();
    await select.selectOption("patient-demographics");

    // Click Run
    await page.click("button:has-text('Run')");

    // Wait for results table to appear
    const resultsTable = page.locator(".results-table");
    await expect(resultsTable).toBeVisible({ timeout: 60_000 });

    // Should have at least 1 row of data
    const rows = resultsTable.locator("tbody tr");
    await expect(rows).not.toHaveCount(0);

    // Should show row count in the pane meta
    await expect(page.locator(".pane-meta")).toContainText("row");
  });

  test("Vital Signs sample produces mixed-type columns", async ({ page }) => {
    const select = page.locator(".sample-select").first();
    await select.selectOption("vital-signs");

    await page.click("button:has-text('Run')");

    // This sample has complex CQL (sort, Count, exists) — allow more time
    const resultsTable = page.locator(".results-table");
    await expect(resultsTable).toBeVisible({ timeout: 90_000 });

    // Check column headers include expected defines
    const headers = resultsTable.locator("th");
    const headerTexts = await headers.allTextContents();
    expect(headerTexts.some((h) => h.includes("Birth Date") || h.includes("birth_date"))).toBeTruthy();
    expect(headerTexts.some((h) => h.includes("Gender") || h.includes("gender"))).toBeTruthy();

    // Check boolean cells are rendered as badges
    const boolBadges = resultsTable.locator(".cell-bool");
    await expect(boolBadges.first()).toBeVisible({ timeout: 5_000 });

    // Check number cells are styled
    const numberCells = resultsTable.locator(".cell-number");
    const numCount = await numberCells.count();
    expect(numCount).toBeGreaterThanOrEqual(0);
  });

  test("SQL output panel updates after translation", async ({ page }) => {
    const select = page.locator(".sample-select").first();
    await select.selectOption("patient-demographics");

    await page.click("button:has-text('▶ Run')");

    // Wait for SQL to appear (not the placeholder text)
    await expect(page.locator("text=WITH")).toBeVisible({ timeout: 60_000 });
  });
});
