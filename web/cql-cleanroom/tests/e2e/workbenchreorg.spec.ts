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

test.describe("console sub-tabs + col2 panes", () => {
  test("sub-tabs follow the active editor; placement + pref persist", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);

    // Library context: the four run-pipeline sub-tabs; the default
    // dataset AUTO-EVALUATES so Results populates with no clicks.
    await page.waitForSelector("[data-testid=console-tab-results]");
    await page.waitForSelector("[data-testid=console-tab-sql]");
    await page.waitForSelector("[data-testid=console-tab-ast]");
    await page.waitForSelector("[data-testid=console-tab-diags]");
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });

    // REORG phase 6b: dock the console right — col2 becomes the console.
    await page.click("[data-testid=console-place]");
    await page.waitForSelector(".app-main.dock-right");
    await page.waitForSelector("[data-testid=results-console]");

    // Placement + sub-tab pref persist across reload (workspace.json).
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.waitForSelector(".app-main.dock-right", { timeout: 90_000 });
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 90_000,
    });

    // Measure editor active → the console shows the Measure Report
    // output (pivot + attrition Sankey), no run-pipeline tabs.
    await page.click("[data-testid=nav-toggle-measures]");
    await page.locator("[data-testid^=nav-item-measure-]").first().click();
    await page.waitForSelector("[data-testid=console-tab-mr]");
    await page.waitForSelector(
      "[data-testid=console-panel-mr]:not([hidden])",
      { timeout: 30_000 },
    );
    await page.waitForSelector("[data-testid=mr-table]", { timeout: 30_000 });
    await page.waitForSelector("[data-testid=population-sankey]", {
      timeout: 30_000,
    });

    // View editor active → the console shows the flatten output.
    await page.click("[data-testid=nav-toggle-views]");
    await page.click("[data-testid=nav-add-views]");
    await page.waitForSelector("[data-testid=console-tab-view]");
    await page.waitForSelector("[data-testid=view-table]", {
      timeout: 60_000,
    });

    // Back to bottom-dock + library tab + Results so nothing bleeds
    // into later specs (autosave may outlive the reset below).
    await page.click("[data-testid=console-place]");
    await page.locator("[data-testid^=editor-tab-library-]").first().click();
    await page.click("[data-testid=console-tab-results]");
    await page.waitForSelector(".app-main.dock-bottom");
    await page.waitForSelector("[data-testid=results-table]");
    await resetWorkspace(page);
  });

  test("measure editor surfaces the report output in the console", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.waitForSelector("[data-testid=dataset-loaded]");
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });

    // MR pivot (m1081 #8): one row PER PATIENT, one column per
    // population — 3 patients in the demo dataset.
    await page.click("[data-testid=nav-toggle-measures]");
    await page.locator("[data-testid^=nav-item-measure-]").first().click();
    await page.waitForSelector("[data-testid=mr-table]", {
      timeout: 30_000,
    });
    const mrRows = await page.locator("[data-testid=mr-table] tbody tr").count();
    if (mrRows !== 3) throw new Error(`mr rows (want 3 patients): ${mrRows}`);

    // Sankey renders after evaluation.
    await page.waitForSelector("[data-testid=population-sankey]", {
      timeout: 30_000,
    });

    await resetWorkspace(page);
  });
});

test.describe("run history", () => {
  test("runs accumulate; diff highlights appear vs prior run", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.waitForFunction(() => Boolean((window as any).__cleanroom));

    await page.waitForSelector("[data-testid=dataset-loaded]");

    // First evaluation (auto): female logic, p1 IPP true.
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    await page.waitForFunction(
      () =>
        (document.querySelector(
          "[data-testid=results-table] tbody tr td:nth-child(2)",
        )?.textContent ?? "").includes("true"),
      undefined,
      { timeout: 90_000 },
    );

    // Change logic (female -> male): auto re-run; diff cells appear.
    await setMaleLibrary(page);
    await page.waitForSelector("td.diff-down-cell", { timeout: 90_000 });
    const changed = await page
      .locator("td.diff-up-cell, td.diff-down-cell")
      .count();
    if (changed < 2) throw new Error(`changed cells: ${changed}`);

    // Footer chips summarize the delta.
    const chip = await page.textContent("[data-testid=diff-chip-changed]");
    if (!chip?.includes("changed")) throw new Error(`chip: ${chip}`);

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
    // Raw auto-commit: wait for all 61 resources to land (~2s debounce).
    await page.waitForFunction(
      () =>
        document
          .querySelector("[data-testid=dataset-loaded]")
          ?.textContent?.includes("61 resources"),
      undefined,
      { timeout: 30_000 },
    );
    await page.click("[data-testid=dataset-view-tree]");

    // Type group for Observation exists with a count.
    await page.waitForSelector(
      "[data-testid=dataset-type-big-Observation]",
      { timeout: 10_000 },
    );
    const label = await page.textContent(
      "[data-testid=dataset-type-toggle-big-Observation]",
    );
    // Restyled toggle: caret span + name + count PILL (e.g. "Observation"
    // text + "60" pill) — the count is no longer parenthesized text.
    if (!label?.includes("Observation")) throw new Error(`type label: ${label}`);
    const pill = await page.textContent(
      `[data-testid=dataset-type-toggle-big-Observation] .dataset-count-pill`,
    );
    if (pill !== "60") throw new Error(`count pill: ${pill}`);

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
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    // WORKBENCH_REORG phase 5: AST is a console sub-tab now.
    await page.click("[data-testid=console-tab-ast]");
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
