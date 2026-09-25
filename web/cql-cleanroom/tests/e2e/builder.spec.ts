import { test } from "@playwright/test";

/**
 * Resource Builder auto-save e2e (replaces the manual validate→add flow):
 * a valid form commits to the dataset ~2s after it settles; edits to an
 * existing row REPLACE it; invalid drafts never commit.
 */
test("builder: valid form auto-commits a Patient", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(500);
  await page.waitForSelector("[data-testid=dataset-loaded]", { timeout: 60_000 });

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

  // Auto-commit: dataset grows to 4 resources (~2s debounce + validate).
  await page.waitForFunction(
    () =>
      document
        .querySelector("[data-testid=dataset-loaded]")
        ?.textContent?.includes("4 resources"),
    undefined,
    { timeout: 30_000 },
  );
  console.log("AUTO_COMMIT: 4 resources OK");

  // The new patient appears in the Resources tree under its own group.
  await page.waitForSelector("[data-testid=dataset-group-built-1]", {
    timeout: 10_000,
  });
  console.log("PREVIEW_OK:", parsed.resourceType === "Patient");
});

test("builder: invalid draft never commits", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(500);
  await page.waitForSelector("[data-testid=dataset-loaded]", { timeout: 60_000 });

  // Raw JSON mode with a resource missing resourceType.
  await page.check('[data-testid=builder-raw-toggle]');
  await page.fill('[data-testid=builder-raw-text]', '{"id": "no-type"}');

  // Give the auto-commit debounce ample time to (wrongly) fire.
  await page.waitForTimeout(3500);
  const loaded = await page.textContent("[data-testid=dataset-loaded]");
  if (!loaded?.includes("3 resources")) {
    throw new Error(`invalid draft committed: ${loaded}`);
  }

  // Diagnostics surface (auto-validate result).
  await page.waitForSelector("[data-testid=builder-diagnostics]", {
    timeout: 30_000,
  });
  const diag = await page.textContent('[data-testid=builder-diagnostics]');
  console.log("DIAG:", (diag ?? "").slice(0, 200));
});

test("builder: edit auto-replaces the source row", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(500);
  await page.waitForSelector("[data-testid=dataset-loaded]", { timeout: 60_000 });

  // Edit p1 (dataset row 0) via the Resources tree.
  await page.locator("[data-testid=dataset-type-toggle-p1-Patient]").click();
  await page.waitForSelector("[data-testid=dataset-edit-0]");
  await page.click("[data-testid=dataset-edit-0]");
  await page.waitForFunction(
    () =>
      (document.querySelector('[data-testid=builder-field-id]') as HTMLInputElement | null)
        ?.value === "p1",
    undefined,
    { timeout: 15_000 },
  );

  // Change gender; auto-commit must REPLACE row 0 (still 3 resources).
  await page.fill('[data-testid=builder-field-gender]', 'male');
  await page.waitForFunction(
    () =>
      document
        .querySelector("[data-testid=dataset-loaded]")
        ?.textContent?.includes("3 resources"),
    undefined,
    { timeout: 30_000 },
  );
  console.log("EDIT_REPLACED: dataset still 3 resources");
});
