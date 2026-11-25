import { test, expect, type Page } from "@playwright/test";

/**
 * FHIR4-49 — ValueSet cache seeding + LOUD fallback in the CQL playground.
 *
 * The browser engine answers ValueSet membership from the in-process C++
 * `g_valueset_cache`. Nothing seeds it in this app unless the dataset ValueSets
 * are wired through `cql_valueset_cache_add`. When the cache is empty,
 * `in_valueset` returns SQL NULL, so every population silently reads as empty —
 * a WRONG ANSWER, not an error. These tests pin both halves of the fix:
 *
 *   1. a valueset retrieve over the shipped demo ValueSet resolves (real rows),
 *   2. a valueset retrieve over a ValueSet nobody loaded is called out loudly
 *      in the UI instead of quietly reporting "no patients".
 */

const INIT_TIMEOUT = 90_000;

const DEMO_VALUESET_URL = "http://fhir4ds.org/ValueSet/diabetes";
const MISSING_VALUESET_URL = "http://example.org/ValueSet/never-loaded";

const DEMO_VALUESET_CQL = `library ValuesetDemo version '1.0.0'

using FHIR version '4.0.1'

context Patient

valueset "Demo Diabetes": '${DEMO_VALUESET_URL}'

define "Diabetes Conditions":
  Count([Condition: "Demo Diabetes"])

define "Has Diabetes":
  exists([Condition: "Demo Diabetes"])
`;

const UNLOADED_VALUESET_CQL = `library MissingValuesetDemo version '1.0.0'

using FHIR version '4.0.1'

context Patient

valueset "Not Loaded": '${MISSING_VALUESET_URL}'

define "Matches":
  Count([Condition: "Not Loaded"])
`;

/** Set the playground Monaco buffer (same helper the other specs use). */
async function setEditorCql(page: Page, cql: string): Promise<void> {
  const ok = await page.evaluate((text) => {
    const monaco = (window as any).monaco;
    if (!monaco) return false;
    const models = monaco.editor.getModels();
    if (!models.length) return false;
    models[0].setValue(text);
    return true;
  }, cql);
  expect(ok).toBeTruthy();
}

test.describe("ValueSet cache (FHIR4-49)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".status-dot.ready")).toHaveCount(2, {
      timeout: INIT_TIMEOUT,
    });
  });

  test("valueset retrieve over the shipped demo ValueSet returns matches", async ({
    page,
  }) => {
    await setEditorCql(page, DEMO_VALUESET_CQL);
    await page.click("button:has-text('Run')");

    const resultsTable = page.locator(".results-table");
    await expect(resultsTable).toBeVisible({ timeout: 90_000 });

    // The demo cohort has SNOMED diabetes Conditions; a seeded cache makes the
    // retrieve match, so at least one patient reports "Has Diabetes" = true.
    await expect(resultsTable.locator(".cell-bool--true").first()).toBeVisible({
      timeout: 15_000,
    });

    // …and the loud-fallback banner stays silent when every ValueSet is loaded.
    await expect(page.getByTestId("valueset-cache-warning")).toHaveCount(0);
  });

  test("valueset retrieve over an unloaded ValueSet is called out loudly", async ({
    page,
  }) => {
    await setEditorCql(page, UNLOADED_VALUESET_CQL);
    await page.click("button:has-text('Run')");

    const warning = page.getByTestId("valueset-cache-warning");
    await expect(warning).toBeVisible({ timeout: 90_000 });
    await expect(warning).toContainText(MISSING_VALUESET_URL);
    await expect(warning).toContainText("not loaded");
  });
});
