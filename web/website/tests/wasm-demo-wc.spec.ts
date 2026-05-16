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
  test("CQL Playground initializes DuckDB under cross-origin isolation", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const consoleMessages: string[] = [];
    page.on("console", (message) => consoleMessages.push(message.text()));
    page.on("pageerror", (error) => consoleMessages.push(error.message));

    const duckDbReady = page.waitForEvent("console", {
      predicate: (message) => message.text().includes("[DuckDB] Ready"),
      timeout: 45_000,
    });

    await page.goto("/docs/examples/cql-playground");
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(1, {
      timeout: 15_000,
    });
    await expect(page.locator("fhir4ds-demo")).toHaveCount(1);
    await expect
      .poll(() => page.evaluate(() => window.crossOriginIsolated), {
        timeout: 15_000,
      })
      .toBe(true);
    await duckDbReady;

    const allMessages = consoleMessages.join("\n");
    expect(allMessages).not.toContain("SharedArrayBuffer is unavailable");
    expect(allMessages).not.toContain("[DuckDB] Initialization failed");
  });

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

  test("SMART demo eagerly loads WC", async ({ page }) => {
    await page.goto("/docs/examples/smart-demo");
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(1, {
      timeout: 10_000,
    });
    await expect(page.locator("fhir4ds-demo")).toHaveCount(1);
    await expect(page.locator("button:has-text('Launch Demo')")).toHaveCount(0);
  });

  test("COI service worker preserves opener on SMART callback URLs", async ({
    page,
  }) => {
    await page.goto("/docs/examples/cql-playground");
    await expect
      .poll(() => page.evaluate(() => window.crossOriginIsolated), {
        timeout: 15_000,
      })
      .toBe(true);

    const headers = await page.evaluate(async () => {
      const normal = await fetch("/docs/examples/cql-playground");
      const callback = await fetch(
        "/docs/examples/smart-demo?code=test-code&state=test-state",
      );
      return {
        normalCoop: normal.headers.get("Cross-Origin-Opener-Policy"),
        normalCoep: normal.headers.get("Cross-Origin-Embedder-Policy"),
        callbackCoop: callback.headers.get("Cross-Origin-Opener-Policy"),
        callbackCoep: callback.headers.get("Cross-Origin-Embedder-Policy"),
      };
    });

    expect(headers).toEqual({
      normalCoop: "same-origin",
      normalCoep: "require-corp",
      callbackCoop: null,
      callbackCoep: null,
    });
  });

  test("SMART callback popup closes when token exchange fails under COI", async ({ page }) => {
    await page.goto("/docs/examples/cql-playground");
    await expect
      .poll(() => page.evaluate(() => window.crossOriginIsolated), {
        timeout: 15_000,
      })
      .toBe(true);

    await page.evaluate((endpoint) => {
      localStorage.setItem(
        "fhir4ds_smart_state",
        JSON.stringify({
          codeVerifier: "verifier",
          state: "state-popup",
          fhirBaseUrl: "https://example.test/fhir",
          vendor: "epic",
          clientId: "client-popup",
          tokenEndpoint: "https://smart-token.test/token",
          redirectUri: `${window.location.origin}/docs/examples/smart-demo`,
        }),
      );
      localStorage.setItem("fhir4ds_smart_popup_pending", "1");
    });

    const popupPromise = page.waitForEvent("popup");
    await page.evaluate(() => {
      window.open(
        "/docs/examples/smart-demo?code=auth-code&state=state-popup",
        "fhir4ds-smart-auth",
        "popup=yes,width=600,height=700,resizable=yes,scrollbars=yes",
      );
    });
    const popup = await popupPromise;

    await expect
      .poll(() => popup.isClosed(), { timeout: 10_000 })
      .toBe(true);
  });

  test("host page Docusaurus navigation is unaffected", async ({ page }) => {
    await page.goto("/docs/examples/cql-playground");
    await expect(page.locator("nav.navbar")).toBeVisible();
    // Should be able to navigate to another page
    await page.click("a:has-text('Examples')");
    await expect(page.locator("nav.navbar")).toBeVisible();
  });
});

test.describe("WasmDemoWC SMART callback", () => {
  test.use({ serviceWorkers: "block" });

  test("handles COOP-severed opener callback marker", async ({ page }) => {
    const tokenEndpoint = "https://smart-token.test/token";
    await page.route(tokenEndpoint, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({
          access_token: "website-token",
          token_type: "Bearer",
          expires_in: 3600,
          patient: "patient-website",
          scope: "launch/patient patient/Patient.read",
        }),
      });
    });

    await page.goto("/");
    await page.evaluate((endpoint) => {
      localStorage.setItem(
        "fhir4ds_smart_state",
        JSON.stringify({
          codeVerifier: "verifier",
          state: "state-website",
          fhirBaseUrl: "https://example.test/fhir",
          vendor: "epic",
          clientId: "client-website",
          tokenEndpoint: endpoint,
          redirectUri: `${window.location.origin}/docs/examples/smart-demo`,
          popupLaunch: true,
        }),
      );
    }, tokenEndpoint);

    await page.goto("/docs/examples/smart-demo?code=auth-code&state=state-website");
    await expect(page.locator("#fhir4ds-wc-bundle")).toHaveCount(1, {
      timeout: 10_000,
    });

    await expect
      .poll(
        () =>
          page.evaluate(() =>
            JSON.parse(localStorage.getItem("fhir4ds_smart_token") || "null"),
          ),
        { timeout: 10_000 },
      )
      .toMatchObject({
        accessToken: "website-token",
        patientId: "patient-website",
      });
  });
});
