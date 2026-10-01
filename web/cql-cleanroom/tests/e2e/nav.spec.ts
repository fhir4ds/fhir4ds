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
    await expect(page.locator("[data-testid=dataset-tree]")).toBeVisible();
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
    await expect(page.locator("[data-testid=dataset-tree]")).toBeVisible();

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

  test("fresh boot lists the default view + the measure's expected item", async ({
    page,
  }) => {
    await bootReady(page);
    // REORG 6d: every measure seeds one derived ViewDefinition, so
    // Views is clickable out of the box.
    await page.click("[data-testid=nav-toggle-views]");
    const viewItem = page.locator("[data-testid^=nav-item-view-]").first();
    await expect(viewItem).toBeVisible();
    await expect(viewItem).toContainText("View 1");

    // Expected Results: one item per measure — listed even with zero
    // authored expectations (empty-but-present), showing the patient
    // count.
    await page.click("[data-testid=nav-toggle-expected]");
    const expectedItem = page
      .locator("[data-testid^=nav-item-expected-]")
      .first();
    await expect(expectedItem).toBeVisible();
    await expect(expectedItem).toContainText(/patients/);

    // Clicking it opens the expectations editor (the expected grid).
    await expectedItem.click();
    await expect(page.locator("[data-testid=expected-grid]")).toBeVisible();
  });

  test("L2 panel and L3 detail slide-outs resize by drag and persist", async ({
    page,
  }) => {
    await bootReady(page);
    await page.click("[data-testid=nav-toggle-valuesets]");
    const panel = page.locator(".nav-panel-wrap > .nav-panel");
    const w0 = (await panel.boundingBox())?.width ?? 0;
    if (Math.round(w0) !== 198) throw new Error(`initial panel width: ${w0}`);

    // Drag the L2 handle +120px (clamps at 480).
    const handle = page.locator("[data-testid=nav-resize-panel]");
    const hb = (await handle.boundingBox())!;
    await page.mouse.move(hb.x + hb.width / 2, hb.y + 200);
    await page.mouse.down();
    await page.mouse.move(hb.x + hb.width / 2 + 120, hb.y + 200, { steps: 5 });
    await page.mouse.up();
    const w1 = (await panel.boundingBox())?.width ?? 0;
    if (Math.abs(w1 - (w0 + 120)) > 2) throw new Error(`post-drag width: ${w1}`);

    // Width persists across reload (localStorage).
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.click("[data-testid=nav-toggle-valuesets]");
    const w2 = (await page.locator(".nav-panel-wrap > .nav-panel").boundingBox())
      ?.width ?? 0;
    if (Math.abs(w2 - w1) > 2) throw new Error(`persisted width: ${w2}`);

    // L3 detail: open a patient drill-in and drag its handle wider.
    await page.click("[data-testid=nav-toggle-tests]");
    await page.locator("[data-testid^=dataset-group-]").first().click();
    await page.waitForSelector("[data-testid=nav-detail]", { timeout: 15_000 });
    const detail = page.locator("[data-testid=nav-detail]");
    const d0 = (await detail.boundingBox())?.width ?? 0;
    const dh = (await page.locator("[data-testid=nav-resize-detail]").boundingBox())!;
    await page.mouse.move(dh.x + dh.width / 2, dh.y + 200);
    await page.mouse.down();
    await page.mouse.move(dh.x + dh.width / 2 + 80, dh.y + 200, { steps: 5 });
    await page.mouse.up();
    const d1 = (await detail.boundingBox())?.width ?? 0;
    if (Math.abs(d1 - (d0 + 80)) > 2) throw new Error(`post-drag detail: ${d1}`);
  });
});
