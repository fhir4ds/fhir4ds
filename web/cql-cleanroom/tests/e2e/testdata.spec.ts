import { test, type Page } from "@playwright/test";
import { waitDatasetResources } from "./dataset";

/**
 * Test-data-authoring campaign e2e (FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md):
 * dataset patient tree, builder v2 recursion (F8 at depth ≥2), Bundle
 * export/import, Results drawers + View overrides persistence.
 */

async function bootReady(page: Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}

async function resetWorkspace(page: Page) {
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(1200);
}

test.describe("dataset patient tree", () => {
  test("groups demo resources by patient with flat-index rows", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.waitForSelector("[data-testid=dataset-tree]", {
      timeout: 30_000,
    });

    // Tree view is the default: the L2 patient list shows one row per
    // patient with a count pill.
    await page.waitForSelector("[data-testid=dataset-tree]", {
      timeout: 10_000,
    });
    await page.waitForSelector("[data-testid=dataset-group-p1]");
    await page.waitForSelector("[data-testid=dataset-group-p2]");
    await page.waitForSelector("[data-testid=dataset-group-p3]");

    // L3 drill-in (reorg 6e): clicking a patient row opens that
    // patient's type groups; dataset-back returns to L2.
    await page.click("[data-testid=dataset-group-p1]");
    await page.waitForSelector("[data-testid=dataset-back]");
    // REORG 6f: the detail slides out BESIDE the list (Maps push) —
    // the p2 row is still mounted AND visible, and patient rows no
    // longer carry a chevron (the list itself is the affordance).
    await page.waitForSelector("[data-testid=dataset-group-p2]");
    const carets = await page
      .locator(".dataset-patient-row .dataset-caret")
      .count();
    if (carets !== 0) throw new Error(`patient-row carets: ${carets}`);
    await page.click("[data-testid=dataset-type-toggle-p1-Patient]");

    // Flat STORAGE-index row testids preserved (p1's Patient = row 0).
    await page.waitForSelector("[data-testid=dataset-row-0]");
    const rows = await page
      .locator("[data-testid^=dataset-row-]")
      .count();
    if (rows !== 1) throw new Error(`tree rows: ${rows}`);

    await page.click("[data-testid=dataset-back]");
    await page.waitForSelector("[data-testid=dataset-group-p2]");
  });

});

test.describe("builder v2 recursion", () => {
  test("nested HumanName + repeatable given array build a valid Patient", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // WORKBENCH_REORG phase 5: the builder is a test editor tab now.
    await page.click("[data-testid=nav-add-tests]");
    await page.waitForSelector("[data-testid=builder-field-id]", {
      timeout: 15_000,
    });

    // Patient form: id + name (HumanName object) -> family + given[0..*].
    await page.fill("[data-testid=builder-field-id]", "p-tree-1");
    await page.click("[data-testid=builder-add-name]");
    await page.waitForSelector("[data-testid=builder-item-name-0]", {
      timeout: 10_000,
    });
    // Empty objects start COLLAPSED: expand the new name item first.
    await page.locator("[data-testid=builder-nested-name] .builder-tree-head")
      .first().click();
    await page.waitForTimeout(300);
    await page.fill("[data-testid=builder-field-family]", "Roe");
    await page.click("[data-testid=builder-add-given]");
    await page.fill("[data-testid=builder-field-given-0]", "Mary");
    await page.click("[data-testid=builder-add-given]");
    await page.fill("[data-testid=builder-field-given-1]", "Jane");

    // AUTO-SAVE: the valid form commits itself (~2s debounce); the new
    // patient appears as its own tree group.
    await page.waitForSelector("[data-testid=dataset-group-p-tree-1]", {
      timeout: 30_000,
    });
  });

  test("reference picker emits Reference objects with context default", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.waitForSelector("[data-testid=dataset-tree]");

    // Per-patient add lives in the L3 detail now (6h: L2 rows have no
    // per-row +): drill into p1, then add with the subject preseeded to
    // Patient/p1 (Observation has no subject-class field at top level
    // in the demo SD — Condition does). Use Condition.
    await page.click("[data-testid=dataset-group-p1]");
    await page.waitForSelector("[data-testid=dataset-add-p1]", {
      timeout: 10_000,
    });
    await page.click("[data-testid=dataset-add-p1]");
    // L3 drill-in: watch the auto-saved Condition land in p1's groups.
    await page.click("[data-testid=dataset-group-p1]");
    await page.selectOption("[data-testid=builder-type]", "Condition");
    await page.fill("[data-testid=builder-field-id]", "cond-p1-1");
    // AUTO-SAVE: commits when valid; wait for the row to appear in p1.
    await page.waitForFunction(
      () =>
        document
          .querySelector("[data-testid=dataset-group-p1]")
          ?.textContent?.includes("Condition") ?? false,
      undefined,
      { timeout: 30_000 },
    );

    // The condition lands INSIDE p1's group (subject preseed).
    const groupText = await page.textContent(
      "[data-testid=dataset-group-p1]",
    );
    if (!groupText?.includes("Condition")) {
      throw new Error(`condition not grouped under p1: ${groupText}`);
    }
  });
});

test.describe("bundle export/import", () => {
  test("export then replace-import round-trips the dataset", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.waitForSelector("[data-testid=dataset-tree]");

    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 60_000 }),
      (async () => {
        await page.click("[data-testid=export-menu]");
        await page.click("[data-testid=bundle-export]");
      })(),
    ]);
    const path = await download.path();
    if (!path) throw new Error("no download path");

    // Wipe + re-import in replace mode (6h: mode select lives in Settings).
    await page.click("[data-testid=workspace-reset]");
    await page.waitForTimeout(1200);
    await page.click("[data-testid=settings-menu]");
    await page.selectOption("[data-testid=bundle-mode]", "replace");
    await page.setInputFiles("[data-testid=bundle-import-input]", path);
    await waitDatasetResources(page, 3, 30_000);
  });
});

test.describe("console docking", () => {
  test("console docks bottom by default and toggles right and back", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // REORG phase 6b: the console lives under the editor by default.
    await page.waitForSelector(".app-main.dock-bottom");
    await page.waitForSelector("[data-testid=results-console]");
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });

    // Toggle to the right dock — the console becomes col2.
    await page.click("[data-testid=settings-menu]");
    await page.selectOption("[data-testid=settings-console-placement]", "right");
    await page.waitForSelector(".app-main.dock-right");
    await page.waitForSelector("[data-testid=results-console]");

    // And back.
    await page.selectOption("[data-testid=settings-console-placement]", "bottom");
    await page.waitForSelector(".app-main.dock-bottom");
    await resetWorkspace(page);
  });
});
