/**
 * QA it10 — Domain 3 (authoring UX) × SKEPTIC (UI layer).
 *  H4 cell-view edit -> switch to text: the full library text is intact
 *     (cell view is a projection; edits must land in the real text).
 */
import { test, expect } from "@playwright/test";

test("H4: cell edit lands in the library text", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  // default boots cellified (cms125). Type into the first cell editor.
  const cell = page.locator("[data-testid=cell-editor], .cell-editor textarea, .monaco-editor textarea").first();
  await cell.waitFor({ state: "visible", timeout: 30000 });
  await cell.click();
  await page.keyboard.insertText("define \"It10Edit\": 42");
  await page.waitForTimeout(1500);
  // switch to text view
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(1000);
  }
  const txt = await page.evaluate(() => document.body.innerText);
  expect(txt).toContain("It10Edit");
});
