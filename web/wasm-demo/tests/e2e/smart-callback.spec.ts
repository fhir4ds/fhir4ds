import { test, expect } from "@playwright/test";

const SMART_STATE_KEY = "fhir4ds_smart_state";
const SMART_TOKEN_KEY = "fhir4ds_smart_token";

test.describe("SMART OAuth callback", () => {
  test("popup callback completes from persisted SMART state without window.opener", async ({ page }) => {
    await page.route("**/smart-token", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "test-token",
          token_type: "Bearer",
          expires_in: 3600,
          patient: "patient-123",
          scope: "launch/patient patient/Patient.read",
        }),
      });
    });

    await page.goto("/");
    await page.evaluate(
      (stateKey) => {
        localStorage.setItem(
          stateKey,
          JSON.stringify({
            codeVerifier: "verifier",
            state: "state-123",
            fhirBaseUrl: "https://example.test/fhir",
            vendor: "epic",
            clientId: "client-123",
            tokenEndpoint: `${window.location.origin}/smart-token`,
            redirectUri: `${window.location.origin}/`,
            popupLaunch: true,
          }),
        );
      },
      SMART_STATE_KEY,
    );

    await page.goto("/?code=auth-code&state=state-123");
    await expect(page.getByText("Authorization complete!")).toBeVisible({
      timeout: 10_000,
    });

    const token = await page.evaluate((tokenKey) => {
      return JSON.parse(localStorage.getItem(tokenKey) || "null");
    }, SMART_TOKEN_KEY);
    expect(token).toMatchObject({
      accessToken: "test-token",
      patientId: "patient-123",
    });
  });
});
