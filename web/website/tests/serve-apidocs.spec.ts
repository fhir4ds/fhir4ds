import { test, expect } from "@playwright/test";

// Journey test for the server-hosted API documentation page
// (https://fhir4ds-bulk-publish-demo-server.hf.space/api-docs).
// The page's promise: same-origin executable docs — runners execute real
// requests against the server that serves the page.

const APIDOCS = "https://fhir4ds-bulk-publish-demo-server.hf.space/api-docs";

test.describe("Server-hosted /api-docs", () => {
  test("page renders with tabs and the health runner executes live", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await page.goto(APIDOCS);

    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "fhir4ds serve",
    );

    // Format tabs (JavaScript default) exist.
    const jsTab = page.getByRole("button", { name: "JavaScript" }).first();
    await expect(jsTab).toBeVisible();
    await expect(jsTab).toHaveAttribute("aria-selected", "true");

    // The health runner answers 200 with the live status payload.
    const runner = page
      .locator(".runner")
      .filter({ hasText: "GET /health" })
      .first();
    await runner.getByRole("button", { name: "▶ Run" }).click();
    await expect(runner.getByText(/HTTP 200/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(runner.getByText(/"status": "ok"/)).toBeVisible();
  });

  test("stored $run executes anonymously from the page", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(APIDOCS);
    const runner = page
      .locator(".runner")
      .filter({ hasText: "/ViewDefinition/slot-view/$run" })
      .first();
    await runner.getByRole("button", { name: "▶ Run" }).click();
    await expect(runner.getByText(/HTTP 200/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(runner.getByText(/"slot_id"/).first()).toBeVisible();
  });
});
