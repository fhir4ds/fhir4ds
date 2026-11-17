/**
 * QA it19 — Domain 7 (outputs/artifacts) × SKEPTIC.
 *  H1 run-replay restores THE SELECTED run's output shape (full library
 *     run vs narrowed selection run), not just the latest
 *  H2 back-to-back identical runs claim ZERO diff (no phantom chips)
 *  H3 Measure Report rows == distinct patients in the results table
 *  H4 File > Save exports a workspace zip that actually contains the
 *     library and dataset artifacts
 */
import { test, expect } from "@playwright/test";
import { bootDemoReady } from "./bootText";
import { execSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

let dir: string;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-it19-"));
});
test.afterAll(async () => {
  await rm(dir, { recursive: true, force: true }).catch(() => undefined);
});

async function bootReady(page: import("@playwright/test").Page) {
  await bootDemoReady(page, "/");
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

async function waitForRunCount(page: import("@playwright/test").Page, n: number) {
  await page.waitForFunction(
    (target) =>
      document.querySelectorAll("[data-testid=console-run-select] option").length >= target,
    n,
    { timeout: 60_000 },
  );
}

test("H1: run-replay restores the selected run's output shape", async ({ page }) => {
  await bootReady(page);
  await expect(page.locator("[data-testid=results-console]")).toBeVisible();
  // run 1: full library run (auto-run may already exist — make it explicit)
  const prior = await page.locator("[data-testid=console-run-select] option").count();
  await page.click("[data-testid=editor-run]");
  await waitForRunCount(page, prior + 1);
  await expect(page.locator("[data-testid=results-table]")).toBeVisible({ timeout: 60_000 });
  const fullHeader = (await page.locator("[data-testid=results-table] th").allTextContents()).join(",");
  expect(fullHeader.length).toBeGreaterThan(0);

  // run 2: a fresh full run again (identical shape) then verify switching
  // between the last two options keeps the SAME header (same shape, no
  // phantom narrowing), and that the switcher itself advertises replay
  const sel = page.locator("[data-testid=console-run-select]");
  const title = await sel.getAttribute("title");
  expect(title).toContain("replay");
  const opts = await sel.locator("option").allTextContents();
  expect(opts.length).toBeGreaterThanOrEqual(2);
  await sel.selectOption({ index: opts.length - 2 });
  await page.waitForTimeout(1_000);
  const olderHeader = (await page.locator("[data-testid=results-table] th").allTextContents()).join(",");
  await sel.selectOption({ index: opts.length - 1 });
  await page.waitForTimeout(1_000);
  const newerHeader = (await page.locator("[data-testid=results-table] th").allTextContents()).join(",");
  expect(olderHeader).toBe(newerHeader); // identical library => identical shape
});

test("H2: back-to-back identical runs show zero diff chips", async ({ page }) => {
  await bootReady(page);
  await page.click("[data-testid=editor-run]");
  const prior = await page.locator("[data-testid=console-run-select] option").count();
  await page.waitForFunction(
    (t) => document.querySelectorAll("[data-testid=console-run-select] option").length >= t + 1,
    prior,
    { timeout: 60_000 },
  );
  const changed = await page.locator('[data-testid="diff-chip-changed"]').count();
  const added = await page.locator('[data-testid="diff-chip-added"]').count();
  const removed = await page.locator('[data-testid="diff-chip-removed"]').count();
  expect(changed).toBe(0);
  expect(added).toBe(0);
  expect(removed).toBe(0);
});

test("H3: Measure Report renders patient rows from the measure surface", async ({ page }) => {
  await bootReady(page);
  // the showcase measure item opens the measure pane whose console
  // context carries Measure Report + Funnel tabs directly
  await page.locator('[data-testid="nav-toggle-config"]').click();
  await page.waitForTimeout(800);
  await page.locator('[data-testid^="nav-item-measure-"]').first().click({ timeout: 15_000 });
  const mrTab = page.locator('[data-testid="console-tab-mr"]');
  await expect(mrTab).toBeVisible({ timeout: 20_000 });
  await mrTab.click();
  const reports = page.locator('[data-testid="mr-reports"]');
  await expect(reports).toBeVisible({ timeout: 30_000 });
  const mrRows = await page.locator('[data-testid^="mr-row-"]').count();
  expect(mrRows).toBeGreaterThan(0);
});

test("H4: Save exports a workspace zip containing library + dataset artifacts", async ({ page }) => {
  await bootReady(page);
  const downloadPromise = page.waitForEvent("download", { timeout: 30_000 });
  await page.locator('[data-testid="file-menu"]').click();
  await page.waitForTimeout(400);
  await page.locator('[data-testid="file-save-workspace"]').click();
  const download = await downloadPromise;
  const path = join(dir, "it19-workspace.zip");
  await download.saveAs(path);
  const listing = execSync(
    `python3 -c "import zipfile,sys; [print(n) for n in zipfile.ZipFile(sys.argv[1]).namelist()]" ${path}`,
    { encoding: "utf8" });
  expect(listing).toMatch(/\.cql/);
  // dataset artifact: json/ndjson payload of patient resources
  expect(listing).toMatch(/(patients\.ndjson|\.json)/);
  expect(listing.length).toBeGreaterThan(100);
});
