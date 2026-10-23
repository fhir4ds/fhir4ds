/**
 * JOURNEY test #1 (design §6, from the design's own words):
 * "Open the app → engine boots → the default Patient Demographics sample
 *  loads and auto-runs → the output table renders patient rows with the
 *  fhir4ds version badge visible."
 */

import { test, expect } from "@playwright/test";

test("journey: default sample boots, auto-runs, and renders patient rows", async ({ page }) => {
  await page.goto("/");

  // Boot overlay shows while the engine initializes (Pyodide + DuckDB-WASM).
  const overlay = page.getByTestId("boot-overlay");
  if (await overlay.isVisible().catch(() => false)) {
    await expect(overlay).toBeHidden({ timeout: 120_000 });
  }

  // Version badge appears once the engine is ready.
  const badge = page.getByTestId("version-badge");
  await expect(badge).toBeVisible({ timeout: 120_000 });
  await expect(badge).toContainText(/fhir4ds \d+\.\d+\.\d+/);

  // The default sample auto-ran: the reference playground's patient set
  // (25 Synthea patients, 35 name rows; S5 reference alignment).
  const table = page.getByTestId("output-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  await expect(table.locator("tbody tr")).toHaveCount(35, { timeout: 30_000 });
  await expect(table).toContainText("Bechtelar572");

  // SQL tab shows the verbatim generated SQL.
  await page.getByRole("tab", { name: "SQL" }).click();
  const sqlView = page.getByTestId("sql-view");
  await expect(sqlView).toBeVisible();
  await expect(sqlView).toContainText("SELECT");
  await expect(sqlView).toContainText("__vd_src");
});
