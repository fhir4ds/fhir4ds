import { test, expect } from "@playwright/test";

// Fresh-profile default example: with no saved workspace (fresh
// IndexedDB), the workbench auto-loads the CMS69 featured example.
test("fresh visitor boots into CMS69 by default", async ({ browser }) => {
  const context = await browser.newContext(); // fresh storage
  const page = await context.newPage();
  await page.goto("/?example=cms69");
  const bootDone = page.waitForSelector("[data-testid=boot-step]", { state: "detached", timeout: 120_000 });
  await bootDone;
  // The CMS69 main library tab is open by default (include tabs follow)
  const tabs = page.locator("[data-testid=editor-tabs] .editor-tab-label");
  await expect(tabs.filter({ hasText: "CMS69" }).first()).toBeVisible({ timeout: 30_000 });
  // The parameters panel shows the prefilled Measurement Period (2026)
  await page.click("[data-testid=nav-toggle-parameters]");
  await page.locator("[data-testid^=nav-item-parameter-]").first().click();
  await page.waitForSelector('[data-testid="param-input-Measurement Period"]', {
    timeout: 30_000,
  });
  await expect(
    page.locator('[data-testid="param-input-Measurement Period"]'),
  ).toHaveValue(/2026/);
  await context.close();
});
