/**
 * JOURNEY tests for S6 (Joel refinement #2, from his own words):
 *  - "the resources pane opens on the Browse tab … resources grouped by
 *    type on load, no clicks"
 *  - "auto-recalc makes the Run button redundant" — evaluate + remove;
 *    "extend to assert no Run button exists"
 * Kept affordance (documented gap): Retry boot after a failed boot (the
 * only state auto-recalc cannot recover from) — and on successful retry
 * the view auto-runs once (boot-retry gap closed in App).
 */

import { test, expect } from "@playwright/test";

test("journey: the app opens on the Browse tab with resources grouped, no clicks", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });

  // DEFAULT view is Browse: the grouped tree is present WITHOUT switching
  // tabs; the editor is one tab away.
  const group = page.getByTestId("resource-group-Patient");
  await expect(group).toBeVisible({ timeout: 30_000 });
  await expect(group.locator(".resource-viewer-count")).toHaveText("25");
  await expect(group).toHaveClass(/resource-highlight/); // VD targets Patient

  // The NDJSON editor is NOT shown; the Editor tab exists.
  await expect(page.getByTestId("resources-editor")).toBeHidden();
  await page.getByRole("tab", { name: "Editor" }).click();
  await expect(page.getByTestId("resources-editor")).toBeVisible();
});

test("journey: no Run button — auto-recalc is the only run path", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });

  // The Run button is gone entirely.
  await expect(page.getByRole("button", { name: /Run view/ })).toHaveCount(0);

  // Output still renders (auto-run on load) and edits still recalc.
  const table = page.getByTestId("output-table");
  await expect(table.locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });
  await page.evaluate(() => {
    (window as any).__vrVdEditor.setValue(
      JSON.stringify({ resource: "Patient", select: [{ column: [{ name: "id", path: "id" }] }] }, null, 2),
    );
  });
  await expect(table.locator("tbody tr")).toHaveCount(25, { timeout: 15_000 });
});
