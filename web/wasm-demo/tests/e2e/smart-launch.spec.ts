import { test, expect } from "@playwright/test";

const INIT_TIMEOUT = 90_000;

test.describe("SMART on FHIR Tab", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Wait for the loading overlay to disappear (engines ready)
    await expect(page.locator(".loading-overlay")).toBeHidden({
      timeout: INIT_TIMEOUT,
    });
  });

  test("SMART tab button is visible and navigable", async ({ page }) => {
    const smartTab = page.locator("button.tab-btn", { hasText: "SMART on FHIR" });
    await expect(smartTab).toBeVisible();
    await smartTab.click();

    // Verify SMART container renders
    await expect(page.locator(".smart-container")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator(".smart-header h2")).toContainText("SMART on FHIR");
  });

  test("SMART tab shows provider selector form", async ({ page }) => {
    await page.click("button.tab-btn:has-text('SMART on FHIR')");

    // Provider select — Epic + Cerner + Custom Endpoint
    const providerSelect = page.locator("#provider-select");
    await expect(providerSelect).toBeVisible({ timeout: 5_000 });
    const options = providerSelect.locator("option");
    await expect(options).toHaveCount(3); // Epic + Cerner + Custom

    // Info box is shown for non-custom providers
    await expect(page.locator(".smart-info-box")).toBeVisible();

    // Connect button
    const connectBtn = page.locator(".smart-btn--primary");
    await expect(connectBtn).toBeVisible();
    await expect(connectBtn).toContainText("Connect");
  });

  test("custom provider shows FHIR URL and client ID fields", async ({ page }) => {
    await page.click("button.tab-btn:has-text('SMART on FHIR')");

    // Switch to Custom
    await page.locator("#provider-select").selectOption("custom");

    // FHIR URL and Client ID fields appear in custom mode
    await expect(page.locator("#fhir-url")).toBeVisible();
    await expect(page.locator("#client-id")).toBeVisible();
  });

  test("switching providers updates the info box", async ({ page }) => {
    await page.click("button.tab-btn:has-text('SMART on FHIR')");

    // Default shows Epic info box
    await expect(page.locator(".smart-info-box")).toContainText("Epic");

    // Switch to Cerner
    await page.locator("#provider-select").selectOption("cerner-sandbox");
    await expect(page.locator(".smart-info-box")).toContainText("Cerner");
  });

  test("all four tabs are accessible", async ({ page }) => {
    // Verify all 4 tab buttons exist
    const tabBtns = page.locator("button.tab-btn");
    await expect(tabBtns).toHaveCount(4);

    // Navigate through all tabs
    await page.click("button.tab-btn:has-text('CMS Measures')");
    await expect(page.locator(".cms-shell")).toBeVisible({ timeout: 5_000 });

    await page.click("button.tab-btn:has-text('SMART on FHIR')");
    await expect(page.locator(".smart-container")).toBeVisible({ timeout: 5_000 });

    await page.click("button.tab-btn:has-text('SDC Forms')");
    await expect(page.locator(".sdc-playground")).toBeVisible({ timeout: 5_000 });

    await page.click("button.tab-btn:has-text('CQL Playground')");
    await expect(page.locator(".workspace")).toBeVisible({ timeout: 5_000 });
  });
});
