import { test, expect } from "@playwright/test";

// Embed + repeat-visit regression coverage (menu-click + default-example).
//
// Menus open on HOVER (mouseenter with a 220ms close grace) and the
// trigger click TOGGLES — a click-based walk can close a flyout that
// hover just opened. Tests below hover each level, matching real user
// pointer travel. File > Open > Examples items must be clickable inside
// the shadow-DOM embed (the outside-click close used e.target
// retargeting, closing the menu on mousedown and swallowing item
// onClicks — fixed with composedPath()).
//
// The default-example path must also survive the app's own auto-seeded
// artifacts (derived "vd_default" view + empty expected-reports slot),
// which auto-save persists on the first visit — previously those made
// isPristineWorkspace fail on every subsequent visit, permanently
// blocking the host default example (CMS69).

test.setTimeout(240_000);

async function bootReady(page: import("@playwright/test").Page) {
  const wc = page.locator("cql-cleanroom");
  await expect(wc).toBeAttached();
  const badge = wc.locator(".version-badge");
  await expect(badge.first()).toContainText("fhir4ds-v2", { timeout: 120_000 });
  const err = wc.locator("[data-testid=boot-error]");
  if (await err.count()) {
    throw new Error(`boot-error: ${await err.first().textContent()}`);
  }
  return wc;
}

test("embed File > Open > Examples menu items are clickable", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto("/docs/examples/cql-cleanroom/");
  const wc = await bootReady(page);
  await page.waitForTimeout(1_000);

  await wc.locator("[data-testid=file-menu]").click();
  await wc.locator("[data-testid=file-open]").hover();
  await expect(wc.locator("[data-testid=file-open-menu]")).toBeVisible();
  await wc.locator("[data-testid=file-examples]").hover();
  await expect(wc.locator("[data-testid=file-examples-menu]")).toBeVisible();

  await wc.locator("[data-testid=load-example-cms69]").click();
  const tabs = wc.locator("[data-testid=editor-tabs] .editor-tab-label");
  await expect(tabs.filter({ hasText: "CMS69" }).first()).toBeVisible({ timeout: 60_000 });
  await context.close();
});

test("embed with auto-seeded saved workspace still defaults to CMS69", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();

  // ---- Visit 1: boot the embed once so the app auto-seeds + saves ----
  await page.goto("/docs/examples/cql-cleanroom/");
  await bootReady(page);
  // Let auto-save (800ms debounce) persist the seeded state.
  await page.waitForTimeout(3_000);

  // ---- Visit 2 (reload): seeded state is now the saved workspace ----
  await page.reload();
  const wc = await bootReady(page);
  const tabs = wc.locator("[data-testid=editor-tabs] .editor-tab-label");
  await expect(tabs.filter({ hasText: "CMS69" }).first()).toBeVisible({ timeout: 60_000 });
  await context.close();
});
