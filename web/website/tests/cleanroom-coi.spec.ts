import { test, expect } from "@playwright/test";

/**
 * Cross-origin isolation for the embedded cleanroom web component.
 *
 * DuckDB-WASM requires SharedArrayBuffer, which requires COOP/COEP.
 * In production the coi-serviceworker injects those headers on GH Pages;
 * in dev a plugin serves them from the dev server. This test boots the
 * real page in the DEV server (PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000)
 * and asserts the embed reaches Ready (version badge), not the
 * "Boot failed / SharedArrayBuffer is unavailable" error state.
 */

test("cleanroom embed boots under dev-server COOP/COEP", async ({ page }) => {
  await page.goto("/docs/examples/cql-cleanroom");

  const wc = page.locator("cql-cleanroom");
  await expect(wc).toBeAttached();

  // Boot overlay must clear (Ready state surfaces the version badge).
  const badge = wc.locator(".version-badge");
  await expect(badge.first()).toContainText("fhir4ds-v2", { timeout: 120_000 });

  // The hard-failure path renders a boot-error element instead — fail
  // fast with its text if it appears.
  const err = wc.locator("[data-testid=boot-error]");
  if (await err.count()) {
    throw new Error(`boot-error: ${await err.first().textContent()}`);
  }
});
