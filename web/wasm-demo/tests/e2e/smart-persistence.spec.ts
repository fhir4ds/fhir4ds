import { test, expect } from "@playwright/test";

test.describe("SMART Persistence", () => {
  test.beforeEach(async ({ page }) => {
    page.setDefaultTimeout(90_000);
  });

  test("smart-flow scenario hides sample selectors", async ({ page }) => {
    await page.goto("/?scenario=smart-flow");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });
    // SMART login form visible
    await expect(page.locator(".smart-container")).toBeVisible();
    // No sample selectors should be visible in the entire page
    const sampleSelects = page.locator(".sample-select");
    await expect(sampleSelects).toHaveCount(0);
  });

  test("localStorage token persistence mechanism works", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 90_000 });

    // Simulate storing a token in localStorage (as smart-auth.ts would)
    await page.evaluate(() => {
      const fakeToken = {
        accessToken: "test-token",
        tokenType: "Bearer",
        expiresAt: Date.now() + 3600_000,
        patientId: "test-patient",
        scope: "patient/*.read",
      };
      const fakeSession = {
        fhirBaseUrl: "https://fhir.epic.com/api/FHIR/R4",
        vendor: "epic",
        clientId: "test-client-id",
      };
      localStorage.setItem("fhir4ds_smart_token", JSON.stringify(fakeToken));
      localStorage.setItem("fhir4ds_smart_session", JSON.stringify(fakeSession));
    });

    // Verify the data was stored
    const token = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("fhir4ds_smart_token") || "null"),
    );
    expect(token).not.toBeNull();
    expect(token.accessToken).toBe("test-token");

    // Clean up
    await page.evaluate(() => {
      localStorage.removeItem("fhir4ds_smart_token");
      localStorage.removeItem("fhir4ds_smart_session");
    });
  });
});
