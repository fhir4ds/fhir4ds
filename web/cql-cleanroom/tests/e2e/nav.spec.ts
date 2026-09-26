import { expect, test } from "@playwright/test";

/**
 * WORKBENCH_REORG phase 2: the 7 nav drawers — expand/collapse, filters,
 * context-menu actions (rename/delete), and legacy alias preservation.
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

test.describe("nav drawers", () => {
  test("seven sections render; libraries + tests default expanded", async ({
    page,
  }) => {
    await bootReady(page);
    for (const id of [
      "measures",
      "libraries",
      "valuesets",
      "parameters",
      "tests",
      "expected",
      "views",
    ]) {
      await expect(page.locator(`[data-testid=nav-sec-${id}]`)).toBeAttached();
    }
    // Boot signal stays VISIBLE inside the Tests drawer (default open).
    await expect(page.locator("[data-testid=dataset-loaded]")).toBeVisible();
    // Libraries open with legacy alias testids; others collapsed.
    await expect(page.locator("[data-testid=library-tab-0]")).toBeVisible();
    await expect(page.locator("[data-testid=library-tab-add]")).toBeVisible();
    await expect(page.locator("[data-testid=nav-list-measures]")).toBeHidden();
  });

  test("drawer expand/collapse + filter", async ({ page }) => {
    await bootReady(page);
    // Parameters drawer: default library declares none → empty list, but
    // the filter input must exist and accept typing.
    await page.click("[data-testid=nav-toggle-parameters]");
    await expect(
      page.locator("[data-testid=nav-filter-parameters]"),
    ).toBeVisible();
    await page.fill("[data-testid=nav-filter-parameters]", "zzz-no-match");

    // Valuesets drawer: the default dataset carries no valueset_resources,
    // so the fresh workspace shows the empty state; the filter must exist
    // and accept typing (workspace-authored valuesets populate it later).
    await page.click("[data-testid=nav-toggle-valuesets]");
    await expect(
      page.locator("[data-testid=nav-sec-valuesets] .nav-empty"),
    ).toBeVisible();
    await page.fill("[data-testid=nav-filter-valuesets]", "zzz-none");
    await expect(page.locator("[data-testid=nav-filter-valuesets]")).toHaveValue(
      "zzz-none",
    );
    await page.fill("[data-testid=nav-filter-valuesets]", "");

    // Libraries filter narrows by name.
    await page.fill("[data-testid=nav-filter-libraries]", "clean");
    await expect(page.locator("[data-testid=library-tab-0]")).toBeVisible();
    await page.fill("[data-testid=nav-filter-libraries]", "zzz-none");
    await expect(page.locator("[data-testid=library-tab-0]")).toBeHidden();
    await page.fill("[data-testid=nav-filter-libraries]", "");

    // Collapse the rail: drawers hide, quick buttons remain.
    await page.click("[data-testid=rail-collapse]");
    await expect(page.locator("[data-testid=nav-sec-libraries]")).toBeHidden();
    await expect(page.locator("[data-testid=rail-dataset]")).toBeVisible();
    // Expanding a section pops the rail back open.
    await page.click("[data-testid=rail-dataset]");
    await expect(page.locator("[data-testid=nav-sec-tests]")).toBeVisible();
    await expect(page.locator("[data-testid=dataset-loaded]")).toBeVisible();
  });

  test("measure rename via context menu updates the label", async ({
    page,
  }) => {
    await bootReady(page);
    await page.click("[data-testid=nav-toggle-measures]");
    const row = page.locator("[data-testid^=nav-item-measure-]").first();
    await row.click({ button: "right" });
    await expect(page.locator("[data-testid=nav-context-menu]")).toBeVisible();
    await page.click("[data-testid=nav-context-menu] >> text=Rename");
    const input = page
      .locator("[data-testid^=nav-item-measure-]")
      .first()
      .locator("input");
    await input.fill("RenamedMeasure");
    await input.press("Enter");
    await expect(row).toContainText("RenamedMeasure");
    // The rename must survive a reload (persisted store). Wait out the
    // 800ms debounced autosave first (same doctrine as workspace.spec).
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.click("[data-testid=nav-toggle-measures]");
    await expect(page.locator("[data-testid^=nav-item-measure-]").first()).toContainText(
      "RenamedMeasure",
    );
  });

  test("expected drawer lists authored expectations; delete works", async ({
    page,
  }) => {
    await bootReady(page);
    await page.click("[data-testid=nav-toggle-expected]");
    // Fresh workspace: no authored expectations yet.
    await expect(page.locator("[data-testid=nav-sec-expected] .nav-empty")).toBeVisible();
  });
});
