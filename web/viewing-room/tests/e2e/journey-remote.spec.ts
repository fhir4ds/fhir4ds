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

  // Default OMOP sample = the raw person reshape over the 25-patient
  // cohort: source ids only, no concept ids yet.
  const table = page.getByTestId("output-table");
  await expect(table.locator("tbody tr")).toHaveCount(25, { timeout: 120_000 });
  await expect(table).toContainText("person_source_value");

  // The person SQLQuery completes it: joined to the map, integer key,
  // source id preserved. Both halves of the tutorial are live samples.
  await page.locator("header select").selectOption("omop-person-sqlquery");
  // Wait for the SQLQuery's shape (the raw view also has 25 rows).
  await expect(
    table.locator("thead th", { hasText: "gender_concept_id" }),
  ).toHaveCount(1, { timeout: 240_000 });
  await expect(table.locator("tbody tr")).toHaveCount(25, { timeout: 60_000 });
  const personCells = await table.locator("tbody tr").evaluateAll((rows) =>
    rows.map((r) =>
      [...r.querySelectorAll("td")].map((td) => td.textContent?.trim() ?? ""),
    ),
  );
  const heads = await table.locator("thead th").evaluateAll((ths) =>
    ths.map((t) => t.textContent?.trim() ?? ""),
  );
  const idIdx = heads.indexOf("person_id");
  const srcIdx = heads.indexOf("person_source_value");
  const conceptIdx = heads.indexOf("gender_concept_id");
  expect(idIdx).toBeGreaterThanOrEqual(0);
  expect(srcIdx).toBeGreaterThanOrEqual(0);
  expect(conceptIdx).toBeGreaterThanOrEqual(0);
  for (const cells of personCells) {
    // Digits only: the integer key exceeds 2^53, so it arrives as text.
    expect(cells[idIdx]).toMatch(/^\d+$/);
    expect(cells[srcIdx]).toMatch(/^[0-9a-f-]{36}$/);
    expect(["8507", "8532"]).toContain(cells[conceptIdx]);
  }
  const personIds = new Set(personCells.map((c) => c[idIdx]));
  expect(personIds.size).toBe(25);

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

  // The same projection runs here, and every drug row's person_id must be
  // one of the person rows above — the OMOP foreign key holds in-browser.
  const medHeads = await table.locator("thead th").evaluateAll((ths) =>
    ths.map((t) => t.textContent?.trim() ?? ""),
  );
  const medIdIdx = medHeads.indexOf("person_id");
  const medPersonIds = await table.locator("tbody tr").evaluateAll(
    (rows, idx) =>
      rows.map((r) => r.querySelectorAll("td")[idx]?.textContent?.trim() ?? ""),
    medIdIdx,
  );
  for (const id of medPersonIds) {
    expect(personIds.has(id)).toBe(true);
  }
});
