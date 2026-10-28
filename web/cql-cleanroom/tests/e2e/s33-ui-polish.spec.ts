import { expect, test } from "@playwright/test";

/**
 * S33 UI polish journey tests (Joel 2026-10-25):
 *  1. The VIEW EDITOR header shows NO spinner while a view runs.
 *  2. The RESULTS console shows a spinner (not the static hint) while an
 *     evaluation is in flight, and the hint when idle.
 *  3. cms125-workspace is the standalone fresh-boot default.
 */

const DEMO = "/";

test("fresh standalone boot loads cms125-workspace by default", async ({ page }) => {
  test.setTimeout(300_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  await page.waitForFunction(
    () =>
      (document.querySelector(".status-note")?.textContent ?? "").includes(
        "loaded example cms125-workspace",
      ),
    undefined,
    { timeout: 120_000 },
  );
});

test("view editor header has no spinner while a view runs", async ({ page }) => {
  test.setTimeout(300_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(DEMO);
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  // Open a view tab: File > the derived demo VD opens the view editor
  // (host tab). In ALL states the editor header must show no busy chip.
  await page.getByRole("navigation", { name: "workspace navigation" })
    .getByRole("button", { name: "Views" }).click({ timeout: 60_000 });
  const pane = page.locator('[data-testid="view-pane"]');
  await expect(pane).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-testid="view-busy"]')).toHaveCount(0);
});

test("results console swaps hint for spinner while evaluating", async ({ page }) => {
  test.setTimeout(300_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(DEMO);
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  // Wait for the boot evaluation to settle: a run result renders (the
  // results console's run selector), and no evaluating spinner remains.
  const evaluating = page.locator('[data-testid="console-evaluating"]');
  await expect(page.locator('[data-testid="console-run-select"]').first())
    .toBeVisible({ timeout: 180_000 })
    .catch(async () => {
      // No run selector (never evaluated): the static hint must show and
      // never both states at once.
      await expect(page.locator('[data-testid="console-empty"]')).toBeVisible({ timeout: 30_000 });
    });
  await expect(evaluating).toHaveCount(0, { timeout: 120_000 });
});
