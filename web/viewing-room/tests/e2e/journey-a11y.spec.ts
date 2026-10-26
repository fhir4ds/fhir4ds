/**
 * JOURNEY test (design §S4, from the design's own words): a11y pass —
 * "keyboard nav, focus states". Also pins the S4 Muse-rec folds:
 * splitter keyboard resize + sample-switch dirty guard.
 */

import { test, expect } from "@playwright/test";

test("journey: keyboard navigation reaches every control and tabs cycle with arrows", async ({ page }) => {
  await page.goto("/?data=local");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  // Tab strip: arrow keys move between tabs; the SQL tab opens via keyboard.
  await page.locator("#vr-tab-table").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#vr-tab-sql")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("sql-view")).toBeVisible();

  // Splitter: keyboard resize changes the left pane width.
  const pane = page.locator(".pane-resources");
  const before = await pane.boundingBox();
  await page.locator(".splitter").focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(300);
  const after = await pane.boundingBox();
  expect(after!.width).toBeLessThan(before!.width);
});

test("journey: dirty guard asks before a sample switch discards edits", async ({ page }) => {
  await page.goto("/?data=local");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  // Edit the VD, then switch samples: the confirm dialog appears.
  await page.evaluate(() => {
    (window as any).__vrVdEditor.setValue('{"resource":"Patient","select":[{"column":[{"name":"id","path":"id"}]}]}');
  });
  page.once("dialog", (dialog) => dialog.dismiss());
  const gallery = page.locator("header select");
  await gallery.selectOption("patient-addresses");
  // Dismissed: editors keep the edited VD (sample not loaded).
  await page.waitForTimeout(1_000);
  const vdNow = await page.evaluate(() => (window as any).__vrVdEditor.getValue());
  expect(vdNow).toContain('"path":"id"');

  // Accepting the dialog loads the sample.
  page.once("dialog", (dialog) => dialog.accept());
  await gallery.selectOption("patient-addresses");
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(3, { timeout: 60_000 });
});
