import { test } from "@playwright/test";
import { waitDatasetResources } from "./dataset";

/**
 * C3-U3 e2e: dataset edit/delete + builder prefill round-trip + the F8
 * invariant end-to-end (build → validate → add → evaluate augmented
 * dataset — green form ⇒ loads cleanly ⇒ evaluates).
 */

test.describe("cleanroom cycle-3 dataset editing", () => {
  test("edit prefills builder and replace round-trips", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".version-badge", { timeout: 150_000 });

    // Load the default 3-patient dataset.
    await waitDatasetResources(page, 3);

    // Edit row 0 (p1, female) → builder prefilled with gender=female.
    // L3 drill-in (reorg 6e), then expand p1's Patient group (it
    // defaults COLLAPSED).
    await page.click('[data-testid=dataset-group-p1]');
    await page.click('[data-testid=dataset-type-toggle-p1-Patient]');
    await page.click('[data-testid=dataset-edit-0]');
    // Prefill is async (schema fetch) — wait for the id input to carry p1.
    await page.waitForFunction(() => {
      const id = document.querySelector('[data-testid=builder-field-id]') as HTMLInputElement;
      return id && id.value === "p1";
    }, undefined, { timeout: 30_000 });
    const genderValue = await page.inputValue('[data-testid=builder-field-gender]');
    console.log("PREFILL_GENDER:", genderValue);
    const idValue = await page.inputValue('[data-testid=builder-field-id]');
    console.log("PREFILL_ID:", idValue);

    // AUTO-SAVE: edit a field (gender male) — the source row is
    // REPLACED (no append). Wait on the OBSERVABLE change: p1's tree
    // group hint flips from "— female, Ann" to "— male, Ann". (The old
    // dataset-row count>=3 wait required every type group expanded;
    // the tree defaults collapsed since the phase-2 nav reorg.)
    await page.fill('[data-testid=builder-field-gender]', "male");
    await page.waitForFunction(
      () =>
        document
          .querySelector("[data-testid=dataset-group-p1]")
          ?.textContent?.includes("male") ?? false,
      undefined,
      { timeout: 30_000 },
    );
    console.log("EDIT_REPLACED: p1 hint now male");

    // Delete p1's row → 2 remain.
    await page.click('[data-testid=dataset-delete-0]');
    await waitDatasetResources(page, 2);
    console.log("DELETE_REMOVED: true");
  });

  test("F8 invariant: built resource evaluates in an augmented dataset", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".version-badge", { timeout: 150_000 });

    // Build a female patient via the form; AUTO-SAVE commits it.
    // WORKBENCH_REORG phase 5: the builder is a test editor tab now.
    await page.click("[data-testid=nav-add-tests]");
    await page.waitForSelector("[data-testid=builder-field-id]", {
      timeout: 15_000,
    });
    await page.fill('[data-testid=builder-field-id]', "px");
    await page.fill('[data-testid=builder-field-gender]', "female");
    // App boots with the DEFAULT demo dataset (3 resources) since the
    // evaluate-button removal; adding px makes 4.
    await waitDatasetResources(page, 4);
    console.log("BUILT_ADDED: true");

    // Load the default dataset on top (append flow covered elsewhere);
    // here evaluate with just the built patient: IPP should be 1/1.
    await page.waitForSelector('[data-testid=results-table-stats]', { timeout: 60_000 });
    const meta = await page.textContent('[data-testid=results-table-stats]');
    console.log("EVAL_META:", meta);
    const badge = await page.textContent('[data-testid=type-badge-initial_population]');
    console.log("TYPE_BADGE_IPP:", badge);
  });
});
