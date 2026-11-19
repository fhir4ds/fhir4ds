/**
 * QA it14 — Domain 4 (datasets/resource builder) × HISTORIAN.
 * UI-claims inventory: does every button/title/label do what it says?
 *  H1 roster row title "Show <pid>'s resources" — click focuses that patient
 *  H2 roster count pill matches the actual resource count for the patient
 *  H3 standalone hides the explicit-commit action bar (Validate/Add) —
 *     connected/disk-mode-only surface (S25 claim)
 *  H4 Raw JSON toggle aria-label switches modes; malformed JSON surfaces
 *     builder-raw-error
 *  H5 remove-element title ("Remove this element from the resource")
 *     removes the element
 */
import { test, expect, type Page } from "@playwright/test";
import { bootTextReady } from "./bootText";

async function bootReady(page: Page) {
  await bootTextReady(page);
}

async function openBuilderTab(page: Page) {
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.click('[data-testid="nav-add-tests"]');
  await page.waitForSelector('[data-testid="builder-pane"]', { timeout: 15_000 });
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
  // non-Patient resources group under their SUBJECT patient, so wait on the
  // resource id appearing anywhere in the document (tree row, toast, or
  // detail panel) rather than a per-id group testid.
  const id = (resource as any).id;
  await page.waitForFunction(
    (v) => (document.body.textContent ?? "").includes(v),
    id,
    { timeout: 20_000 },
  );
  await page.waitForTimeout(400);
}

test("H1/H2: roster title focuses the patient; count pill accurate", async ({ page }) => {
  await bootReady(page);
  await resetWorkspace(page);
  await page.waitForSelector("[data-testid=dataset-tree]");
  await importResource(page, { resourceType: "Patient", id: "h1p", gender: "female" });
  await importResource(page, { resourceType: "Condition", id: "c1", subject: { reference: "Patient/h1p" } });
  await importResource(page, { resourceType: "Condition", id: "c2", subject: { reference: "Patient/h1p" } });

  // standalone rows carry dataset-group-<pid> (ds-roster-* is connected-only)
  const row = page.locator('[data-testid="dataset-group-h1p"]');
  await expect(row).toBeVisible();
  // H1: the title claim, verbatim
  await expect(row).toHaveAttribute("title", "Show h1p's resources");
  // H2: count pill = group.rows.length (patient + 2 conditions = 3)
  await expect(row.locator(".dataset-count-pill")).toHaveText("3");
  await row.click();
  await expect(page.locator('[data-testid="dataset-pane"]')).toContainText("h1p");
});

test("H3: standalone hides the explicit-commit action bar", async ({ page }) => {
  await bootReady(page);
  await expect(page.locator('[data-testid="builder-validate"]')).toBeHidden();
  await expect(page.locator('[data-testid="builder-add"]')).toBeHidden();
});

test("H4: Raw JSON toggle aria + malformed JSON error row", async ({ page }) => {
  await bootReady(page);
  await openBuilderTab(page);
  const toggle = page.locator('[data-testid="builder-raw-toggle"]');
  await expect(toggle).toHaveAttribute("aria-label", "Raw JSON mode");
  await toggle.click();
  const rawText = page.locator('[data-testid="builder-raw-text"]');
  await expect(rawText).toBeVisible();
  await rawText.fill('{"resourceType": "Patient", ');
  // the raw→form commit (and its error) fires on the toggle itself
  await toggle.click();
  await expect(page.locator('[data-testid="builder-raw-error"]')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-testid="builder-raw-error"]')).toContainText(/Unexpected end|parse|JSON/i);
});

test("H5: add/remove element titles do what they say", async ({ page }) => {
  await bootReady(page);
  await openBuilderTab(page);
  // claim 1: the "+ add element…" select (title "Add a data element to the
  // resource") adds an element — pick its first real option
  const addSel = page.locator('[data-testid="builder-add-element"]').first();
  await expect(addSel).toHaveAttribute("title", "Add a data element to the resource");
  const firstValue = await addSel.locator("option").evaluateAll(
    (opts) => (opts as HTMLOptionElement[]).find((o) => o.value)?.value ?? "",
  );
  expect(firstValue).toBeTruthy();
  await addSel.selectOption(firstValue);
  const removes = page.locator('[title="Remove this element from the resource"]');
  await expect(removes.first()).toBeVisible({ timeout: 10_000 });
  const before = await removes.count();
  expect(before).toBeGreaterThan(0);
  // claim 2: "Remove this element from the resource" removes it
  await removes.first().click();
  await page.waitForTimeout(300);
  expect(await removes.count()).toBeLessThan(before);
});
