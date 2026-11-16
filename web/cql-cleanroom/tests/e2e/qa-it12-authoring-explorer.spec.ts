/**
 * QA it12 — Domain 3 (authoring UX) × EXPLORER: chaos.
 *  V1 rapid tab toggling (cell<->text x10) — no state corruption
 *  V2 paste pathological text (null bytes strip, 10k-char line, emoji)
 *  V3 rapid typing bursts with auto-recalc live
 *  V4 toggle mid-typing — no lost keystrokes class (app stays alive)
 */
import { test, expect } from "@playwright/test";

test("V1: rapid view toggling keeps content", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  for (let i = 0; i < 10; i++) {
    await toggle.click();
    await page.waitForTimeout(120);
  }
  await page.waitForTimeout(1500);
  const txt = await page.evaluate(() => document.body.innerText);
  expect(txt).toContain("define");
  expect(txt.length).toBeGreaterThan(100);
});

test("V2: pathological pastes do not crash the editor", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(800);
  }
  const editor = page.locator('[data-testid="cql-editor"]');
  for (const payload of [
    "define \"Emoji😀\": 'héllo'",
    "x".repeat(10000),
    "define \"Nul\": '" + String.fromCharCode(0) + "'",
    "define \"Deep\": " + "(".repeat(200) + "1" + ")".repeat(200),
  ]) {
    await editor.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.insertText(payload).catch(() => undefined);
    await page.waitForTimeout(300);
  }
  // app still responsive
  const alive = await page.evaluate(() => !!document.querySelector(".app-footer, footer"));
  expect(alive).toBe(true);
});

test("V3: typing bursts with live auto-recalc stay responsive", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(800);
  }
  const editor = page.locator('[data-testid="cql-editor"]');
  await editor.click();
  await page.keyboard.press("Control+a");
  await page.keyboard.insertText("library V3 version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine A1: 1\n");
  for (let i = 2; i <= 12; i++) {
    await page.keyboard.press("End");
    await page.keyboard.insertText(`\ndefine A${i}: A${i - 1} + 1`);
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(4000);
  const txt = await page.evaluate(() => document.body.innerText);
  expect(txt).toContain("A12");
});

test("V4: toggle mid-typing keeps the app alive", async ({ page }) => {
  const step = async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
    try { const v = await fn(); console.log(`[V4 step] ${label} ok`); return v; }
    catch (e) { console.log(`[V4 step] ${label} FAIL ${String(e).slice(0, 120)}`); return undefined; }
  };
  await page.goto("/");
  await page.waitForTimeout(15000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  // fresh boots AUTO-CELLIFY (S25): only flip if we are in text view
  if ((await toggle.getAttribute("aria-checked")) !== "true") {
    await step("toggle1", () => toggle.click());
  }
  await page.waitForTimeout(500);
  const cell = page.locator("[data-testid=cell-editor], .cell-editor textarea, .monaco-editor textarea").first();
  await step("cellclick", () => cell.click());
  await step("insert", () => page.keyboard.insertText('define "Mid": 7'));
  await step("toggle2", () => toggle.click());
  await page.waitForTimeout(1500);
  const len = await step("eval", () => page.evaluate(() => document.body.innerText.length));
  expect(len).toBeGreaterThan(100);
});

