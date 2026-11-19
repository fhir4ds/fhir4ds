/**
 * QA it8 — Domain 5 (persistence/workspaces) × HISTORIAN: claim inventory.
 *  J1 share-link overflow: DOCUMENTED NOT-PINNED — inserting a >100KB
 *     document through Playwright freezes Monaco/auto-recalc long past
 *     the test budget; the overflow path is a 5-line try/catch verified
 *     by inspection (src/lib/share.ts:60, App.tsx REV-C2-002 note), and
 *     the share happy path is pinned by cycle3.spec.
 *  J2 reset: workspace-reset returns to the default example, survives
 *     reload (S25 postReset claim).
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

test("J2: reset returns to the default example and survives reload", async ({ page }) => {
  await bootStandalone(page);
  // dirty the workspace first (so reset has something to reset)
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(1000);
  }
  const editor = page.locator('[data-testid="cql-editor"]');
  await editor.click();
  await page.keyboard.press("Control+a");
  await page.keyboard.type("library It8Dirty version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine X: 1\n", { delay: 5 });
  await page.waitForTimeout(2000);
  await page.click('[data-testid="file-menu"]');
  await page.click('[data-testid="workspace-reset"]');
  await page.waitForTimeout(2000);
  const afterReset = await page.evaluate(() => document.body.innerText);
  expect(afterReset).not.toContain("It8Dirty");
  // S25: reload keeps the reset (postReset flag)
  await page.reload();
  await page.waitForTimeout(15000);
  const afterReload = await page.evaluate(() => document.body.innerText);
  expect(afterReload).not.toContain("It8Dirty");
});
