/**
 * WasmDemoWC Docusaurus integration tests.
 *
 * Verifies the Web Component renders correctly in the Docusaurus site.
 * These tests require:
 *   1. wasm-demo built (`cd web/wasm-demo && npx vite build`)
 *   2. wasm-app deployed to website static (`cp -r dist/* ../website/static/wasm-app/`)
 *   3. website built (`cd web/website && npx docusaurus build`)
 *   4. website served (`npx docusaurus serve`)
 */
import { test, expect } from "@playwright/test";

test.describe("WasmDemoWC Docusaurus integration", () => {
  test("CQL Playground page loads WC script", async ({ page }) => {
    await page.goto("/docs/examples/cql-playground");
    // Docusaurus navbar should still be present
    await expect(page.locator("nav.navbar")).toBeVisible();
    // The WC script should be injected
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(1, {
      timeout: 10_000,
    });
    // The custom element should be in the DOM
    await expect(page.locator("fhir4ds-demo")).toHaveCount(1);
  });

  test("CMS Measures page loads WC script", async ({ page }) => {
    await page.goto("/docs/examples/cms-measures");
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(1, {
      timeout: 10_000,
    });
    await expect(page.locator("fhir4ds-demo")).toHaveCount(1);
  });

  test("SDC Forms page loads WC script", async ({ page }) => {
    await page.goto("/docs/examples/sdc-playground");
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(1, {
      timeout: 10_000,
    });
    await expect(page.locator("fhir4ds-demo")).toHaveCount(1);
  });

  test("SMART demo shows launch card (lazyLaunch)", async ({ page }) => {
    await page.goto("/docs/examples/smart-demo");
    // lazyLaunch=true: should show the launcher, not the WC yet
    await expect(
      page.locator("button:has-text('Launch Demo')")
    ).toBeVisible();
    // No fhir4ds-demo element yet
    await expect(page.locator("fhir4ds-demo")).toHaveCount(0);
    // The WC script should NOT be injected until Launch is clicked
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(0);
  });

  test("SMART demo launch card click loads WC", async ({ page }) => {
    await page.goto("/docs/examples/smart-demo");
    await page.click("button:has-text('Launch Demo')");
    // After clicking, the WC should be injected
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(1, {
      timeout: 10_000,
    });
    await expect(page.locator("fhir4ds-demo")).toHaveCount(1);
  });

  test("host page Docusaurus navigation is unaffected", async ({ page }) => {
    await page.goto("/docs/examples/cql-playground");
    await expect(page.locator("nav.navbar")).toBeVisible();
    // Should be able to navigate to another page
    await page.click("a:has-text('Examples')");
    await expect(page.locator("nav.navbar")).toBeVisible();
  });
});
