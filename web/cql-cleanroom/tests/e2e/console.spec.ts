import { expect, test } from "@playwright/test";

/**
 * REORG 6g: the console is run-centric. Runs are triggered from the
 * LIBRARY EDITOR (Run button = selection when one exists, else the
 * whole library; Ctrl/Cmd+Enter same). Every run (auto heartbeat +
 * manual) lands in a 20-entry ring; the console's Results/SQL/AST/CQL
 * tabs render from the SELECTED run's replay payload, and a manual run
 * overrides the display.
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

async function selectIppBody(page: import("@playwright/test").Page) {
  // Select line 6 of the default library (the Initial Population
  // expression body):
  // `  exists([Patient] P where P.gender = 'female')`
  await page.click("[data-testid=cql-editor] .monaco-editor");
  await page.keyboard.press("Control+Home");
  for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Home");
  await page.keyboard.press("Shift+End");
}

async function tableHeader(page: import("@playwright/test").Page) {
  return page.locator("[data-testid=results-table] th").allTextContents();
}

/** Completion signal for a manual run: the switcher gains an option.
 *  (The results table is ALWAYS visible now — the auto run renders it —
 *  so visibility alone cannot tell a manual run landed.) */
async function waitForRunCount(
  page: import("@playwright/test").Page,
  n: number,
) {
  await page.waitForFunction(
    (target) =>
      document.querySelectorAll("[data-testid=console-run-select] option")
        .length >= target,
    n,
    { timeout: 60_000 },
  );
}

test.describe("cql console (run-centric)", () => {
  test("editor Run evaluates the whole library", async ({ page }) => {
    await bootReady(page);
    await expect(page.locator("[data-testid=results-console]")).toBeVisible();
    // No header chrome — the tabs strip carries the switcher instead.
    await expect(page.locator("[data-testid=results-console] h2")).toHaveCount(0);
    await page.click("[data-testid=editor-run]");
    const table = page.locator("[data-testid=results-table]");
    await expect(table).toBeVisible({ timeout: 60_000 });
    // Default dataset: p1/p2/p3 all present, population columns included.
    await expect(table).toContainText("p1");
    await expect(table).toContainText("p2");
    await expect(table).toContainText("Initial Population");
  });

  test("editor Run with a selection evaluates just the selection", async ({
    page,
  }) => {
    await bootReady(page);
    const runBtn = page.locator("[data-testid=editor-run]");
    await expect(runBtn).toHaveText("Run");
    await selectIppBody(page);
    await expect(runBtn).toHaveText("Run selection");
    const prior = await page
      .locator("[data-testid=console-run-select] option")
      .count();
    await runBtn.click();
    await waitForRunCount(page, prior + 1);
    // Narrowed output: patient_id + snippet only (the manual run
    // OVERRIDES the auto-eval table).
    const header = (await tableHeader(page)).join(",");
    expect(header).toContain("patient_id");
    expect(header).toContain("snippet");
    expect(header).not.toContain("Initial Population");
    // p1/p3 female → true, p2 male → false.
    const rows = await page
      .locator("[data-testid=results-table] tbody tr")
      .allTextContents();
    const p1 = rows.find((r) => r.includes("p1")) ?? "";
    const p2 = rows.find((r) => r.includes("p2")) ?? "";
    expect(p1).toContain("true");
    expect(p2).toContain("false");
  });

  test("Ctrl/Cmd+Enter runs the selection from the editor (6e)", async ({
    page,
  }) => {
    await bootReady(page);
    await selectIppBody(page);
    // No button involved — the editor shortcut drives the run.
    const prior = await page
      .locator("[data-testid=console-run-select] option")
      .count();
    await page.keyboard.press("Control+Enter");
    await waitForRunCount(page, prior + 1);
    const header = (await tableHeader(page)).join(",");
    expect(header).toContain("snippet");
    const rows = await page
      .locator("[data-testid=results-table] tbody tr")
      .allTextContents();
    const p1 = rows.find((r) => r.includes("p1")) ?? "";
    expect(p1).toContain("true");
  });

  test("a broken selection surfaces a renumbered diagnostic", async ({
    page,
  }) => {
    await bootReady(page);
    // Replace the whole editor text with a broken one-liner and select it.
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+A");
    await page.keyboard.press("Delete");
    await page.keyboard.type("define \"X\":\n  exists [Patient] where");
    await page.keyboard.press("Control+Home");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Home");
    await page.keyboard.press("Shift+End");
    await page.click("[data-testid=editor-run]");
    // The diagnostic must NOT point at the appended-block line numbers
    // (8+); it is renumbered relative to the snippet (line ≤ 2).
    await expect(page.locator("[data-testid=console-diags]")).toBeVisible({
      timeout: 60_000,
    });
    const loc = await page
      .locator("[data-testid=console-diags] .diag-loc")
      .first()
      .textContent();
    const line = Number((loc ?? "").replace("L", "").split(":")[0]);
    expect(line).toBeLessThanOrEqual(3);
  });
});

test.describe("run ring + switcher (6g)", () => {
  test("manual runs override; the switcher replays results/SQL/AST/CQL", async ({
    page,
  }) => {
    await bootReady(page);
    // Auto heartbeat run lands first: population columns.
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });

    // Manual SELECTION run — overrides the display to snippet columns…
    const prior = await page
      .locator("[data-testid=console-run-select] option")
      .count();
    await selectIppBody(page);
    await page.click("[data-testid=editor-run]");
    await waitForRunCount(page, prior + 1);
    expect((await tableHeader(page)).join(",")).toContain("snippet");
    // …and the CQL tab shows the executed __snippet__ wrapper.
    await page.click("[data-testid=console-tab-cql]");
    await expect(page.locator("[data-testid=cql-viewer]")).toContainText(
      "__snippet__",
      { timeout: 15_000 },
    );

    // Switch back to a prior LIBRARY run (the auto heartbeat): the
    // table replays its full population columns, and SQL/AST/CQL come
    // from the SAME run.
    await page.click("[data-testid=console-tab-results]");
    // Options are newest-first; pick a LIBRARY-mode run (the auto
    // heartbeat) via its label suffix.
    const libRunValue = await page.evaluate(() => {
      const sel = document.querySelector(
        "[data-testid=console-run-select]",
      ) as HTMLSelectElement | null;
      const opt = [...(sel?.options ?? [])].find((o) =>
        (o.textContent ?? "").includes("· library"),
      );
      return opt?.value ?? "";
    });
    if (!libRunValue) throw new Error("no library run in the switcher");
    await page.selectOption("[data-testid=console-run-select]", libRunValue);
    await expect(page.locator("[data-testid=results-table]")).toContainText(
      "initial_population",
      { timeout: 15_000 },
    );
    await page.click("[data-testid=console-tab-sql]");
    await expect(page.locator("[data-testid=sql-viewer]")).toBeVisible();
    await page.click("[data-testid=console-tab-ast]");
    await expect(
      page.locator(".ast-filter-row, .ast-row").first(),
    ).toBeVisible();
    await page.click("[data-testid=console-tab-cql]");
    await expect(page.locator("[data-testid=cql-viewer]")).toContainText(
      "library CleanroomDemo",
    );
    await expect(page.locator("[data-testid=cql-viewer]")).not.toContainText(
      "__snippet__",
    );

    // A new manual run (library mode — selection collapsed) overrides
    // back to the latest.
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+Home");
    await page.click("[data-testid=editor-run]");
    await waitForRunCount(page, prior + 2);
    expect((await tableHeader(page)).join(",")).toContain(
      "Initial Population",
    );
  });
});
