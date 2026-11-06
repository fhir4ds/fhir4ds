import { expect, test } from "@playwright/test";

/**
 * End-to-end coverage for the live Auto-Coding example
 * (/docs/examples/autocoding).
 *
 * The demo loads the real fhir4ds-v2 wheel into Pyodide and calls the live
 * public terminology Space, so timings are generous and the run-flow test
 * tolerates (and retries past) the Space's engine-warmup state.
 */

const ENGINE_LOAD_MS = 180_000; // first Pyodide load: ~30 MB wheel + packages

test.describe("Auto-Coding example", () => {
  test("page renders the three-step narrative", async ({ page }) => {
    await page.goto("/docs/examples/autocoding");
    await expect(
      page.locator(".adc-step-title", { hasText: "FHIR data is messy" })
    ).toBeVisible();
    await expect(
      page.locator(".adc-step-title", { hasText: "Search by meaning" })
    ).toBeVisible();
    await expect(
      page.locator(".adc-step-title", { hasText: "The augmented resource" })
    ).toBeVisible();
    // presets
    for (const label of ["diabetes", "heart attack", "metformin"]) {
      await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
    }
  });

  test("engine loads and shows the ready badge", async ({ page }) => {
    await page.goto("/docs/examples/autocoding");
    const badge = page.locator(".adc-status-badge", {
      hasText: "fhir4ds · medterm4ds",
    });
    await expect(badge).toBeVisible({ timeout: ENGINE_LOAD_MS });
  });

  test("auto-run codes the default example end to end", async ({ page }) => {
    await page.goto("/docs/examples/autocoding");

    // Engine ready (badge) — the auto-run fires immediately after.
    await expect(
      page.locator(".adc-status-badge", { hasText: "fhir4ds · medterm4ds" })
    ).toBeVisible({ timeout: ENGINE_LOAD_MS });

    // Results table with at least one graded candidate row. The Space may
    // briefly be warming (error text shows); retrigger via a preset click.
    const table = page.locator(".adc-table tbody tr");
    for (let attempt = 0; attempt < 6; attempt++) {
      await expect(table.first()).toBeVisible({ timeout: 30_000 }).catch(() => {});
      if ((await table.count()) > 0) break;
      await page.getByRole("button", { name: "diabetes", exact: true }).click();
    }
    await expect(table.first()).toBeVisible();
    await expect(page.locator(".adc-table .badge").first()).not.toBeEmpty();

    // The augmented resource renders as a tree containing a SNOMED coding
    // with the audit extension and userSelected: false.
    // .first(): the Annotations demo (same NLP page) also renders an
    // .adc-tree-lg once its engine finishes — scope to the Auto-Coding one.
    const tree = page.locator(".adc-tree-lg").first();
    await expect(tree).toBeVisible({ timeout: 30_000 });
    await expect(tree.locator(".json-tree-key", { hasText: "coding" }).first()).toBeVisible();
    await expect(tree.getByText("snomed.info")).toBeVisible();
    const userSelected = tree.locator(".json-tree-row", { hasText: "userSelected" }).first();
    await expect(userSelected).toBeVisible();
    await expect(userSelected.locator(".json-tree-value")).toHaveText("false");
  });

  test("switching presets re-runs the search", async ({ page }) => {
    await page.goto("/docs/examples/autocoding");
    await expect(
      page.locator(".adc-status-badge", { hasText: "fhir4ds · medterm4ds" })
    ).toBeVisible({ timeout: ENGINE_LOAD_MS });

    await page.getByRole("button", { name: "heart attack", exact: true }).click();
    // The heart-attack example resolves to myocardial infarction.
    await expect(
      page.locator(".adc-tree-lg").getByText("Myocardial infarction")
    ).toBeVisible({ timeout: 60_000 });
  });
});
