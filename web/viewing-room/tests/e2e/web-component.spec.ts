import { test, expect } from "@playwright/test";

/**
 * S1 web-component smoke (design §2): the <sqlonfhir-viewing-room> custom
 * element mounts the same app inside a shadow root and the engine boots.
 *
 * The stable-filename bundle (sqlonfhir-viewing-room.js) is served at the
 * preview root by the vite dual-entry build.
 */

test("web component mounts and boots the engine", async ({ page }) => {
  await page.goto("/web-component.html?data=local");
  const el = page.locator("sqlonfhir-viewing-room");
  await expect(el).toBeAttached();

  // Boot completes inside the shadow root (badge is ported-CSS visible).
  const badge = el.locator(".version-badge");
  await expect(badge).toBeVisible({ timeout: 120_000 });

  // The component carries a default height (85vh) via the host attribute.
  const height = await el.evaluate((node) =>
    getComputedStyle(node).height !== "" ? node.getAttribute("height") ?? "default" : "none",
  );
  expect(height).toBeTruthy();

  // suite="omop" attribute: OMOP-only gallery, defaulting to the person
  // sample over the committed 8-patient fixture slice.
  await expect(
    el.locator('[data-testid="output-table"] tbody tr'),
  ).toHaveCount(8, { timeout: 60_000 });
  const options = await el.locator("header select option").count();
  expect(options).toBe(5);
});
