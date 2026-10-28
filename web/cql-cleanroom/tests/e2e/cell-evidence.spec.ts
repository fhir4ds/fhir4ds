import { expect, test } from "@playwright/test";
import { bootTextReady, openTestsDrawer } from "./bootText";

/**
 * E3: cell-level evidence drill-in — clicking a population cell in the
 * results table opens the evidence popover for that (patient, population).
 */
test("population cell click opens evidence popover", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await bootTextReady(page);
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  // S25: / boots the cms125 showcase — reset to the scratch demo (p1/p2/p3,
  // auto-evaluated) before contracting on demo cells.
  await page.click("[data-testid=file-menu]");
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(800);

  await openTestsDrawer(page);
  await page.waitForSelector("[data-testid=dataset-tree]");
  await page.waitForSelector("[data-testid=results-table]", { timeout: 90_000 });

  // Click p1's Initial Population cell (demo: true). S26: run columns
  // use the measure's DISPLAY names ("Initial Population"), so the cell
  // testid carries the space.
  await page.click('[data-testid="cell-p1-Initial Population"]');
  await page.waitForSelector("[data-testid=evidence-popover]", {
    timeout: 30_000,
  });
  await page.waitForSelector("[data-testid^=evidence-row-]", {
    timeout: 30_000,
  });

  const header = await page.textContent("[data-testid=evidence-popover] h3");
  // S26 display-name columns: the popover header names the DISPLAY
  // population name ("Initial Population").
  if (!header?.includes("p1") || !header?.includes("Initial Population")) {
    throw new Error(`popover header: ${header}`);
  }
  const verdict = await page.textContent("[data-testid=evidence-verdict]");
  if (!verdict?.includes("true")) throw new Error(`verdict: ${verdict}`);

  // A contributing resource row is present (Patient/p1)
  const firstRow = await page
    .locator("[data-testid^=evidence-row-]")
    .first()
    .textContent();
  if (!firstRow?.includes("Patient/p1")) throw new Error(`row: ${firstRow}`);

  // Close
  await page.click("[data-testid=evidence-popover-close]");
  await page.waitForSelector("[data-testid=evidence-popover]", {
    state: "detached",
    timeout: 10_000,
  });

  // A false cell works too (p2 male → initial_population false)
  await page.click('[data-testid="cell-p2-Initial Population"]');
  await page.waitForSelector("[data-testid=evidence-verdict]", {
    timeout: 30_000,
  });
  const verdict2 = await page.textContent("[data-testid=evidence-verdict]");
  if (!verdict2?.includes("false")) throw new Error(`verdict2: ${verdict2}`);
  expect(verdict2).toBeTruthy();
});
