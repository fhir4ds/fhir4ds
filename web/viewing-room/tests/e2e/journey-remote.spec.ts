/**
 * JOURNEY (network): the production default loads the FULL OMOP datasets
 * from the Hugging Face dataset — no ?data=local override. Skips when the
 * dataset is unreachable (environment availability, not a behavior skip).
 *
 * Proves: HF serves the NDJSON bundles with CORS (browser + DuckDB-WASM
 * fetch them directly), the 25-patient cohort renders, and the single
 * ConceptMap resolves every coded medication concept in-browser.
 */

import { test, expect } from "@playwright/test";

const HF_BASE = "https://huggingface.co/datasets/fhir4ds/omop-demo/resolve/main";

test.setTimeout(300_000);

test("journey: OMOP samples load the full Hugging Face datasets by default", async ({ page, request }) => {
  const probe = await request.get(`${HF_BASE}/patient-resources.ndjson`, {
    timeout: 30_000,
  }).catch(() => null);
  if (!probe || !probe.ok()) {
    test.skip(true, "Hugging Face dataset unreachable in this environment");
  }

  await page.goto("/?suite=omop");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });

  // Default OMOP sample = person over the full 25-patient cohort.
  const table = page.getByTestId("output-table");
  await expect(table.locator("tbody tr")).toHaveCount(25, { timeout: 120_000 });

  // Switch to the medications ViewDefinition sample (single RxNorm+CVX map).
  await page.locator("header select").selectOption("omop-drug-exposure");
  await expect(table.locator("tbody tr")).toHaveCount(1143, { timeout: 240_000 });
  // Concepts resolved through the full standard RxNorm ConceptMap.
  const resolved = await table.locator("tbody tr").evaluateAll((rows) => {
    return rows.filter((r) => {
      const cells = r.querySelectorAll("td");
      // drug_concept_id is the 3rd data column in the arm view.
      const v = cells[2]?.textContent?.trim();
      return v && v !== "null" && v !== "0";
    }).length;
  });
  expect(resolved).toBe(1143);  // 100% of coded rows resolve through the map
});
