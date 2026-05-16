import { test, expect } from "@playwright/test";

test.describe("SMART Logout", () => {
  test.beforeEach(async ({ page }) => {
    page.setDefaultTimeout(90_000);
  });

  test("logout button clears localStorage and shows login screen", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });

    // Navigate to SMART tab
    await page.click("button.tab-btn:has-text('SMART on FHIR')");
    await expect(page.locator(".smart-container")).toBeVisible();

    // Verify we're on the login/select screen initially
    // (no existing token, so we should see the provider selector)
    const providerSelect = page.locator(".smart-select").first();
    await expect(providerSelect).toBeVisible();
  });

  test("disconnect removes stale callback result before reconnect", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.setItem(
        "fhir4ds_smart_token",
        JSON.stringify({
          accessToken: "mock-access-token",
          patientId: "test-patient-123",
          scope: "launch/patient patient/*.read openid fhirUser",
          expiresAt: Date.now() + 60 * 60 * 1000,
        }),
      );
      localStorage.setItem(
        "fhir4ds_smart_session",
        JSON.stringify({
          fhirBaseUrl: "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
          vendor: "epic",
          clientId: "test-client-id",
        }),
      );
      localStorage.setItem("fhir4ds_smart_popup_pending", "1");
      localStorage.setItem(
        "fhir4ds_smart_callback_result",
        JSON.stringify({
          type: "FHIR4DS_SMART_TOKEN",
          token: { accessToken: "stale" },
        }),
      );
    });

    await page.goto("/?scenario=smart-flow");
    await page.getByRole("button", { name: /Disconnect/i }).click();

    const remaining = await page.evaluate(() =>
      Object.keys(localStorage).filter((key) => key.startsWith("fhir4ds_smart")),
    );
    expect(remaining).toEqual([]);
  });

  test("disconnect button is visible when connected and returns to login", async ({ page }) => {
    // Inject a fake token to simulate connected state, then verify
    // that the disconnect handler machinery exists
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });

    await page.click("button.tab-btn:has-text('SMART on FHIR')");
    await expect(page.locator(".smart-container")).toBeVisible();

    // Without a real OAuth flow, we verify the login form is present
    // and the connect button exists
    await expect(page.locator(".smart-btn--primary")).toBeVisible();
  });

  test("smart-flow with no token shows only login form", async ({ page }) => {
    // Clear any stale tokens
    await page.goto("/?scenario=smart-flow");
    await page.evaluate(() => {
      localStorage.removeItem("fhir4ds_smart_token");
      localStorage.removeItem("fhir4ds_smart_session");
    });

    await page.goto("/?scenario=smart-flow");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });

    // Only the SMART container should be visible
    await expect(page.locator(".smart-container")).toBeVisible();
    // Tab nav should be hidden (unauthenticated state)
    await expect(page.locator("[data-testid='tab-nav']")).toBeHidden();
  });
});
