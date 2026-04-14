import { test, expect } from "@playwright/test";

test.describe("Scenario Routing", () => {
  test.beforeEach(async ({ page }) => {
    // Wait for DuckDB + Pyodide to be ready (loading overlay disappears)
    page.setDefaultTimeout(90_000);
  });

  test("default (no scenario) shows all 4 tabs", async ({ page }) => {
    await page.goto("/");
    // Wait for loading to finish
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    const tabNav = page.locator("[data-testid='tab-nav']");
    await expect(tabNav).toBeVisible();
    const buttons = tabNav.locator(".tab-btn");
    await expect(buttons).toHaveCount(4);
    await expect(buttons.nth(0)).toContainText("CQL Playground");
    await expect(buttons.nth(1)).toContainText("CMS Measures");
    await expect(buttons.nth(2)).toContainText("SMART on FHIR");
    await expect(buttons.nth(3)).toContainText("SDC Forms");
  });

  test("?scenario=cql-sandbox shows only CQL Playground with no tab nav", async ({ page }) => {
    await page.goto("/?scenario=cql-sandbox");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    // Tab nav should be hidden
    const tabNav = page.locator("[data-testid='tab-nav']");
    await expect(tabNav).toBeHidden();
    // CQL Playground content should be visible
    await expect(page.locator(".app-header")).toBeVisible();
    // CMS, SMART, SDC content should not exist
    await expect(page.locator(".smart-container")).not.toBeVisible();
    await expect(page.locator(".sdc-playground")).not.toBeVisible();
  });

  test("?scenario=cms-measures shows only CMS Measures with no tab nav", async ({ page }) => {
    await page.goto("/?scenario=cms-measures");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    // Tab nav should be hidden
    const tabNav = page.locator("[data-testid='tab-nav']");
    await expect(tabNav).toBeHidden();
    // CMS content should be visible
    await expect(page.locator(".cms-shell")).toBeVisible();
    // Other scenarios should not be visible
    await expect(page.locator(".smart-container")).not.toBeVisible();
    await expect(page.locator(".sdc-playground")).not.toBeVisible();
  });

  test("?scenario=sdc-forms shows only SDC Forms with no tab nav", async ({ page }) => {
    await page.goto("/?scenario=sdc-forms");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    // Tab nav should be hidden
    const tabNav = page.locator("[data-testid='tab-nav']");
    await expect(tabNav).toBeHidden();
    // SDC content should be visible
    await expect(page.locator(".sdc-playground")).toBeVisible();
    // CQL Playground and SMART should not be visible
    await expect(page.locator(".smart-container")).not.toBeVisible();
  });

  test("?scenario=smart-flow shows only the login form initially", async ({ page }) => {
    await page.goto("/?scenario=smart-flow");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    // Tab nav should be hidden (not authenticated)
    const tabNav = page.locator("[data-testid='tab-nav']");
    await expect(tabNav).toBeHidden();
    // SMART login form should be visible
    await expect(page.locator(".smart-container")).toBeVisible();
    // CQL Playground should not be visible
    await expect(page.locator(".app-header")).not.toBeVisible();
  });

  test("sample selector is visible in default scenario", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    await expect(page.locator(".sample-select").first()).toBeVisible();
  });

  test("?scenario=cql-sandbox shows sample selector", async ({ page }) => {
    await page.goto("/?scenario=cql-sandbox");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    await expect(page.locator(".sample-select").first()).toBeVisible();
  });
});
