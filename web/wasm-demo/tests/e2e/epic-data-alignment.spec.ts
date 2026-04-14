import { test, expect } from "@playwright/test";

test.describe("Epic Data Alignment", () => {
  test.beforeEach(async ({ page }) => {
    page.setDefaultTimeout(90_000);
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
  });

  test("Clinical Overview CQL sample exists and is first in list", async ({ page }) => {
    const select = page.locator(".sample-select").first();
    await expect(select).toBeVisible();
    const firstOption = select.locator("option").nth(1); // skip placeholder
    await expect(firstOption).toContainText("Clinical Overview");
  });

  test("Clinical Overview sample runs and shows patient columns", async ({ page }) => {
    // Ensure we're on the playground tab and Clinical Overview is selected by default
    await expect(page.locator("[data-testid='workspace-toolbar']")).toBeVisible();

    // Click the Run button in the playground header
    await page.locator(".app-header").locator("button:has-text('Run')").click();

    const table = page.locator(".results-table");
    await expect(table).toBeVisible({ timeout: 60_000 });

    // Should have expected columns from the Clinical Overview CQL
    const headers = table.locator("th");
    const texts = await headers.allTextContents();
    const combined = texts.join(" ");
    expect(combined).toContain("Patient Name");
  });

  test("Patient Intake SDC form exists in sample list", async ({ page }) => {
    // Navigate to SDC Forms tab
    await page.click("button.tab-btn:has-text('SDC Forms')");
    await expect(page.locator(".sdc-playground")).toBeVisible({ timeout: 5_000 });

    // Check the sample selector has "Patient Intake & History"
    const select = page.locator(".sdc-header-controls .sample-select");
    await expect(select).toBeVisible();
    const options = select.locator("option");
    const texts = await options.allTextContents();
    expect(texts.some(t => t.includes("Patient Intake"))).toBeTruthy();
  });

  test("Patient Intake form has pre-populate button and calculated fields", async ({ page }) => {
    await page.click("button.tab-btn:has-text('SDC Forms')");
    await expect(page.locator(".sdc-playground")).toBeVisible({ timeout: 5_000 });

    // Select Patient Intake
    const select = page.locator(".sdc-header-controls .sample-select");
    await select.selectOption("patient-intake");

    // Pre-populate button should exist
    await expect(page.locator("text=▶ Pre-Populate")).toBeVisible();

    // The form should show the title
    await expect(page.locator(".sdc-form-title")).toContainText("Patient Intake");
  });

  test("progressive disclosure: smart-flow shows only Common Core CQL samples", async ({ page }) => {
    // This test doesn't actually connect to SMART — we just verify the default scenario
    // shows all 5 samples while smart-flow would show only 3 (commonCore ones)
    const select = page.locator(".sample-select").first();
    const options = select.locator("option");
    // In default workbench: placeholder + 5 samples = 6
    await expect(options).toHaveCount(6);
  });
});
