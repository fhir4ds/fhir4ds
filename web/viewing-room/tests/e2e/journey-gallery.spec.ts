/**
 * JOURNEY tests #5-6 (design §6, from the design's own words):
 *  - "the sample gallery loads each shipped sample and each renders rows"
 *    (design §5: six curated samples)
 *  - "collection:true columns render as JSON arrays in the table"
 */

import { test, expect } from "@playwright/test";

// Engine-verified row counts per sample (validated against the local
// fhir4ds viewdef generator + duckdb before pinning).
const SAMPLE_ROWS: Record<string, number> = {
  "patient-demographics": 35,
  "patient-addresses": 3,
  "patient-contact-address-union": 3,
  "us-core-blood-pressures": 2,
  "questionnaire-response-items": 5,
  "observation-values": 3,
  "omop-patient": 8,
  "omop-encounters": 464,
  "omop-drug-exposure": 418,
  "omop-drug-exposure-sqlquery": 524,
};

test("journey: every gallery sample loads and renders its rows", async ({ page }) => {
  await page.goto("/?data=local");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  const gallery = page.locator("header select");
  const options = await gallery.locator("option").all();
  expect(options.length).toBe(10);

  // Auto-accept dirty-guard prompts (auto-recalc marks editors dirty after
  // the first run; sample switching is this journey's subject).
  page.on("dialog", (d) => d.accept());

  // Sample switches are explicit user intent; auto-accept the dirty guard
  // (the editors carry only the auto-run debounce's stale marker). Let any
  // in-flight auto-run settle before switching — staging races otherwise
  // run the NEW view over the PREVIOUS sample's data.
  for (const opt of options) {
    const slug = await opt.getAttribute("value");
    const expected = SAMPLE_ROWS[slug!];
    expect(expected, `sample ${slug} has a row expectation`).toBeGreaterThan(0);
    await page.waitForTimeout(1_500);
    await gallery.selectOption(slug!);
    await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(expected, {
      timeout: 60_000,
    });
  }
});

test("journey: collection column renders as a JSON array", async ({ page }) => {
  await page.goto("/?data=local");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  const gallery = page.locator("header select");
  await gallery.selectOption("observation-values");
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(3, { timeout: 60_000 });
  // The component_codes / component_values collection cells render as JSON
  // arrays; the first row's code collection is the BP panel pair.
  const cells = page.getByTestId("output-table").locator("tbody tr td .json-cell");
  await expect(cells.first()).toHaveText(/\[\s*"8480-6"[\s,]+/);
});
