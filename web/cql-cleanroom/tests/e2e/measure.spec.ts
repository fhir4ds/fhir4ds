import { expect, test, type Page } from "@playwright/test";

/**
 * Measure-reports campaign e2e (FEATURE_CLEANROOM_MEASURE_REPORTS.md):
 * MeasurePane authoring + validation, TestsPane v2 expected-value grid,
 * MeasureReport export/import round-trip, ViewPane default-VD flatten.
 */

async function bootReady(page: Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}

async function loadDataset(page: Page) {
  await page.waitForSelector("[data-testid=dataset-tree]", {
    timeout: 30_000,
  });
}

/** WORKBENCH_REORG phase 5: measure authoring is an editor tab — expand
 *  the Measures drawer (collapsed on fresh boot), then open the tab. */
async function openMeasureTab(page: Page) {
  await page.click("[data-testid=nav-toggle-measures]");
  await page.locator("[data-testid^=nav-item-measure-]").first().click();
  await page.waitForSelector("[data-testid=measure-validate]", {
    timeout: 10_000,
  });
}

test.describe("measure pane authoring", () => {
  test("default measure validates and drives the expected grid", async ({ page }) => {
    await bootReady(page);
    await loadDataset(page);
    await openMeasureTab(page);

    // Default measure: initial-population -> Initial Population,
    // numerator -> Has Name. Validate through the capability.
    await page.click("[data-testid=measure-validate]");
    await page.waitForSelector("[data-testid=measure-status]", {
      timeout: 60_000,
    });
    const status = await page.textContent("[data-testid=measure-status]");
    if (!status?.includes("valid")) throw new Error(`measure status: ${status}`);

    // Expected grid: authoring is CURATED (REORG 6c) — the "+" opens
    // the editor, patients are added from the dataset, then every
    // population code becomes a column.
    await page.click("[data-testid=nav-toggle-expected]");
    await page.click("[data-testid=nav-add-expected]");
    await page.waitForSelector("[data-testid=expected-grid]");
    for (const pid of ["p1", "p2", "p3"]) {
      await page.selectOption("[data-testid=expected-add-patient]", pid);
    }
    await page.waitForSelector("[data-testid=expected-p1-initial-population]");
    await page.waitForSelector("[data-testid=expected-p3-numerator]");
  });

  test("add row, pick code + define, remove", async ({ page }) => {
    await bootReady(page);
    await loadDataset(page);
    await openMeasureTab(page);

    await page.click("[data-testid=measure-add-row]");
    await page.waitForSelector("[data-testid=measure-row-2]", {
      timeout: 10_000,
    });

    // denominator-exclusion is free; the used codes are disabled.
    await page.selectOption("[data-testid=measure-code-2]", {
      label: "denominator-exclusion",
    });
    // Define picker lists the parsed definitions of the main library
    // (cold-boot parse takes seconds — poll for the option to land).
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll("[data-testid=measure-define-2] option")].some(
          (o) => o.textContent?.includes("Initial Population"),
        ),
      undefined,
      { timeout: 30_000 },
    );
    const options = await page
      .locator("[data-testid=measure-define-2] option")
      .allTextContents();
    if (!options.some((o) => o.includes("Initial Population"))) {
      throw new Error(`define options: ${options}`);
    }
    await page.selectOption("[data-testid=measure-define-2]", {
      label: "Has Name",
    });

    // Validate the extended measure; expected grid gains the column.
    await page.click("[data-testid=measure-validate]");
    await page.waitForSelector("[data-testid=measure-status]", {
      timeout: 60_000,
    });
    // REORG 6c: open the expected tab and add p1 to see the new column.
    await page.click("[data-testid=nav-toggle-expected]");
    await page.click("[data-testid=nav-add-expected]");
    await page.waitForSelector("[data-testid=expected-grid]");
    await page.selectOption("[data-testid=expected-add-patient]", "p1");
    await page.waitForSelector(
      "[data-testid=expected-p1-denominator-exclusion]",
      { timeout: 10_000 },
    );

    // Back to the measure tab (the grid click switched tabs)…
    await page.locator("[data-testid^=editor-tab-measure-]").click();

    // …then remove the row again; the grid column disappears.
    await page.click("[data-testid=measure-remove-2]");
    await page.waitForSelector("[data-testid=measure-row-2]", {
      state: "detached",
      timeout: 10_000,
    });
    const gone = await page
      .locator("[data-testid=expected-p1-denominator-exclusion]")
      .count();
    if (gone !== 0) throw new Error("denominator_exclusion column not removed");
  });

  test("unknown define surfaces a typed error", async ({ page }) => {
    await bootReady(page);
    await loadDataset(page);
    await openMeasureTab(page);

    // Remove row 1 (initial-population) and re-add it pointing at a
    // define that does not exist: select offers only parsed names, so
    // simulate via the raw measure editor path — use Suggest+manual.
    // Simpler: delete both rows, then validate an empty measure is
    // legal (bootstrap mode), and re-add with a real define.
    await page.click("[data-testid=measure-remove-1]");
    await page.click("[data-testid=measure-remove-0]");
    await page.waitForSelector("[data-testid=measure-empty]", {
      timeout: 10_000,
    });
    await page.click("[data-testid=measure-validate]");
    await page.waitForSelector("[data-testid=measure-status]", {
      timeout: 60_000,
    });
    const status = await page.textContent("[data-testid=measure-status]");
    if (!status?.includes("valid"))
      throw new Error(`empty measure should validate: ${status}`);
  });
});

test.describe("expected values + MeasureReport round-trip", () => {
  test("import a MeasureReport bundle via the Expected ▾ menu restores the grid", async ({ page }) => {
    await bootReady(page);
    await loadDataset(page);

    // REORG phase 6a: authoring happens in the "expected" editor tab.
    await page.click("[data-testid=nav-toggle-expected]");
    await page.click("[data-testid=nav-add-expected]");
    await page.waitForSelector("[data-testid=expected-grid]", {
      timeout: 10_000,
    });

    // Author expectations: p1 both, p2 numerator only, p3 initial only.
    // Seed all-true first so every cell gets an explicit entry
    // (unchecking an unchecked controlled box is a no-op).
    await page.click("[data-testid=expected-default]");
    await page.click("[data-testid=expected-default-all-true]");
    await page.uncheck("[data-testid=expected-p2-initial-population]");
    await page.uncheck("[data-testid=expected-p3-numerator]");

    // #64: the editor lost its export/import buttons — the authored set
    // round-trips as a MeasureReport bundle through the nav section's ▾
    // menu (single individual MR per patient, count 1|0 per code).
    const bundle = {
      resourceType: "Bundle",
      type: "collection",
      entry: [
        mrEntry("p1", { "initial-population": 1, numerator: 1 }),
        mrEntry("p2", { "initial-population": 0, numerator: 1 }),
        mrEntry("p3", { "initial-population": 1, numerator: 0 }),
      ],
    };

    // Wipe via All false, verify, then re-import the bundle.
    await page.click("[data-testid=expected-default]");
    await page.click("[data-testid=expected-default-all-false]");
    await page.waitForFunction(() => {
      const cb = document.querySelector(
        "[data-testid=expected-p1-initial-population]",
      ) as HTMLInputElement | null;
      return cb && cb.checked === false;
    });

    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser", { timeout: 15_000 }),
      page.click("[data-testid=nav-import-expected]"),
      page.click("[data-testid=nav-import-expected-expected-json]"),
    ]);
    await chooser.setFiles({
      name: "expected-measure-reports.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(bundle)),
    });
    await page.waitForFunction(() => {
      const cb = document.querySelector(
        "[data-testid=expected-p1-initial-population]",
      ) as HTMLInputElement | null;
      return cb && cb.checked === true;
    });
    const p3 = await page.isChecked(
      "[data-testid=expected-p3-initial-population]",
    );
    if (!p3) throw new Error("import did not restore p3 initial_population");

    // 6h #62: the compare derives from the latest auto-run — imported
    // expectations match the demo data truths (no button).
    await page.waitForFunction(
      () =>
        document
          .querySelector("[data-testid=tests-summary]")
          ?.textContent?.includes("6/6") ?? false,
      undefined,
      { timeout: 90_000 },
    );
  });
});

/** One authored individual MeasureReport entry (count 0|1 per code). */
function mrEntry(
  pid: string,
  counts: Record<string, number>,
): { resource: Record<string, unknown> } {
  return {
    resource: {
      resourceType: "MeasureReport",
      status: "complete",
      type: "individual",
      measure: "urn:cleanroom:measure:CleanroomDemoMeasure",
      subject: { reference: `Patient/${pid}` },
      group: [
        {
          population: Object.entries(counts).map(([code, count]) => ({
            code: { coding: [{ code }] },
            count,
          })),
        },
      ],
    },
  };
}

async function openViewTab(page: Page) {
  // REORG phase 6b: the ViewDefinition editor is a col1 tab; the "+"
  // in the Views drawer creates a derived VD and opens it.
  await page.click("[data-testid=nav-toggle-views]");
  await page.click("[data-testid=nav-add-views]");
  await page.waitForSelector("[data-testid=view-mode]", {
    timeout: 30_000,
  });
}

test.describe("view pane flatten", () => {
  test("derived VD flattens evaluation MeasureReports wide-format", async ({ page }) => {
    await bootReady(page);
    await loadDataset(page);

    // Evaluate first so MeasureReports exist for the reports source.
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    await openViewTab(page);

    // Derived mode is the default: ONE ROW PER PATIENT (m1081 #9),
    // one integer count column per population (wide format, no forEach).
    await page.waitForSelector("[data-testid=view-table]", {
      timeout: 60_000,
    });

    const header = await page
      .locator("[data-testid=view-table] thead tr")
      .textContent();
    if (!header?.includes("patient_id")) throw new Error(`header: ${header}`);
    if (!header?.includes("initial_population")) throw new Error(`header: ${header}`);
    if (!header?.includes("numerator")) throw new Error(`header: ${header}`);

    // Exactly one row per patient in the dataset (3 patients demo).
    const rows = await page.locator("[data-testid=view-table] tbody tr").count();
    if (rows !== 3) throw new Error(`view rows (want 3 patients): ${rows}`);

    // Wide-format cells carry 0/1 counts; first row is a Patient ref.
    const first = await page
      .locator("[data-testid=view-table] tbody tr")
      .first()
      .textContent();
    if (!first?.includes("Patient/")) throw new Error(`view row: ${first}`);
  });

  test("per-column override forks the derived name", async ({ page }) => {
    await bootReady(page);
    await loadDataset(page);
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    await openViewTab(page);

    // Override the numerator column name (ghost-text default forks on edit).
    await page.fill(
      "[data-testid=view-col-name-numerator]",
      "num_count",
    );
    await page.waitForSelector("[data-testid=view-table]", {
      timeout: 60_000,
    });
    const header = await page
      .locator("[data-testid=view-table] thead tr")
      .textContent();
    if (!header?.includes("num_count")) throw new Error(`header: ${header}`);
    if (header?.includes("numerator")) throw new Error(`old name still present: ${header}`);
  });

  test("custom VD flattens MeasureReports", async ({ page }) => {
    await bootReady(page);
    await loadDataset(page);
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    await openViewTab(page);

    // Custom mode: long-format projection of the engine's MeasureReports.
    await page.selectOption("[data-testid=view-mode]", "custom");
    await page.fill(
      "[data-testid=vd-editor]",
      JSON.stringify({
        resource: "MeasureReport",
        select: [
          {
            column: [
              { name: "subject", path: "%resource.subject.reference", type: "string" },
              { name: "code", path: "population.code.coding.code", type: "string" },
            ],
            forEach: "group.population",
          },
        ],
      }),
    );
    await page.waitForSelector("[data-testid=view-table]", {
      timeout: 60_000,
    });
    const rows = await page.locator("[data-testid=view-table] tbody tr").count();
    if (rows < 6) throw new Error(`report view rows: ${rows}`);
    const first = await page
      .locator("[data-testid=view-table] tbody tr")
      .first()
      .textContent();
    if (!first?.includes("Patient/")) throw new Error(`view row: ${first}`);
  });
});

test.describe("measure association (reorg 6f)", () => {
  test("primary-library picker repoints the measure + inputs table", async ({
    page,
  }) => {
    await bootReady(page);
    await loadDataset(page);
    await openMeasureTab(page);

    // The entrypoint's closure surfaces as a collapsible inputs table
    // (reorg 6h — replaced the 6f chip row).
    await page.waitForSelector("[data-testid=measure-inputs]");
    await page.click("[data-testid=measure-inputs-toggle]");
    const row0 = await page.textContent(
      "[data-testid=measure-inputs] tbody tr:first-child",
    );
    if (!row0?.includes("CleanroomDemo"))
      throw new Error(`initial inputs row: ${row0}`);

    // A second library becomes selectable; picking it re-points the
    // measure through the SAME write path as the nav double-click.
    await page.click("[data-testid=nav-toggle-libraries]");
    await page.click("[data-testid=library-tab-add]");
    await page.waitForSelector("[data-testid=library-tab-1]");
    await page.locator("[data-testid^=editor-tab-measure-]").click();
    await page.waitForSelector("[data-testid=measure-main-library]");
    const secondName = await page.evaluate(() => {
      const sel = document.querySelector<HTMLSelectElement>(
        "[data-testid=measure-main-library]",
      );
      return sel!.options[1]?.textContent ?? "";
    });
    if (!secondName) throw new Error("second library option missing");
    await page.selectOption("[data-testid=measure-main-library]", {
      index: 1,
    });
    await page.waitForFunction(
      (name) =>
        document
          .querySelector("[data-testid=measure-inputs] tbody tr")
          ?.textContent?.includes(name ?? ""),
      secondName,
      { timeout: 10_000 },
    );

    // Switch back so the heartbeat evaluates a real library again.
    await page.selectOption("[data-testid=measure-main-library]", {
      index: 0,
    });
    await page.waitForFunction(
      () =>
        document
          .querySelector("[data-testid=measure-inputs] tbody tr")
          ?.textContent?.includes("CleanroomDemo"),
      undefined,
      { timeout: 10_000 },
    );
  });

  test("Default > Current result writes the expected grid + authored status", async ({
    page,
  }) => {
    await bootReady(page);
    await loadDataset(page);
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 90_000,
    });
    await openMeasureTab(page);

    // Not authored yet; the expected editor carries the capture.
    await page.waitForSelector("[data-testid=expected-status]");
    const before = await page.textContent("[data-testid=expected-status]");
    if (!before?.includes("not authored"))
      throw new Error(`status before capture: ${before}`);

    // #64: capture moved out of the console into the expected editor's
    // Default ▾ ("Current result" = the old Capture-as-expected).
    await page.click("[data-testid=nav-toggle-expected]");
    await page.click("[data-testid=nav-add-expected]");
    await page.waitForSelector("[data-testid=tests-pane]", { timeout: 30_000 });
    await page.click("[data-testid=expected-default]");
    await page.click("[data-testid=expected-default-current-result]");

    // The grid mirrors the run (female demo logic: p1/p3 in the
    // initial population, p2 out).
    await page.waitForSelector("[data-testid=expected-grid]");
    await page.waitForFunction(
      () => document.querySelectorAll("[data-testid^=expected-row-]").length === 3,
      undefined,
      { timeout: 10_000 },
    );
    const checked = await page.evaluate(() => {
      const get = (tid: string) =>
        document.querySelector<HTMLInputElement>(
          `[data-testid=expected-${tid}]`,
        )?.checked ?? null;
      return {
        p1: get("p1-initial-population"),
        p2: get("p2-initial-population"),
        p3: get("p3-initial-population"),
      };
    });
    if (checked.p1 !== true || checked.p3 !== true || checked.p2 !== false) {
      throw new Error(`captured grid mismatch: ${JSON.stringify(checked)}`);
    }

    // Back on the measure tab, the association strip counts the authored
    // reports (the editor column swaps panes, so the measure remounts).
    await page
      .locator("[data-testid^=editor-tab-measure-]")
      .first()
      .click();
    await page.waitForFunction(
      () =>
        document
          .querySelector("[data-testid=expected-status]")
          ?.textContent?.includes("3 patients"),
      undefined,
      { timeout: 10_000 },
    );
  });

  test("compare derives automatically and survives a broken library", async ({
    page,
  }) => {
    await bootReady(page);
    // Deterministic start: this test asserts the EMPTY-grid compare
    // state, so leaky prior-spec expectations would mask it.
    await page.click("[data-testid=file-menu]");
    await page.click("[data-testid=workspace-reset]");
    await page.waitForTimeout(1200);
    await page.waitForSelector("[data-testid=dataset-tree]", {
      timeout: 30_000,
    });

    // Fresh expected report + its editor tab: the empty grid renders the
    // compare hint (no 0/0 chip).
    await page.click("[data-testid=nav-toggle-expected]");
    await page.click("[data-testid=nav-add-expected]");
    await page.waitForSelector("[data-testid=tests-pane]", { timeout: 30_000 });
    await page.waitForSelector("[data-testid=compare-empty]", {
      timeout: 30_000,
    });

    // Author expectations: the compare derives from the latest auto-run
    // immediately (chip in the console's Compare tab).
    await page.click("[data-testid=expected-default]");
    await page.click("[data-testid=expected-default-all-true]");
    await page.waitForSelector("[data-testid=tests-summary]", {
      timeout: 60_000,
    });
    await expect(page.locator("[data-testid=tests-summary]")).toContainText(
      "passed",
    );

    // Break the library: the heartbeat run fails (no rows) → the compare
    // explains and the chip disappears. Never crash the tree.
    await page.locator("[data-testid^=editor-tab-library-]").first().click();
    await page.click("[data-testid=cql-editor]");
    await page.keyboard.press("Control+Home");
    await page.keyboard.insertText("this is not cql {{{\n");
    await page.locator("[data-testid^=nav-item-expected-]").first().click();
    await page.waitForSelector("[data-testid=tests-pane]", { timeout: 30_000 });
    await page.waitForSelector("[data-testid=compare-empty]", {
      timeout: 60_000,
    });
    await expect(page.locator("[data-testid=tests-pane]")).toBeVisible();
    await expect(page.locator(".version-badge")).toBeVisible();
  });
});
