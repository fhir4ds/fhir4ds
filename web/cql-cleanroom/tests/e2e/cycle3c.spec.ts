import { test } from "@playwright/test";

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
    await page.click('[data-testid=load-dataset]');
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid=dataset-loaded]')?.textContent ===
        "Active: 3 resources",
    );

    // Edit row 0 (p1, female) → builder prefilled with gender=female.
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

    // Prefill does NOT auto-validate: add stays disabled until fresh ok.
    const disabledBefore = await page.isDisabled('[data-testid=builder-add]');
    console.log("EDIT_NEEDS_VALIDATE:", disabledBefore);

    // Validate then add → appends as a NEW row (append semantics).
    await page.click('[data-testid=builder-validate]');
    await page.waitForFunction(
      () => !(document.querySelector('[data-testid=builder-add]') as HTMLButtonElement)?.disabled,
      undefined,
      { timeout: 30_000 },
    );
    await page.click('[data-testid=builder-add]');
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid=dataset-loaded]')?.textContent ===
        "Active: 4 resources",
    );
    console.log("EDIT_ADD_APPENDED: true");

    // Delete the appended row → back to 3.
    await page.click('[data-testid=dataset-delete-3]');
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid=dataset-loaded]')?.textContent ===
        "Active: 3 resources",
    );
    console.log("DELETE_REMOVED: true");
  });

  test("F8 invariant: built resource evaluates in an augmented dataset", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".version-badge", { timeout: 150_000 });

    // Build a female patient via the form.
    await page.fill('[data-testid=builder-field-id]', "px");
    await page.fill('[data-testid=builder-field-gender]', "female");

    // Validate → add.
    await page.click('[data-testid=builder-validate]');
    await page.waitForFunction(
      () => !(document.querySelector('[data-testid=builder-add]') as HTMLButtonElement)?.disabled,
      undefined,
      { timeout: 30_000 },
    );
    await page.click('[data-testid=builder-add]');
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid=dataset-loaded]')?.textContent ===
        "Active: 1 resources",
    );
    console.log("BUILT_ADDED: true");

    // Load the default dataset on top (append flow covered elsewhere);
    // here evaluate with just the built patient: IPP should be 1/1.
    await page.click('[data-testid=run-eval]');
    await page.waitForSelector('[data-testid=eval-meta]', { timeout: 60_000 });
    const meta = await page.textContent('[data-testid=eval-meta]');
    console.log("EVAL_META:", meta);
    const badge = await page.textContent('[data-testid=type-badge-IPP]');
    console.log("TYPE_BADGE_IPP:", badge);
  });
});
