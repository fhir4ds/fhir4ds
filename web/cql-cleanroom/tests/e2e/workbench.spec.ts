import { test, type Page } from "@playwright/test";

async function bootReady(page: Page) {
  await page.goto("/");
  // Wait for FULL engine boot (pyodide + duckdb-wasm): the version badge
  // only renders on the boot-ok message. Clicking into a still-booting
  // worker (runPython during in-flight runPythonAsync) crashes natively.
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}

test("editor parses and evaluates with typed results", async ({ page }) => {
  await bootReady(page);

  // Default library parses clean (debounced parse_cql)
  await page.waitForFunction(
    () =>
      document
        .querySelector("[data-testid=parse-status]")
        ?.textContent?.includes("parsed"),
    undefined,
    { timeout: 30_000 },
  );

  // Dataset: default NDJSON prefilled → Use dataset
  await page.click("[data-testid=load-dataset]");
  await page.waitForSelector("[data-testid=dataset-loaded]");
  const loaded = await page.textContent("[data-testid=dataset-loaded]");
  if (!loaded?.includes("3")) throw new Error(`expected 3 resources: ${loaded}`);

  // Evaluate → typed results table + SQL viewer
  await page.click("[data-testid=run-eval]");
  await page.waitForSelector("[data-testid=results-table]", {
    timeout: 60_000,
  });
  const badge = await page.textContent("[data-testid=type-badge-initial_population]");
  if (badge !== "Boolean") throw new Error(`IPP badge: ${badge}`);
  const meta = await page.textContent("[data-testid=eval-meta]");
  if (!meta?.includes("3 patients")) throw new Error(`meta: ${meta}`);
  await page.click("[data-testid=show-sql]");
  const sql = await page.textContent(".sql-pre");
  if (!sql || !sql.includes("ORDER BY")) throw new Error("sql viewer empty");
});

test("tests run against the loaded dataset", async ({ page }) => {
  await bootReady(page);
  // Deterministic start: clear any workspace persisted by prior specs
  // (IndexedDB survives browser-context isolation — same origin).
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(600);
  await page.click("[data-testid=load-dataset]");
  await page.waitForSelector("[data-testid=dataset-loaded]");

  // Tests live in the MeasureReport tab now.
  await page.click("[data-testid=results-tab-measure]");
  const drawer = page.locator("[data-testid=drawer-populations]");
  if ((await drawer.count()) > 0 && !(await drawer.isVisible())) {
    await page.click("[data-testid=drawer-populations-toggle]");
  }

  // Expected-value grid renders (Measure-backed, TestsPane v2)
  await page.waitForSelector("[data-testid=expected-grid]", {
    timeout: 30_000,
  });

  // Author explicit expectations for every cell: seed all-true, then
  // uncheck the false cells (unchecking an unchecked controlled box is
  // a no-op, so seed first to guarantee every cell has an entry).
  await page.click("[data-testid=tests-set-all-true]");
  // p1 female+name (both), p2 male+name (numerator only),
  // p3 female+no-name (initial_population only).
  await page.uncheck("[data-testid=expected-p2-initial-population]");
  await page.uncheck("[data-testid=expected-p3-numerator]");

  await page.click("[data-testid=run-tests]");
  await page.waitForSelector("[data-testid=tests-summary]", {
    timeout: 90_000,
  });
  // 6 cases (3 patients × 2 populations), all matching.
  const counts = await page.textContent("[data-testid=tests-summary]");
  if (!counts?.includes("6/6")) throw new Error(`counts: ${counts}`);
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
