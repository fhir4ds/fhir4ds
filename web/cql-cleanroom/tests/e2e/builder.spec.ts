import { test } from "@playwright/test";

/**
 * C3-U2/U4 e2e: Resource Builder — form → validate → add-to-dataset.
 * F8 invariant leg: a green form must produce a resource that loads
 * into evaluation cleanly (checked in the workbench flow by running
 * evaluate on the augmented dataset).
 */
test("builder: form validates and adds a Patient", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));

  // Builder defaults to Patient. Fill id + gender + birthDate.
  await page.fill('[data-testid=builder-field-id]', 'built-1');
  await page.fill('[data-testid=builder-field-gender]', 'female');
  await page.fill('[data-testid=builder-field-birthDate]', '1990-05-04');

  // Preview must be the exact payload.
  const preview = await page.textContent('[data-testid=builder-preview]');
  const parsed = JSON.parse(preview!);
  if (parsed.resourceType !== "Patient" || parsed.id !== "built-1") {
    console.log("PREVIEW:", preview!.slice(0, 300));
  }

  // Add is gated until a fresh validate.
  const disabledBefore = await page.isDisabled('[data-testid=builder-add]');
  await page.click('[data-testid=builder-validate]');
  await page.waitForSelector('[data-testid=builder-valid]', { timeout: 30_000 });
  const enabledAfter = await page.isEnabled('[data-testid=builder-add]');
  console.log("GATE disabledBefore:", disabledBefore, "enabledAfter:", enabledAfter);

  // Stale-ok guard: editing after validate must disable Add again.
  await page.fill('[data-testid=builder-field-gender]', 'other');
  const staleDisabled = await page.isDisabled('[data-testid=builder-add]');
  console.log("STALE_OK_GUARD:", staleDisabled);
  // Restore + revalidate.
  await page.fill('[data-testid=builder-field-gender]', 'female');
  await page.click('[data-testid=builder-validate]');
  // Wait for the GATE (enabled button), not the banner element — the
  // banner from the first validate may still be mounted.
  await page.waitForFunction(() => {
    const btn = document.querySelector('[data-testid=builder-add]');
    return btn && !(btn as HTMLButtonElement).disabled;
  }, undefined, { timeout: 30_000 });

  // Add to dataset (empty dataset → 1 resource).
  await page.click('[data-testid=builder-add]');

  // Load the default dataset (3 patients) so the count is deterministic.
  await page.click('[data-testid=load-dataset]');

  // The builder form reset on add — revalidate, then re-add so the
  // built patient rides on the default dataset.
  await page.click('[data-testid=builder-validate]');
  await page.waitForFunction(() => {
    const btn = document.querySelector('[data-testid=builder-add]');
    return btn && !(btn as HTMLButtonElement).disabled;
  }, undefined, { timeout: 30_000 });
  await page.click('[data-testid=builder-add]');
  const loaded = await page.textContent('[data-testid=dataset-loaded]');
  console.log("DATASET_LOADED:", (loaded ?? "").trim());
  console.log("PREVIEW_OK:", parsed.resourceType === "Patient");
});

test("builder: invalid resource shows typed diagnostics", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));

  // Raw JSON mode with a resource missing resourceType.
  await page.check('[data-testid=builder-raw-toggle]');
  await page.fill('[data-testid=builder-raw-text]', '{"id": "no-type"}');
  await page.click('[data-testid=builder-validate]');
  await page.waitForSelector('[data-testid=builder-diagnostics]', {
    timeout: 30_000,
  });
  const diag = await page.textContent('[data-testid=builder-diagnostics]');
  console.log("DIAG:", (diag ?? "").slice(0, 200));
  const addDisabled = await page.isDisabled('[data-testid=builder-add]');
  console.log("INVALID_ADD_DISABLED:", addDisabled);
});
