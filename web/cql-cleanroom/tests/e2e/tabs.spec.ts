import { expect, test } from "@playwright/test";

/**
 * WORKBENCH_REORG phase 3: the editor column is tabbed — one tab per
 * open workspace resource, kind-specific hosts, per-library Monaco
 * models, and library rename that rewrites the CQL header.
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

test.describe("editor tabs", () => {
  test("boot opens the entrypoint library tab with the editor visible", async ({
    page,
  }) => {
    await bootReady(page);
    await expect(page.locator("[data-testid=editor-tabs]")).toBeVisible();
    await expect(page.locator("[data-testid^=editor-tab-library-]")).toHaveCount(1);
    await expect(page.locator("[data-testid=cql-editor]")).toBeVisible();
  });

  test("nav clicks open kind tabs; the host replaces the editor; closing restores it", async ({
    page,
  }) => {
    await bootReady(page);
    // Measure tab via the Measures drawer.
    await page.click("[data-testid=nav-toggle-measures]");
    await page.locator("[data-testid^=nav-item-measure-]").first().click();
    await expect(page.locator("[data-testid^=editor-tab-measure-]")).toBeVisible();
    // The host replaces the editor (which stays mounted, hidden).
    await expect(page.locator("[data-testid=cql-editor]")).toBeHidden();
    // Strip switch back to the library tab.
    await page.locator("[data-testid^=editor-tab-library-]").first().click();
    await expect(page.locator("[data-testid=cql-editor]")).toBeVisible();
    // Close the measure tab: strip returns to the library tab only.
    await page.locator("[data-testid^=editor-tab-close-measure-]").click();
    await expect(page.locator("[data-testid^=editor-tab-measure-]")).toHaveCount(0);
    await expect(page.locator("[data-testid=cql-editor]")).toBeVisible();
  });

  test("valueset tab opens the single-valueset editor", async ({ page }) => {
    await bootReady(page);
    // Create a workspace valueset via the terminology drawer.
    await page.click("[data-testid=drawer-terminology-toggle]");
    await page.click("[data-testid=terminology-add]");
    await page.click("[data-testid=drawer-terminology-toggle]");
    // Open it from the Valuesets drawer.
    await page.click("[data-testid=nav-toggle-valuesets]");
    await page.locator("[data-testid^=nav-item-valueset-]").first().click();
    await expect(page.locator("[data-testid=valueset-editor]")).toBeVisible();
    await expect(page.locator("[data-testid=cql-editor]")).toBeHidden();
    // Codes table accepts a code.
    await page.locator("[data-testid=valueset-add-code]").click();
    await page
      .locator("[data-testid=valueset-codes] input[aria-label=code]")
      .last()
      .fill("1234-5");
    // Strip shows two tabs; closing the valueset tab restores the editor.
    await expect(page.locator(".editor-tab")).toHaveCount(2);
    await page.locator("[data-testid^=editor-tab-close-valueset-]").click();
    await expect(page.locator("[data-testid=cql-editor]")).toBeVisible();
  });

  test("library rename via context menu rewrites the CQL header and persists", async ({
    page,
  }) => {
    await bootReady(page);
    await page.click("[data-testid=nav-toggle-libraries]");
    await page.click("[data-testid=library-tab-0]", { button: "right" });
    await page.click("[data-testid=nav-context-menu] >> text=Rename library");
    const input = page.locator("[data-testid=library-tab-0-rename] input");
    await input.fill("RenamedDemo");
    await input.press("Enter");
    // Tab label mirrors the new name...
    await expect(
      page.locator("[data-testid^=editor-tab-library-]").first(),
    ).toContainText("RenamedDemo");
    // ...and the CQL header was rewritten (not just the workspace name).
    await expect(page.locator(".monaco-editor .view-lines")).toContainText(
      "library RenamedDemo",
      { timeout: 15_000 },
    );
    // Persisted across a reload (wait out the 800ms debounced autosave).
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await expect(page.locator(".monaco-editor .view-lines")).toContainText(
      "library RenamedDemo",
      { timeout: 30_000 },
    );
  });
});
