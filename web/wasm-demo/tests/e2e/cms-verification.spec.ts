import { test, expect } from "@playwright/test";

test.describe("CMS Verification", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Navigate to CMS Measures tab
    await page.click("button.tab-btn:has-text('CMS Measures')");
    await expect(page.locator(".cms-shell")).toBeVisible({ timeout: 10_000 });
  });

  test("CMS workspace shows measure select and run button", async ({ page }) => {
    const shell = page.locator(".cms-shell");
    await expect(shell).toBeVisible();
    // Measure selector in the header
    await expect(shell.locator("select.sample-select").first()).toBeVisible();
    // ▶ Run button
    await expect(shell.getByRole("button", { name: /▶ Run/ })).toBeVisible();
  });

  test("measure description is visible in workspace", async ({ page }) => {
    // The selected measure's h3 heading should be visible in the Measure Definition pane
    await expect(page.getByRole("heading", { name: /CMS124/i })).toBeVisible({ timeout: 10_000 });
    // The description text should also be visible
    await expect(page.locator("text=Women 21–64 who were screened for cervical cancer").first()).toBeVisible({ timeout: 5_000 });
  });

  test("running CMS124 shows results with clickable patient rows", async ({ page }) => {
    test.setTimeout(360_000); // CMS DuckDB init + execution can take ~5 min on cold start
    // Wait for DuckDB to be ready before running
    await expect(page.locator(".status-dot.ready")).toBeVisible({ timeout: 120_000 });

    const measureSelect = page.locator(".cms-shell select.sample-select").first();
    await measureSelect.selectOption("CMS124");

    await page.click("button:has-text('▶ Run')");

    await expect(page.locator(".results-table")).toBeVisible({ timeout: 120_000 });

    const rows = page.locator(".results-table tbody tr");
    await expect(rows.first()).toBeVisible();

    // Click the first patient row — should be clickable
    const firstRow = rows.first();
    await firstRow.click();
    await expect(firstRow).toHaveCSS("cursor", "pointer");
  });
});
