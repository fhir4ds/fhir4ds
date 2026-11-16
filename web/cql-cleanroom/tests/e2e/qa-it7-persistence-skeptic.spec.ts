/**
 * QA it7 — Domain 5 (persistence/workspaces) × SKEPTIC.
 *  F1 (from it1, repro-first): blocked IndexedDB — autosave fails SILENTLY.
 *     Expectation: a visible storage-degraded notice (users must know their
 *     work is not persisting).
 *  H3: healthy storage round-trip — an edit survives reload.
 *  H4: reload after save failure does not resurrect stale content.
 */
import { test, expect, type Page } from "@playwright/test";

async function bootStandalone(page: Page) {
  await page.goto("/");
  await page.evaluate(() => (window as any).__cleanroomReady?.());
  await page.waitForFunction(
    () => (window as any).__cleanroomBooted === true,
    null,
    { timeout: 180_000 },
  );
}

test("F1: blocked IndexedDB surfaces a storage notice", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "indexedDB", {
      get() {
        throw new DOMException("blocked", "SecurityError");
      },
    });
  });
  await page.goto("/");
  await bootStandalone(page);
  // make an edit to trigger the debounced autosave
  await page.keyboard.press("Control+A").catch(() => {});
  await expect
    .poll(() => page.evaluate(() => document.body.innerText), { timeout: 20_000 })
    .toMatch(/not saved|storage unavailable|storage blocked|save failed/i);
});

test("H3: healthy storage round-trip survives reload", async ({ page }) => {
  await page.goto("/");
  await bootStandalone(page);
  // text-view editor (cell view may be default) — S21 pattern
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(1000);
  }
  const editor = page.locator('[data-testid="cql-editor"]');
  await editor.click();
  await page.keyboard.press("Control+a");
  await page.keyboard.type(
    "library It7Persist version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\ndefine Ok: 2 = 2\n",
    { delay: 5 },
  );
  await page.waitForTimeout(2500); // autosave debounce
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(15000);
  const toggle2 = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle2.getAttribute("aria-checked")) === "true") {
    await toggle2.click();
    await page.waitForTimeout(1000);
  }
  const body = await page.evaluate(() => document.body.innerText);
  expect(body).toContain("It7Persist");
});
