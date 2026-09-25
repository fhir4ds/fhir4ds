import { expect, test } from "@playwright/test";

/**
 * E3: cell-level evidence drill-in — clicking a population cell in the
 * results table opens the evidence popover for that (patient, population).
 */
test("population cell click opens evidence popover", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));

  await page.click("[data-testid=load-dataset]");
  await page.waitForSelector("[data-testid=dataset-loaded]");
  await page.waitForSelector("[data-testid=results-table]", { timeout: 90_000 });

  // Click p1's initial_population cell (demo: true)
  await page.click('[data-testid="cell-p1-initial_population"]');
  await page.waitForSelector("[data-testid=evidence-popover]", {
    timeout: 30_000,
  });
  await page.waitForSelector("[data-testid^=evidence-row-]", {
    timeout: 30_000,
  });

  const header = await page.textContent("[data-testid=evidence-popover] h3");
  if (!header?.includes("p1") || !header?.includes("initial_population")) {
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
  await page.click('[data-testid="cell-p2-initial_population"]');
  await page.waitForSelector("[data-testid=evidence-verdict]", {
    timeout: 30_000,
  });
  const verdict2 = await page.textContent("[data-testid=evidence-verdict]");
  if (!verdict2?.includes("false")) throw new Error(`verdict2: ${verdict2}`);
  expect(verdict2).toBeTruthy();
});
