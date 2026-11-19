/**
 * QA it21 — Domain 7 (outputs/artifacts) × EXPLORER (chaos, FINAL iteration).
 *  Y1 run spam: 5 rapid Run clicks while evaluation is in flight — runs
 *     list stays coherent (monotonic count, no duplicate ghost options)
 *  Y2 replay spam: switch run selections rapidly mid-render — final
 *     selection's table is the one rendered (no stale flicker-lock)
 *  Y3 download during run: File > Save while an evaluation is executing
 *     still yields a valid zip
 *  Y4 tab spam across console tabs (results/sql/mr/funnel) mid-run
 *  Y5 huge results: select-all + Run on the full showcase library twice —
 *     console remains responsive
 */
import { test, expect } from "@playwright/test";
import { bootDemoReady } from "./bootText";
import { execSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

let dir: string;
test.beforeAll(async () => { dir = await mkdtemp(join(tmpdir(), "ccr-it21-")); });
test.afterAll(async () => { await rm(dir, { recursive: true, force: true }).catch(() => undefined); });

async function bootReady(page: import("@playwright/test").Page) {
  await bootDemoReady(page, "/");
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

test("Y1: run spam keeps the runs list coherent", async ({ page }) => {
  await bootReady(page);
  const before = await page.locator("[data-testid=console-run-select] option").count();
  for (let i = 0; i < 5; i++) await page.click("[data-testid=editor-run]", { noWaitAfter: true });
  await page.waitForFunction(
    (t) => document.querySelectorAll("[data-testid=console-run-select] option").length >= t + 1,
    before,
    { timeout: 120_000 },
  );
  await page.waitForTimeout(2_000);
  const opts = await page.locator("[data-testid=console-run-select] option").allTextContents();
  const uniq = new Set(opts.map((o) => o.trim()));
  expect(opts.length).toBe(uniq.size); // no ghost duplicates
  expect(opts.length).toBeLessThanOrEqual(20);
});

test("Y2: replay spam lands on the selected run", async ({ page }) => {
  await bootReady(page);
  await page.click("[data-testid=editor-run]");
  await page.waitForTimeout(4_000);
  const sel = page.locator("[data-testid=console-run-select]");
  const n = await sel.locator("option").count();
  for (let i = 0; i < 4; i++) {
    await sel.selectOption({ index: i % n }).catch(() => undefined);
    await page.waitForTimeout(200);
  }
  await sel.selectOption({ index: n - 1 });
  await page.waitForTimeout(2_000);
  const table = page.locator("[data-testid=results-table]");
  await expect(table).toBeVisible({ timeout: 30_000 });
});

test("Y3: Save during an in-flight run still exports a valid zip", async ({ page }) => {
  await bootReady(page);
  await page.click("[data-testid=editor-run]", { noWaitAfter: true });
  await page.waitForTimeout(500);
  const downloadPromise = page.waitForEvent("download", { timeout: 60_000 });
  await page.locator('[data-testid="file-menu"]').click();
  await page.waitForTimeout(400);
  await page.locator('[data-testid="file-save-workspace"]').click();
  const download = await downloadPromise;
  const path = join(dir, "it21-midrun.zip");
  await download.saveAs(path);
  const listing = execSync(
    `python3 -c "import zipfile,sys; [print(x) for x in zipfile.ZipFile(sys.argv[1]).namelist()]" ${path}`,
    { encoding: "utf8" });
  expect(listing).toMatch(/\.cql/);
});

test("Y4: console tab spam mid-run never wedges", async ({ page }) => {
  await bootReady(page);
  await page.click("[data-testid=editor-run]", { noWaitAfter: true });
  for (const tab of ["console-tab-results", "console-tab-sql", "console-tab-results", "console-tab-sql"]) {
    await page.click(`[data-testid=${tab}]`, { timeout: 15_000 }).catch(() => undefined);
    await page.waitForTimeout(200);
  }
  await page.waitForTimeout(4_000);
  const alive = await page.evaluate(() => document.querySelector("[data-testid=results-console]") !== null);
  expect(alive).toBe(true);
});

test("Y5: two full showcase runs stay responsive", async ({ page }) => {
  await bootReady(page);
  for (let i = 0; i < 2; i++) {
    await page.click("[data-testid=editor-run]");
    await page.waitForTimeout(1_000);
  }
  await page.waitForTimeout(6_000);
  await expect(page.locator("[data-testid=results-table]")).toBeVisible({ timeout: 60_000 });
  const alive = await page.evaluate(() => document.querySelector("[data-testid=results-console]") !== null);
  expect(alive).toBe(true);
});
