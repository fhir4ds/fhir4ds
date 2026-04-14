/**
 * Web Component integration tests.
 *
 * Uses /wc-test.html — a minimal test harness that loads fhir4ds-demo.js
 * and renders <fhir4ds-demo> with scenario from URL params.
 *
 * Prerequisites: `npx vite build` must have run (fhir4ds-demo.js in dist/).
 */
import { test, expect } from "@playwright/test";

test.describe("Web Component", () => {
  test.beforeEach(async ({ page }) => {
    page.setDefaultTimeout(90_000);
  });

  test("fhir4ds-demo.js is present in build output", async ({ page }) => {
    const response = await page.request.get("/fhir4ds-demo.js");
    expect(response.status()).toBe(200);
    const contentType = response.headers()["content-type"] || "";
    expect(contentType).toContain("javascript");
  });

  test('<fhir4ds-demo scenario="cql-sandbox"> renders CQL Playground', async ({
    page,
  }) => {
    await page.goto("/wc-test.html?scenario=cql-sandbox");

    // The WC element should be visible
    const wcEl = page.locator("fhir4ds-demo");
    await expect(wcEl).toBeVisible({ timeout: 10_000 });

    // Wait for the app to fully load (loading overlay disappears inside shadow DOM)
    const loadingOverlay = page.locator("fhir4ds-demo >> .loading-overlay");
    await expect(loadingOverlay).toBeHidden({ timeout: 90_000 });

    // Tab navigation should NOT be visible (single scenario mode)
    const tabNav = page.locator(
      "fhir4ds-demo >> [data-testid='tab-nav']"
    );
    await expect(tabNav).toBeHidden();
  });

  test('<fhir4ds-demo scenario="cms-measures"> renders CMS', async ({
    page,
  }) => {
    await page.goto("/wc-test.html?scenario=cms-measures");

    const wcEl = page.locator("fhir4ds-demo");
    await expect(wcEl).toBeVisible({ timeout: 10_000 });

    // CMS shell should render inside shadow DOM
    const cmsShell = page.locator("fhir4ds-demo >> .cms-shell");
    await expect(cmsShell).toBeVisible({ timeout: 90_000 });
  });

  test("host page styles are not overridden by WC", async ({ page }) => {
    await page.goto("/wc-test.html?scenario=cql-sandbox");

    // Set host page background to a known color
    await page.evaluate(() => {
      document.body.style.background = "rgb(255, 0, 0)";
    });

    await page.waitForTimeout(1_000);

    // Host page background should still be red (WC dark styles are in Shadow DOM)
    const bodyBg = await page.evaluate(() =>
      window.getComputedStyle(document.body).backgroundColor
    );
    expect(bodyBg).toBe("rgb(255, 0, 0)");
  });

  test("Google Fonts link is injected into head", async ({ page }) => {
    await page.goto("/wc-test.html?scenario=cql-sandbox");

    // Wait for WC to initialize
    await expect(page.locator("fhir4ds-demo")).toBeVisible({ timeout: 10_000 });

    const fontLink = page.locator("link#fhir4ds-inter-font");
    await expect(fontLink).toHaveCount(1);
    const href = await fontLink.getAttribute("href");
    expect(href).toContain("fonts.googleapis.com");
    expect(href).toContain("Inter");
  });

  test("duplicate script loads do not double-register", async ({ page }) => {
    await page.goto("/wc-test.html?scenario=cql-sandbox");

    // Load the script a second time — should not throw
    const error = await page.evaluate(async () => {
      const script = document.createElement("script");
      script.type = "module";
      script.src = "/fhir4ds-demo.js?cachebust=2";
      document.head.appendChild(script);
      await new Promise((r) => setTimeout(r, 2_000));
      try {
        const wc = document.createElement("fhir4ds-demo");
        document.body.appendChild(wc);
        return null;
      } catch (e: any) {
        return e.message;
      }
    });

    expect(error).toBeNull();
  });
});
