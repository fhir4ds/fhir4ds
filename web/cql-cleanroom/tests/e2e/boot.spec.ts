import { test, expect } from "@playwright/test";

// Wait-for-boot doctrine: fresh Pyodide takes ~40-60s; never poll faster
// than the boot overlay can update.
test("boot reaches ready with wheel version", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "CQL Cleanroom" })).toBeVisible();
  const bootDone = page.waitForSelector("[data-testid=boot-step]", { state: "detached", timeout: 120_000 });
  await bootDone;
  // After overlay clears, the version badge shows the wheel version
  await expect(page.locator(".version-badge")).toContainText("fhir4ds-v2", { timeout: 10_000 });
});
