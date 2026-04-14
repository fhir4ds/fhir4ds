import { test, expect } from "@playwright/test";

test.describe("Workspace Toggles", () => {
  test.beforeEach(async ({ page }) => {
    page.setDefaultTimeout(90_000);
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
  });

  test("workspace toolbar shows 3 toggle buttons", async ({ page }) => {
    const toolbar = page.locator("[data-testid='workspace-toolbar']");
    await expect(toolbar).toBeVisible();
    const toggles = toolbar.locator(".workspace-toggle");
    await expect(toggles).toHaveCount(3);
  });

  test("all 3 panes are visible by default", async ({ page }) => {
    await expect(page.locator("[data-testid='pane-cql-editor']")).toBeVisible();
    await expect(page.locator("[data-testid='pane-sql-output']")).toBeVisible();
    await expect(page.locator("[data-testid='pane-patient-data']")).toBeVisible();
  });

  test("toggling a pane hides it", async ({ page }) => {
    // Hide patient data pane
    await page.locator("[data-testid='toggle-patient-data']").click();
    await expect(page.locator("[data-testid='pane-patient-data']")).not.toBeVisible();

    // Other panes should still be visible
    await expect(page.locator("[data-testid='pane-cql-editor']")).toBeVisible();
    await expect(page.locator("[data-testid='pane-sql-output']")).toBeVisible();
  });

  test("toggling a pane again restores it", async ({ page }) => {
    const toggle = page.locator("[data-testid='toggle-patient-data']");
    // Hide
    await toggle.click();
    await expect(page.locator("[data-testid='pane-patient-data']")).not.toBeVisible();
    // Show
    await toggle.click();
    await expect(page.locator("[data-testid='pane-patient-data']")).toBeVisible();
  });

  test("pane visibility persists across tab switches", async ({ page }) => {
    // Hide SQL output pane
    await page.locator("[data-testid='toggle-sql-output']").click();
    await expect(page.locator("[data-testid='pane-sql-output']")).not.toBeVisible();

    // Switch to SDC Forms tab then back
    await page.click("button.tab-btn:has-text('SDC Forms')");
    await expect(page.locator(".sdc-playground")).toBeVisible({ timeout: 5_000 });

    await page.click("button.tab-btn:has-text('CQL Playground')");
    // SQL output should still be hidden (state persisted)
    await expect(page.locator("[data-testid='pane-sql-output']")).not.toBeVisible();
    // CQL editor should still be visible
    await expect(page.locator("[data-testid='pane-cql-editor']")).toBeVisible();
  });

  test("patient data viewer shows in CQL Playground", async ({ page }) => {
    const viewer = page.locator("[data-testid='patient-data-viewer']");
    await expect(viewer).toBeVisible();
    // Should have patient controls
    await expect(viewer.locator(".patient-viewer-controls")).toBeVisible();
  });
});
