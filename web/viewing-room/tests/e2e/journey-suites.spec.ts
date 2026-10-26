/**
 * JOURNEY test: sample suites — the ?suite= query param filters the
 * gallery to one optgroup (General / US Core / OMOP), the default
 * sample becomes the first of the active suite, and a clear-filter
 * affordance restores the full gallery.
 */

import { test, expect } from "@playwright/test";

test("journey: ?suite=omop filters the gallery and defaults to omop-patient", async ({ page }) => {
  await page.goto("/?suite=omop");

  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  // Default sample = first OMOP sample: person rows render.
  const table = page.getByTestId("output-table");
  await expect(table.locator("tbody tr")).not.toHaveCount(0, { timeout: 60_000 });
  await expect(table).toContainText("pat-001");

  // The dropdown shows ONLY the OMOP optgroup (4 samples, no General/US Core).
  const options = await page.locator("header select option").allTextContents();
  expect(options).toHaveLength(4);
  expect(options.some((o) => o.includes("Patient Demographics"))).toBe(false);
  expect(options.some((o) => o.includes("OMOP"))).toBe(true);

  // The optgroup label is present.
  await expect(page.locator("header select optgroup[label='OMOP']")).toHaveCount(1);

  // The filter pill names the suite and clears to the full gallery.
  const pill = page.getByTestId("suite-filter");
  await expect(pill).toBeVisible();
  await expect(pill).toContainText("OMOP");
  await pill.click();
  await page.waitForURL((url) => !url.searchParams.has("suite"));
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  const allOptions = await page.locator("header select option").allTextContents();
  expect(allOptions).toHaveLength(10);
});

test("journey: unfiltered gallery is grouped by suite", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  const groups = await page.locator("header select optgroup").evaluateAll((els) =>
    els.map((e) => (e as HTMLOptGroupElement).label),
  );
  expect(groups).toEqual(["General", "US Core", "OMOP"]);
  // No filter pill without the param.
  await expect(page.getByTestId("suite-filter")).toHaveCount(0);
});
