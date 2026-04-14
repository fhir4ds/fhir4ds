import { test, expect } from "@playwright/test";

test.describe("WASM Workbench Scenarios", () => {
  
  test("CQL Sandbox: should hide tabs and show CQL tool", async ({ page }) => {
    await page.goto("/?scenario=cql-sandbox");
    
    // Tab nav should NOT exist in the DOM
    const tabNav = page.locator("[data-testid='tab-nav']");
    await expect(tabNav).not.toBeAttached();
    
    // Header should be visible
    await expect(page.locator(".app-header")).toBeVisible();
    
    // CQL Editor should be visible (within WorkspaceLayout)
    await expect(page.locator(".pane-title:has-text('CQL Editor')")).toBeVisible();
  });

  test("SDC Forms: should hide tabs and show SDC tool", async ({ page }) => {
    await page.goto("/?scenario=sdc-forms");
    
    // Tab nav should NOT exist in the DOM
    const tabNav = page.locator("[data-testid='tab-nav']");
    await expect(tabNav).not.toBeAttached();
    
    // SDC header (app-header) should be visible
    await expect(page.locator(".sdc-playground .app-header")).toBeVisible();
    
    // Form Preview should be visible
    await expect(page.locator(".pane-title:has-text('Form Preview')")).toBeVisible();
  });

  test("Dynamic Switch: should change scenario when URL changes", async ({ page }) => {
    await page.goto("/?scenario=cql-sandbox");
    await expect(page.locator(".pane-title:has-text('CQL Editor')")).toBeVisible();
    
    // Navigate to SDC without reload
    await page.evaluate(() => {
      window.history.pushState({}, '', '/?scenario=sdc-forms');
    });
    
    // Should switch to SDC
    await expect(page.locator(".sdc-playground .app-header")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".pane-title:has-text('CQL Editor')")).not.toBeVisible();
  });
});
