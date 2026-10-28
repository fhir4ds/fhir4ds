import { test, type Page } from "@playwright/test";
import { waitDatasetResources } from "./dataset";
import { bootTextReady } from "./bootText";

async function bootReady(page: Page) {
  // S25: fresh boots auto-load cms125 and auto-cellify — legacy specs
  // contract on the text editor + the DEFAULT demo state, so boot to
  // text, then reset to the scratch demo (3 resources).
  await bootTextReady(page);
  await page.click("[data-testid=file-menu]");
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(800);
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
  // The Tests drawer hosts the dataset tree (default rail: Libraries).
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.waitForSelector("[data-testid=dataset-tree]", { timeout: 30_000 });
}

test("editor parses and evaluates with typed results", async ({ page }) => {
  await bootReady(page);
  // Deterministic start: prior specs' auto-commits persist (same origin).
  await page.click("[data-testid=file-menu]");
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(600);

  // Default library parses clean (debounced parse_cql)
  await page.waitForFunction(
    () =>
      document
        .querySelector("[data-testid=parse-status]")
        ?.textContent?.includes("parsed"),
    undefined,
    { timeout: 30_000 },
  );

  // Dataset: the demo 3-resource workspace.
  await page.waitForSelector("[data-testid=dataset-tree]");
  await waitDatasetResources(page, 3);

  // Evaluate → typed results table + SQL viewer
  await page.waitForSelector("[data-testid=results-table]", {
    timeout: 60_000,
  });
  // S26: run columns use the measure's DISPLAY names ("Initial
  // Population"), not the DQM underscore convention.
  const badge = await page.textContent("[data-testid=\"type-badge-Initial Population\"]");
  if (badge !== "Boolean") throw new Error(`IPP badge: ${badge}`);
  const meta = await page.textContent("[data-testid=results-table-stats]");
  if (!meta?.includes("3 rows")) throw new Error(`meta: ${meta}`);
  // WORKBENCH_REORG phase 5: SQL is a console sub-tab now.
  await page.click("[data-testid=console-tab-sql]");
  await page.waitForSelector("[data-testid=sql-viewer]", { timeout: 10_000 });
  const sql = await page.textContent(".sql-pre");
  if (!sql || !sql.includes("ORDER BY")) throw new Error("sql viewer empty");
  // Leave the console on Results for later assertions/specs.
  await page.click("[data-testid=console-tab-results]");
  await page.waitForSelector("[data-testid=results-table]");
});

test("tests run against the loaded dataset", async ({ page }) => {
  await bootReady(page);
  // Deterministic start: clear any workspace persisted by prior specs
  // (IndexedDB survives browser-context isolation — same origin).
  await page.click("[data-testid=file-menu]");
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(600);
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.waitForSelector("[data-testid=dataset-tree]");

  // REORG phase 6a: the expected grid is the "expected" editor tab —
  // "+" on the Expected Results drawer seeds a skeleton and opens it.
  await page.click("[data-testid=nav-toggle-expected]");
  await page.click("[data-testid=nav-add-expected]");
  await page.waitForSelector("[data-testid=expected-grid]", {
    timeout: 30_000,
  });

  // Author explicit expectations for every cell: seed all-true, then
  // uncheck the false cells (unchecking an unchecked controlled box is
  // a no-op, so seed first to guarantee every cell has an entry).
  await page.click("[data-testid=expected-default]");
  await page.click("[data-testid=expected-default-all-true]");
  // p1 female+name (both), p2 male+name (numerator only),
  // p3 female+no-name (initial_population only).
  await page.uncheck("[data-testid=expected-p2-initial-population]");
  await page.uncheck("[data-testid=expected-p3-numerator]");

  // 6h #62: the compare derives from the latest auto-run — no button.
  // 6 cases (3 patients × 2 populations), all matching.
  await page.waitForFunction(
    () =>
      document
        .querySelector("[data-testid=tests-summary]")
        ?.textContent?.includes("6/6") ?? false,
    undefined,
    { timeout: 90_000 },
  );
});

test("broken library surfaces diagnostics", async ({ page }) => {
  await bootReady(page);
  // Type an incomplete expression into Monaco via keyboard
  const editor = page.locator("[data-testid=cql-editor]");
  await editor.click();
  // Move to end of document and append a broken define
  await page.keyboard.press("Control+End");
  await page.keyboard.type('\ndefine "Broken":\n  1 +');
  await page.waitForSelector("[data-testid=diag-row]", { timeout: 30_000 });
  const status = await page.textContent("[data-testid=parse-status]");
  if (!status?.includes("diagnostic")) throw new Error(`status: ${status}`);
});
