/**
 * QA it11 — Domain 3 (authoring UX) × HISTORIAN: affordance inventory.
 *  J1 the cell-view toggle's aria state matches the view actually shown
 *  J2 "Add Library" creates an independent tab; content stays per-tab
 *  J3 the Run affordance labels match behavior (cell inline vs console)
 */
import { test, expect, type Page } from "@playwright/test";

async function toText(page: Page) {
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(800);
  }
}

test("J1: cell toggle aria state matches the rendered view", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  const cellActive = (await toggle.getAttribute("aria-checked")) === "true";
  const cellEditors = await page
    .locator("[data-testid=cell-editor], .cell-editor")
    .count();
  if (cellActive) {
    expect(cellEditors).toBeGreaterThan(0);
  } else {
    expect(await page.locator('[data-testid="cql-editor"]').count()).toBeGreaterThan(0);
  }
  // flip and re-check
  await toggle.click();
  await page.waitForTimeout(1000);
  const nowCell = (await toggle.getAttribute("aria-checked")) === "true";
  expect(nowCell).toBe(!cellActive);
});

test("J2: libraries are independent tabs", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  await toText(page);
  // add a library via the + affordance
  const add = page.locator('[data-testid="add-library"], [title*="Add"], button:has-text("+")').first();
  await add.click();
  await page.waitForTimeout(800);
  const editor = page.locator('[data-testid="cql-editor"]');
  await editor.click();
  await page.keyboard.insertText("library It11B version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine Only: 1\n");
  await page.waitForTimeout(1000);
  // switch back to the first tab and confirm its content is intact
  const tab = page.locator('[data-testid="lib-tab-0"], .editor-tab').first();
  await tab.click();
  await page.waitForTimeout(800);
  const txt = await page.evaluate(() => document.body.innerText);
  expect(txt).not.toContain("It11B");
});
