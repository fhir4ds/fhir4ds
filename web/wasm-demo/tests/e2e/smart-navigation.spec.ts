import { test, expect } from "@playwright/test";
import { getAccessToken } from "../../src/lib/smart-auth";

/**
 * SMART on FHIR navigation tests.
 *
 * Tests that simulating a "return to page with stored token" shows the correct
 * tabs (CQL Playground + SDC Forms) and NOT the SMART login screen.
 *
 * These tests inject a mock token into localStorage before navigation to
 * simulate the state after a successful OAuth login.
 */

// A mock token that appears valid (expiresAt 1 hour from now)
function makeMockToken() {
  return {
    accessToken: "mock-access-token",
    patientId: "test-patient-123",
    scope: "launch/patient patient/*.read openid fhirUser",
    expiresAt: Date.now() + 60 * 60 * 1000, // 1 hour
  };
}

const SMART_TOKEN_KEY = "fhir4ds_smart_token";
const SMART_SESSION_KEY = "fhir4ds_smart_session";

test.describe("SMART on FHIR navigation — page return with stored session", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate once to set the origin context, then inject mock token
    await page.goto("/");
    await page.evaluate(({ key, token, sessionKey, session }) => {
      localStorage.setItem(key, JSON.stringify(token));
      localStorage.setItem(sessionKey, JSON.stringify(session));
    }, {
      key: SMART_TOKEN_KEY,
      token: makeMockToken(),
      sessionKey: SMART_SESSION_KEY,
      session: { fhirBaseUrl: "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4", vendor: "epic", clientId: "test-client-id" },
    });
  });

  test.afterEach(async ({ page }) => {
    // Clean up mock token
    await page.evaluate(({ key, sessionKey }) => {
      localStorage.removeItem(key);
      localStorage.removeItem(sessionKey);
    }, { key: SMART_TOKEN_KEY, sessionKey: SMART_SESSION_KEY });
  });

  test("smart-flow with stored token shows CQL Playground tab (not SMART login)", async ({ page }) => {
    // Navigate to smart-flow scenario with stored token already in localStorage
    await page.goto("/?scenario=smart-flow");
    await page.waitForTimeout(2000);

    // The tab nav should NOT show SMART on FHIR tab when authenticated
    const smartTab = page.locator("button.tab-btn:has-text('SMART on FHIR')");
    await expect(smartTab).not.toBeVisible({ timeout: 5_000 });

    // CQL Playground tab SHOULD be visible
    const playgroundTab = page.locator("button.tab-btn:has-text('CQL Playground')");
    await expect(playgroundTab).toBeVisible({ timeout: 5_000 });

    // SDC Forms tab SHOULD be visible
    const formsTab = page.locator("button.tab-btn:has-text('SDC Forms')");
    await expect(formsTab).toBeVisible({ timeout: 5_000 });
  });

  test("smart-flow with stored token does NOT show SMART login provider selector", async ({ page }) => {
    await page.goto("/?scenario=smart-flow");
    await page.waitForTimeout(2000);

    // The SMART provider selector (Connect button) should NOT be visible
    const connectBtn = page.locator("button.smart-btn--primary");
    await expect(connectBtn).not.toBeVisible({ timeout: 5_000 });
  });

  test("smart-flow with stored token shows CQL Playground as active default tab", async ({ page }) => {
    await page.goto("/?scenario=smart-flow");
    await page.waitForTimeout(2000);

    // The CQL Playground header should be visible (active tab renders its content)
    const header = page.locator(".app-header");
    await expect(header).toBeVisible({ timeout: 10_000 });
  });

  test("smart-flow without stored token shows SMART launch UI", async ({ page }) => {
    // Remove the mock token we set in beforeEach
    await page.evaluate(({ key }) => localStorage.removeItem(key), { key: SMART_TOKEN_KEY });
    await page.goto("/?scenario=smart-flow");
    await page.waitForTimeout(2000);

    // Without stored token, the SMART launch page is rendered directly
    // (showTabNav=false for smart-flow before auth). Look for the heading.
    const smartHeading = page.locator("h2").filter({ hasText: "SMART on FHIR" });
    await expect(smartHeading).toBeVisible({ timeout: 5_000 });

    // CQL Playground should NOT be visible
    const playgroundTab = page.locator("button.tab-btn:has-text('CQL Playground')");
    await expect(playgroundTab).not.toBeVisible({ timeout: 5_000 });
  });
});
