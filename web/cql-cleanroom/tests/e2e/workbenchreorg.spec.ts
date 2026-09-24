import { test, type Page } from "@playwright/test";

/**
 * Workbench-reorg e2e (FEATURE_CLEANROOM_WORKBENCH_REORG.md):
 * Results tabs + empty states, run history (save/compare/drift/rename/
 * delete), dataset tree scale (type groups + show-more + filter),
 * AST filter.
 */

async function bootReady(page: Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
}

async function resetWorkspace(page: Page) {
  await page.click("[data-testid=workspace-reset]");
  await page.waitForTimeout(800);
}


async function setMaleLibrary(page: import("@playwright/test").Page) {
  // Monaco doesn't honor fill() on its textarea — focus, select all, type.
  await page.click("[data-testid=cql-editor]");
  await page.keyboard.press("Control+Home");
  await page.keyboard.press("Control+Shift+End");
  await page.keyboard.insertText('library CleanroomDemo version \'1.0.0\'\nusing FHIR version \'4.0.1\'\ninclude FHIRHelpers version \'4.0.1\' called FHIRHelpers\n\ndefine "Initial Population":\n  exists([Patient] P where P.gender = \'male\')\n\ndefine "Has Name":\n  exists([Patient] P where P.name.first().given.first() is not null)\n');
  // Debounced parse
  await page.waitForTimeout(1200);
}

test.describe("results tabs", () => {
  test("three tabs navigate; empty states before first run", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // All three tabs render.
    await page.waitForSelector("[data-testid=results-tab-cql]");
    await page.waitForSelector("[data-testid=results-tab-measure]");
    await page.waitForSelector("[data-testid=results-tab-view]");

    // Before any evaluation: CQL tab has no table, MR tab shows its
    // hint, View tab shows no-reports.
    const cqlTable = await page
      .locator("[data-testid=results-table]")
      .count();
    if (cqlTable !== 0) throw new Error("results table before eval");

    await page.click("[data-testid=results-tab-measure]");
    await page.waitForSelector("[data-testid=measure-pane]");
    const mrEmpty = await page
      .locator("[data-testid=mr-empty]")
      .count();
    if (mrEmpty !== 1) throw new Error("mr-empty missing before eval");

    await page.click("[data-testid=results-tab-view]");
    await page.waitForSelector("[data-testid=view-no-reports]");

    // Tab pref persists across reload (rides workspace.json).
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.waitForSelector("[data-testid=view-no-reports]", {
      timeout: 30_000,
    });

    // Return to the CQL tab so the persisted tab pref does not bleed
    // into later specs (autosave may outlive the reset below).
    await page.click("[data-testid=results-tab-cql]");
    await page.waitForTimeout(1000);
    await resetWorkspace(page);
  });

  test("evaluate populates all three tabs without re-execution", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=load-dataset]");
    await page.waitForSelector("[data-testid=dataset-loaded]");

    await page.click("[data-testid=run-eval]");
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });

    // MR tab: report rows render (3 patients x 2 populations).
    await page.click("[data-testid=results-tab-measure]");
    await page.waitForSelector("[data-testid=mr-table]", {
      timeout: 30_000,
    });
    // MR pivot (m1081 #8): one row PER PATIENT, one column per
    // population — 3 patients in the demo dataset.
    const mrRows = await page.locator("[data-testid=mr-table] tbody tr").count();
    if (mrRows !== 3) throw new Error(`mr rows (want 3 patients): ${mrRows}`);

    // Sankey renders in the MR tab after evaluation.
    await page.waitForSelector("[data-testid=population-sankey]", {
      timeout: 30_000,
    });

    // View tab: derived run over the saved reports.
    await page.click("[data-testid=results-tab-view]");
    await page.click("[data-testid=view-run]");
    await page.waitForSelector("[data-testid=view-table]", {
      timeout: 60_000,
    });

    await resetWorkspace(page);
  });
});

test.describe("run history", () => {
  test("runs accumulate; compare shows delta; rename + delete work", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.click("[data-testid=load-dataset]");
    await page.waitForSelector("[data-testid=dataset-loaded]");

    // Two evaluations -> two saved runs.
    await page.click("[data-testid=run-eval]");
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    // The Evidence drawer (<details>) starts OPEN (attr renders as
    // "" — falsy string but present). Check the DOM prop instead.
    const evOpen = await page.evaluate(
      () =>
        (document.querySelector(
          "[data-testid=drawer-evidence] details",
        ) as HTMLDetailsElement | null)?.open ?? false,
    );
    if (!evOpen) {
      await page.click("[data-testid=drawer-evidence-toggle]");
    }
    await page.waitForFunction(
      () =>
        document.querySelectorAll(
          '[data-testid=compare-select] option[value]:not([value=""])',
        ).length >= 1,
      undefined,
      { timeout: 30_000 },
    );

    // Change logic (female -> male) and evaluate again.
    await setMaleLibrary(page);
    await page.click("[data-testid=run-eval]");
    // The results-table never detaches between runs — wait for the
    // run HISTORY to grow instead (append is async post-evaluate).
    await page.waitForFunction(
      () =>
        document.querySelectorAll(
          '[data-testid=compare-select] option[value]:not([value=""])',
        ).length >= 2,
      undefined,
      { timeout: 60_000 },
    );

    const optionCount = await page
      .locator('[data-testid=compare-select] option[value]:not([value=""])')
      .count();
    if (optionCount < 2) throw new Error(`runs saved: ${optionCount}`);

    // Compare vs the first run: library changed -> drift warning + moved rows.
    // Runs list is newest-first; the FEMALE baseline is the LAST option.
    const runCount = await page
      .locator('[data-testid=compare-select] option')
      .count();
    await page.selectOption("[data-testid=compare-select]", {
      index: runCount - 1,
    });
    await page.waitForSelector("[data-testid=compare-drift]", {
      timeout: 10_000,
    });
    await page.click("[data-testid=compare-run]");
    await page.waitForSelector("[data-testid=compare-delta]", {
      timeout: 30_000,
    });
    const rows = await page
      .locator("[data-testid=compare-row]")
      .allTextContents();
    const moved = rows.filter(
      (r) => r.includes("initial_population") && r.includes("moved"),
    );
    if (moved.length === 0) throw new Error(`no moved rows: ${JSON.stringify(rows)}`);

    // Rename the currently selected (oldest) run via the prompt dialog.
    page.once("dialog", (d) => void d.accept("baseline-female"));
    await page.click("[data-testid=run-rename]");
    await page.waitForTimeout(300);
    const optionEls = await page
      .locator('[data-testid=compare-select] option')
      .allTextContents();
    if (!optionEls.some((t) => t.includes("baseline-female")))
      throw new Error(`rename failed: ${JSON.stringify(optionEls)}`);

    // Delete the renamed run: option count drops by one.
    page.once("dialog", (d) => void d.accept());
    await page.click("[data-testid=run-delete]");
    await page.waitForTimeout(300);
    const after = await page
      .locator("[data-testid=compare-select] option")
      .count();
    if (after !== optionCount + 1 - 1) throw new Error(`delete: ${after}`);

    await resetWorkspace(page);
  });
});

test.describe("dataset tree scale", () => {
  test("60 observations group by type with cap + show-more + filter", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // Build a big dataset through the raw NDJSON view.
    const lines: string[] = [
      JSON.stringify({ resourceType: "Patient", id: "big", gender: "female", name: [{ given: ["Bee"] }] }),
    ];
    for (let i = 0; i < 60; i++) {
      lines.push(
        JSON.stringify({
          resourceType: "Observation",
          id: `obs-${i}`,
          status: "final",
          code: { text: "o" },
          subject: { reference: "Patient/big" },
        }),
      );
    }
    await page.click("[data-testid=dataset-view-raw]");
    await page.fill("[data-testid=dataset-editor]", lines.join("\n"));
    await page.click("[data-testid=load-dataset]");
    await page.waitForSelector("[data-testid=dataset-loaded]");
    await page.click("[data-testid=dataset-view-tree]");

    // Type group for Observation exists with a count.
    await page.waitForSelector(
      "[data-testid=dataset-type-big-Observation]",
      { timeout: 10_000 },
    );
    const label = await page.textContent(
      "[data-testid=dataset-type-toggle-big-Observation]",
    );
    if (!label?.includes("(60)")) throw new Error(`type label: ${label}`);

    // >3 rows -> group starts collapsed (OQ-1).
    const rowsVisible = await page
      .locator("[data-testid=dataset-row-5]")
      .count();
    if (rowsVisible !== 0) throw new Error("rows visible while collapsed");

    // Expand: 25-row cap + show-more.
    await page.click("[data-testid=dataset-type-toggle-big-Observation]");
    const capped = await page.locator("[data-testid^=dataset-row-]").count();
    if (capped > 26) throw new Error(`cap exceeded: ${capped}`);
    await page.waitForSelector("[data-testid=dataset-more-big-Observation]");
    await page.click("[data-testid=dataset-more-big-Observation]");
    await page.waitForTimeout(200);
    const expanded = await page.locator("[data-testid^=dataset-row-]").count();
    if (expanded < 60) throw new Error(`show-more: ${expanded}`);

    // Filter bypasses cap + auto-expands.
    await page.fill("[data-testid=dataset-filter]", "obs-58");
    await page.waitForTimeout(300);
    const filtered = await page
      .locator("[data-testid^=dataset-row-]")
      .count();
    if (filtered < 1) throw new Error("filter found nothing");

    await resetWorkspace(page);
  });
});

test.describe("ast filter", () => {
  test("filter narrows statement trees by define name", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    await page.click("[data-testid=run-eval]");
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    await page.click("[data-testid=show-ast]");
    await page.click("[data-testid=ast-load]");
    await page.waitForSelector("[data-testid^=ast-def-]", {
      timeout: 30_000,
    });
    const all = await page
      .locator("[data-testid^=ast-def-]")
      .count();
    if (all < 2) throw new Error(`defs: ${all}`);

    await page.fill("[data-testid=ast-filter]", "name");
    await page.waitForTimeout(200);
    const one = await page
      .locator("[data-testid^=ast-def-]")
      .count();
    if (one !== 1) throw new Error(`filtered defs: ${one}`);

    await resetWorkspace(page);
  });
});
