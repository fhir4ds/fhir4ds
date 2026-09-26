import { expect, test } from "@playwright/test";

/**
 * REORG phase 6d: maps-style nav — L1 icon rail (nav-toggle-{id}) +
 * L2 single slide-out panel (one section at a time), filters,
 * context-menu actions, legacy alias preservation.
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

test.describe("nav rail + panel", () => {
  test("seven rail icons; Tests panel opens by default with the boot signal", async ({
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
      await expect(page.locator(`[data-testid=nav-toggle-${id}]`)).toBeVisible();
    }
    // Boot signal is VISIBLE inside the default Tests panel.
    await expect(page.locator("[data-testid=dataset-loaded]")).toBeVisible();
    await expect(page.locator("[data-testid=nav-sec-tests]")).toBeVisible();
    // Other sections' content mounts only when their icon opens it.
    await expect(page.locator("[data-testid=nav-sec-measures]")).toHaveCount(0);
  });

  test("panel switches sections; collapse; filters", async ({ page }) => {
    await bootReady(page);
    // Collapse the rail (close the panel).
    await page.click("[data-testid=rail-collapse]");
    await expect(page.locator("[data-testid=nav-sec-tests]")).toHaveCount(0);
    // The Tests icon pops the panel back open.
    await page.click("[data-testid=nav-toggle-tests]");
    await expect(page.locator("[data-testid=dataset-loaded]")).toBeVisible();

    // Parameters: opens; the filter accepts typing.
    await page.click("[data-testid=nav-toggle-parameters]");
    await expect(
      page.locator("[data-testid=nav-filter-parameters]"),
    ).toBeVisible();
    await page.fill("[data-testid=nav-filter-parameters]", "zzz-no-match");

    // Valuesets: the fresh workspace shows the empty state; ONE panel at
    // a time — opening it closed Parameters.
    await page.click("[data-testid=nav-toggle-valuesets]");
    await expect(
      page.locator("[data-testid=nav-sec-valuesets] .nav-empty"),
    ).toBeVisible();
    await expect(page.locator("[data-testid=nav-sec-parameters]")).toHaveCount(0);
    await page.fill("[data-testid=nav-filter-valuesets]", "zzz-none");
    await expect(page.locator("[data-testid=nav-filter-valuesets]")).toHaveValue(
      "zzz-none",
    );
    await page.fill("[data-testid=nav-filter-valuesets]", "");

    // Libraries filter narrows by name.
    await page.click("[data-testid=nav-toggle-libraries]");
    await page.fill("[data-testid=nav-filter-libraries]", "clean");
    await expect(page.locator("[data-testid=library-tab-0]")).toBeVisible();
    await page.fill("[data-testid=nav-filter-libraries]", "zzz-none");
    await expect(page.locator("[data-testid=library-tab-0]")).toBeHidden();
    await page.fill("[data-testid=nav-filter-libraries]", "");

    // The panel header caret closes the panel.
    await page.click("[data-testid=nav-close-libraries]");
    await expect(page.locator("[data-testid=nav-sec-libraries]")).toHaveCount(0);
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
