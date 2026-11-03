import { test, expect } from "@playwright/test";

// Journey tests for the FHIR REST API docs page (/docs/examples/serve-api).
// The page's promise: every read/operation example runs LIVE against the
// public demo server from the browser — no key for reads, a key field for
// writes, and the response is shown inline. These tests pin that promise in
// the page's own words: "runs live", "no key needed for reads",
// "No key, no writes".

async function run(page: import("@playwright/test").Page, label: RegExp) {
  const button = page.getByRole("button", { name: label });
  await button.waitFor({ state: "visible", timeout: 20_000 });
  // The response block is a sibling within the same TryIt container.
  const container = button.locator("xpath=ancestor::div[contains(@class,'tryit')]");
  await button.click();
  return container;
}

test.describe("FHIR REST API examples page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/docs/examples/serve-api");
  });

  test("page renders with tabs for curl, Python, and JavaScript", async ({
    page,
  }) => {
    await expect(page).toHaveTitle(/FHIR REST API/);
    await expect(
      page.getByRole("heading", { level: 1, name: "FHIR REST API" }),
    ).toBeVisible();

    await expect(page.getByRole("tab", { name: "curl" }).first()).toBeVisible();
    await expect(page.getByRole("tab", { name: "Python" }).first()).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "JavaScript" }).first(),
    ).toBeVisible();

    await page.getByRole("tab", { name: "Python" }).first().click();
    await expect(page.getByText("import requests").first()).toBeVisible();
  });

  test("health example runs live and shows the response inline", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const container = await run(page, /Run: health/);
    await expect(container.getByText(/HTTP 200/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(container.getByText(/"status": "ok"/)).toBeVisible();
  });

  test("stored ViewDefinition run returns slot rows anonymously", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const container = await run(page, /Run: run slot-view/);
    await expect(container.getByText(/HTTP 200/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(container.getByText(/"slot_id"/).first()).toBeVisible();
  });

  test("SQL-on-FHIR query with a status parameter returns joined rows", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const container = await run(page, /Run: free-slots-query/);
    await expect(container.getByText(/HTTP 200/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(container.getByText(/"actor_display"/).first()).toBeVisible();
  });

  test("write without a key is refused with 401 (no key, no writes)", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    // Leave the key field empty — the promise is a refusal, not silence.
    const container = await run(page, /Run: upsert a Slot/);
    await expect(container.getByText(/HTTP 401/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(container.getByText(/OperationOutcome/)).toBeVisible();
  });
});
