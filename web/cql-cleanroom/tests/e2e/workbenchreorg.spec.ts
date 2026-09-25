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
    // Prior SPEC FILES may have left resultsTab=view persisted; go to
    // the CQL tab BEFORE resetting so the first results wait targets a
    // visible panel.
    await page.click("[data-testid=results-tab-cql]");
    await resetWorkspace(page);

    // All three tabs render.
    await page.waitForSelector("[data-testid=results-tab-cql]");
    await page.waitForSelector("[data-testid=results-tab-measure]");
    await page.waitForSelector("[data-testid=results-tab-view]");

    // U5: default dataset AUTO-EVALUATES — the CQL tab populates with
    // no clicks. Reload post-reset so the workspace rehydrates
    // deterministically (a prior test's tab pref can bleed), then go
    // to the CQL tab explicitly.
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    // Wait out the async workspace hydration (IndexedDB restore can
    // land AFTER this point and re-apply a stale tab pref over the
    // click below — the classic restore race).
    await page.waitForFunction(
      () =>
        document.querySelectorAll("[data-testid=library-tab-0]").length > 0,
      undefined,
      { timeout: 30_000 },
    );
    await page.waitForTimeout(600);
    // Self-healing tab click: hydration can land after the first click
    // and re-apply a stale pref; poll-and-reclick until the CQL panel
    // is actually visible (or give up with diagnostics).
    let visible = false;
    for (let attempt = 0; attempt < 12 && !visible; attempt++) {
      await page.click("[data-testid=results-tab-cql]");
      try {
        await page.waitForSelector("[data-testid=results-table]", {
          timeout: 10_000,
        });
        visible = true;
      } catch {
        const state = await page.evaluate(() => ({
          tab: document
            .querySelector('[data-testid=tab-panel-cql]')
            ?.getAttribute("hidden"),
          active: [
            ...document.querySelectorAll(".results-tabs .tab"),
          ].findIndex((b) => b.className.includes("active")),
        }));
        console.log(`TAB_RETRY ${attempt}:`, JSON.stringify(state));
      }
    }
    if (!visible) throw new Error("CQL tab never became visible after 12 clicks");

    await page.click("[data-testid=results-tab-measure]");
    await page.waitForSelector("[data-testid=measure-pane]");
    // View tab still gates on MeasureReports (needs the measure
    // materialization cycle) — may show the no-reports hint briefly.
    await page.click("[data-testid=results-tab-view]");

    // Tab pref persists across reload (rides workspace.json): the VIEW
    // tab we just selected restores — assert the VIEW output renders
    // (not the CQL table, which is hidden on the view tab!).
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.waitForSelector(
      "[data-testid=tab-panel-view]:not([hidden])",
      { timeout: 90_000 },
    );

    // Return to the CQL tab so the persisted tab pref does not bleed
    // into later specs (autosave may outlive the reset below).
    await page.click("[data-testid=results-tab-cql]");
    await page.waitForTimeout(1000);
    await resetWorkspace(page);
  });

  test("evaluate populates all three tabs without re-execution", async ({ page }) => {
    await bootReady(page);
    await resetWorkspace(page);
    await page.waitForSelector("[data-testid=dataset-loaded]");
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
    await page.waitForSelector("[data-testid=view-table]", {
      timeout: 60_000,
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
