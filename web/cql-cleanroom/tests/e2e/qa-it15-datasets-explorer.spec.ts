/**
 * QA it15 — Domain 4 (datasets/resource builder) × EXPLORER (chaos).
 *  V1 rapid-fire imports — 10 resources back-to-back; roster ends consistent
 *  V2 pathological resources — 64KB string field, deep nesting (50 levels),
 *     unicode/emoji ids rejected-or-handled per FHIR id rules
 *  V3 raw-mode chaos — paste garbage (binary-ish, huge, arrays) into the
 *     raw editor; error surfaces, app survives
 *  V4 duplicate-id re-import — replacing an existing resource updates the
 *     count, never duplicates the row
 *  V5 builder state under rapid add/remove toggling
 */
import { test, expect, type Page } from "@playwright/test";
import { bootTextReady } from "./bootText";

async function bootReady(page: Page) {
  await bootTextReady(page);
}

async function resetWorkspace(page: Page) {
  await page.click("[data-testid=file-menu]");
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(1200);
  await page.click('[data-testid="nav-toggle-tests"]');
}

async function importResource(page: Page, resource: object) {
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser", { timeout: 15_000 }),
    (async () => {
      await page.click("[data-testid=nav-import-tests]");
      await page.click("[data-testid=nav-import-tests-resource-json]");
    })(),
  ]);
  await chooser.setFiles({
    name: "resource.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(resource)),
  });
  const id = (resource as any).id ?? "";
  if (id) {
    await page.waitForFunction(
      (v) => (document.body.textContent ?? "").includes(v),
      id,
      { timeout: 20_000 },
    );
  } else {
    await page.waitForTimeout(600);
  }
}

test("V1: rapid-fire imports stay consistent", async ({ page }) => {
  await bootReady(page);
  await resetWorkspace(page);
  await page.waitForSelector("[data-testid=dataset-tree]");
  for (let i = 1; i <= 10; i++) {
    await importResource(page, {
      resourceType: i === 1 ? "Patient" : "Condition",
      id: `v1-${i}`,
      ...(i === 1 ? {} : { subject: { reference: "Patient/v1-1" } }),
    });
  }
  // one patient group holding all 10 resources
  const row = page.locator('[data-testid="dataset-group-v1-1"]');
  await expect(row).toBeVisible();
  await expect(row.locator(".dataset-count-pill")).toHaveText("10");
});

test("V2: pathological resources handled", async ({ page }) => {
  await bootReady(page);
  await resetWorkspace(page);
  await page.waitForSelector("[data-testid=dataset-tree]");
  // 64KB string field
  await importResource(page, {
    resourceType: "Patient", id: "v2-big", gender: "other",
    name: [{ family: "x".repeat(65_536) }],
  });
  // 50-level deep nesting in an extension
  let deep: any = { url: "urn:deep", valueString: "bottom" };
  for (let i = 0; i < 50; i++) deep = { url: `urn:l${i}`, extension: [deep] };
  await importResource(page, {
    resourceType: "Patient", id: "v2-deep", extension: [deep],
  });
  // both rows present; app alive
  await expect(page.locator('[data-testid="dataset-group-v2-big"]')).toBeVisible();
  await expect(page.locator('[data-testid="dataset-group-v2-deep"]')).toBeVisible();
  // invalid id (emoji) must NOT create a row — FHIR id charset; the
  // import is REJECTED with a status note naming the rule (F3 fix)
  await importResource(page, { resourceType: "Patient", id: "v2-😀", gender: "male" });
  await expect(page.locator('[data-testid="status-note"]')).toContainText(/id/i, { timeout: 10_000 });
  await expect(page.locator('[data-testid="dataset-group-v2-😀"]')).toHaveCount(0);
});

test("V3: raw-mode garbage never kills the app", async ({ page }) => {
  await bootReady(page);
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.click('[data-testid="nav-add-tests"]');
  await page.waitForSelector('[data-testid="builder-pane"]');
  const toggle = page.locator('[data-testid="builder-raw-toggle"]');
  await toggle.click();
  const rawText = page.locator('[data-testid="builder-raw-text"]');
  for (const garbage of [
    "not json at all",
    "[]",
    '"just a string"',
    '{"a":'.repeat(500),
    JSON.stringify({ arr: new Array(2000).fill("x") }),
  ]) {
    await rawText.fill(garbage.slice(0, 100_000));
    await toggle.click();
    await expect(page.locator('[data-testid="builder-raw-error"]')).toBeVisible({ timeout: 10_000 });
    await toggle.click(); // back to raw for the next round
  }
  // app still alive
  await expect(page.locator('[data-testid="builder-pane"]')).toBeVisible();
});

test("V4: duplicate-id re-import replaces, never duplicates", async ({ page }) => {
  await bootReady(page);
  await resetWorkspace(page);
  await page.waitForSelector("[data-testid=dataset-tree]");
  await importResource(page, { resourceType: "Patient", id: "v4p", gender: "female" });
  await importResource(page, { resourceType: "Condition", id: "v4c", subject: { reference: "Patient/v4p" } });
  await importResource(page, { resourceType: "Condition", id: "v4c", subject: { reference: "Patient/v4p" } });
  const row = page.locator('[data-testid="dataset-group-v4p"]');
  await expect(row.locator(".dataset-count-pill")).toHaveText("2");
});

test("V5: rapid add/remove element toggling stays coherent", async ({ page }) => {
  await bootReady(page);
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.click('[data-testid="nav-add-tests"]');
  await page.waitForSelector('[data-testid="builder-pane"]');
  for (let i = 0; i < 6; i++) {
    // the add-select is re-created each cycle (and may become scoped when
    // nested) — re-resolve it and its first real option every iteration
    const addSel = page.locator('[data-testid^="builder-add-element"]').first();
    await expect(addSel).toBeVisible({ timeout: 10_000 });
    const firstValue = await addSel.locator("option").evaluateAll(
      (opts) => (opts as HTMLOptionElement[]).find((o) => o.value)?.value ?? "",
    );
    if (!firstValue) break;
    await addSel.selectOption(firstValue);
    const removes = page.locator('[title="Remove this element from the resource"]');
    await expect(removes.first()).toBeVisible({ timeout: 10_000 });
    await removes.first().click();
    await page.waitForTimeout(150);
  }
  await expect(page.locator('[data-testid="builder-pane"]')).toBeVisible();
});
