import type { Page } from "@playwright/test";

/**
 * S25 boot contract: fresh standalone boots auto-load the cms125
 * example and AUTO-CELLIFY the library (cells view is the default
 * surface for real content). Legacy specs that contract on the classic
 * text editor (`cql-editor`) must toggle cells OFF after boot.
 */

/** Wait for engine boot, then ensure the TEXT editor is visible. */
export async function bootTextReady(
  page: Page,
  url = "/",
  timeout = 150_000,
): Promise<void> {
  await page.goto(url);
  await page.waitForSelector(".version-badge", { timeout });
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  // The switch may render before the badge settles; give the cellify
  // effect a moment, then flip to text if cells are on.
  for (let i = 0; i < 30; i++) {
    const checked = await toggle.getAttribute("aria-checked").catch(() => null);
    if (checked === "true") {
      await toggle.click();
      await page.waitForTimeout(800);
      break;
    }
    if ((await page.locator("[data-testid=cql-editor]").count()) > 0) break;
    await page.waitForTimeout(500);
  }
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}

/** Open the Tests drawer (hosts the dataset tree) if not already open. */
export async function openTestsDrawer(page: import("@playwright/test").Page): Promise<void> {
  const tree = page.locator('[data-testid="dataset-tree"]');
  if (await tree.isVisible().catch(() => false)) return;
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.waitForTimeout(500);
}

/**
 * S25 demo-boot contract: fresh boots auto-load the cms125 showcase and
 * auto-cellify. Legacy specs that contract on the scratch demo
 * (CleanroomDemo + 3-resource dataset) must (a) wait out the example
 * load (it can land AFTER boot, racing an immediate reset), (b) reset
 * to the demo, (c) return to the text editor.
 */
export async function bootDemoReady(
  page: import("@playwright/test").Page,
  url = "/",
): Promise<void> {
  await bootTextReady(page, url);
  // Wait out the auto example load (the note appears when it lands; on
  // a restored non-pristine workspace no note appears — poll briefly).
  await page
    .waitForFunction(
      () =>
        (document.querySelector(".status-note")?.textContent ?? "").includes(
          "loaded example",
        ),
      undefined,
      { timeout: 30_000 },
    )
    .catch(() => undefined);
  await page.click("[data-testid=file-menu]");
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(800);
  // The reset lands in TEXT view (S25), but re-assert: cells may have
  // auto-opened between the reset click and now.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked").catch(() => "false")) === "true") {
    await toggle.click();
    await page.waitForTimeout(800);
  }
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}
