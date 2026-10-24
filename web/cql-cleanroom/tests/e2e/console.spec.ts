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
  // S25: cells view is console-FREE by design, and the default library
  // auto-cellifies (markers injected, cells view opens). These specs
  // exercise the TEXT editor + console — if cells auto-opened, switch
  // back to text and wait for a clean re-parse.
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) await gotIt.click();
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  try {
    await toggle.waitFor({ state: "visible", timeout: 10_000 });
    if ((await toggle.getAttribute("aria-checked")) === "true") {
      await toggle.click();
      await page.waitForFunction(
        () =>
          (document
            .querySelector('[data-testid="parse-status"]')
            ?.textContent ?? "").includes("parsed ✓"),
        { timeout: 30_000 },
      );
    }
  } catch {
    /* toggle absent — text view already */
  }
}

async function selectIppBody(page: import("@playwright/test").Page) {
  // Select the Initial Population expression body:
  // `  exists([Patient] P where P.gender = 'female')`
  // S25: marker-agnostic navigation — the buffer may carry auto-injected
  // `// # %%` cell markers, so walk down from Home until the caret sits
  // on the expression-body LINE (derived exactly from the textarea's
  // selectionStart against the full buffer), then Home + Shift+End.
  const target = "exists([Patient] P where P.gender = 'female')";
  await page.click("[data-testid=cql-editor] .monaco-editor");
  await page.keyboard.press("Control+Home");
  for (let i = 0; i < 15; i++) {
    const onTarget = await page.evaluate((needle) => {
      const ta = document.querySelector(
        "[data-testid=cql-editor] textarea",
      ) as HTMLTextAreaElement | null;
      if (!ta) return false;
      const pos = ta.selectionStart ?? 0;
      const before = ta.value.slice(0, pos);
      const lineStart = before.lastIndexOf("\n") + 1;
      const line = ta.value.slice(lineStart, ta.value.indexOf("\n", lineStart));
      return line.includes(needle);
    }, target);
    if (onTarget) {
      await page.keyboard.press("Home");
      await page.keyboard.press("Shift+End");
      return;
    }
    await page.keyboard.press("ArrowDown");
  }
  throw new Error("IPP expression body line not found");
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
    // S26 (items 1+2 doctrine): library runs show EVERY define's column
    // (all-defines output, S23-1) — including the demo's
    // Initial Population define, never measure-mapped population codes.
    await expect(page.locator("[data-testid=results-table]")).toContainText(
      "Initial Population",
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

test.describe("shape-aware runs + active-tab targeting (6j)", () => {
  test("selecting the whole library runs it AS the library", async ({
    page,
  }) => {
    await bootReady(page);
    const prior = await page
      .locator("[data-testid=console-run-select] option")
      .count();
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+A");
    await page.click("[data-testid=editor-run]");
    await waitForRunCount(page, prior + 1);
    // No __snippet__ wrapper: output = all defines, and the CQL tab is
    // exactly the library text (no appended define).
    const header = (await tableHeader(page)).join(",");
    expect(header).toContain("patient_id");
    expect(header).toContain("Initial Population");
    expect(header).not.toContain("snippet");
    await page.click("[data-testid=console-tab-cql]");
    await expect(page.locator("[data-testid=cql-viewer]")).not.toContainText(
      "__snippet__",
    );
  });

  test("selecting a define statement runs it unwrapped (no snippet column)", async ({
    page,
  }) => {
    await bootReady(page);
    const prior = await page
      .locator("[data-testid=console-run-select] option")
      .count();
    // Select the `define "Initial Population":` line + its body
    // (marker-agnostic: walk to the define-header line by content).
    const needle = 'define "Initial Population":';
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+Home");
    for (let i = 0; i < 15; i++) {
      const onTarget = await page.evaluate((n) => {
        const ta = document.querySelector(
          "[data-testid=cql-editor] textarea",
        ) as HTMLTextAreaElement | null;
        if (!ta) return false;
        const pos = ta.selectionStart ?? 0;
        const before = ta.value.slice(0, pos);
        const lineStart = before.lastIndexOf("\n") + 1;
        const line = ta.value.slice(lineStart, ta.value.indexOf("\n", lineStart));
        return line.includes(n);
      }, needle);
      if (onTarget) break;
      await page.keyboard.press("ArrowDown");
    }
    await page.keyboard.press("Home");
    await page.keyboard.press("Shift+ArrowDown");
    await page.keyboard.press("Shift+End");
    await page.click("[data-testid=editor-run]");
    await waitForRunCount(page, prior + 1);
    const header = (await tableHeader(page)).join(",");
    expect(header).toContain("patient_id");
    expect(header).toContain("Initial Population");
    expect(header).not.toContain("snippet");
  });

  test("runs follow the active library tab (Library2 output + ring label)", async ({
    page,
  }) => {
    await bootReady(page);
    await page.click("[data-testid=nav-toggle-libraries]");
    await page.click("[data-testid=library-tab-add]");
    await page.waitForSelector("[data-testid=library-tab-1]");
    await page.waitForSelector("[data-testid=cql-editor]");
    // Author a distinctive define in Library2.
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+A");
    await page.keyboard.press("Delete");
    await page.keyboard.type(
      "library Library2 version '1.0.0'\nusing FHIR version '4.0.1'\n\ndefine \"FromLib2\":\n  true\n",
    );
    // The heartbeat follows the active tab: the auto run lands with
    // Library2's define as the output column (no manual click needed).
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll("[data-testid=results-table] th")]
          .some((th) => th.textContent?.includes("FromLib2")),
      undefined,
      { timeout: 60_000 },
    );
    // The ring entry names its library.
    const latest = await page.evaluate(() => {
      const sel = document.querySelector<HTMLSelectElement>(
        "[data-testid=console-run-select]",
      );
      return sel?.options[1]?.textContent ?? "";
    });
    expect(latest).toContain("Library2");
    // Switching back to the entrypoint tab restores the heartbeat's
    // define columns (S26 doctrine: library runs show every define —
    // the demo's Initial Population among them).
    await page.click("[data-testid=library-tab-0]");
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll("[data-testid=results-table] th")]
          .some((th) => th.textContent?.includes("Initial Population")),
      undefined,
      { timeout: 60_000 },
    );
  });
});

test.describe("results table (S26 doctrine: all defines, live)", () => {
  test("Results tab evaluates every define live as you type", async ({
    page,
  }) => {
    await bootReady(page);
    // S26 (items 1+2): the Defines tab is GONE — the Results table IS
    // the all-defines matrix (every define, population or not).
    await expect(
      page.locator("[data-testid=console-tab-defines]"),
    ).toHaveCount(0);
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 120_000,
    });
    const header = (
      await page.locator("[data-testid=results-table] th").allTextContents()
    ).join(",");
    expect(header).toContain("patient_id");
    expect(header).toContain("Initial Population");
    expect(header).toContain("Has Name");
    // p1/p3 female → Initial Population true; p2 male → false.
    const rows = await page
      .locator("[data-testid=results-table] tbody tr")
      .allTextContents();
    expect(rows.find((r) => r.includes("p1")) ?? "").toContain("true");
    expect(rows.find((r) => r.includes("p2")) ?? "").toContain("false");
    // LIVE: author a new define — it joins the table with no manual run.
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+End");
    await page.keyboard.type('\ndefine "MatrixCheck":\n  true\n');
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll("[data-testid=results-table] th")].some(
          (th) => th.textContent?.includes("MatrixCheck"),
        ),
      undefined,
      { timeout: 60_000 },
    );
  });
});

test.describe("workspace completions (visual editor 2)", () => {
  test("suggests defines and dataset retrieves from the workspace", async ({
    page,
  }) => {
    await bootReady(page);
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+End");
    // Workspace define suggestion.
    await page.keyboard.type('\ndefine "TryMe":\n  H');
    await page.waitForSelector(".suggest-widget .monaco-list-row", {
      timeout: 15_000,
    });
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".suggest-widget .monaco-list-row")].some(
          (r) => r.textContent?.includes("Has Name"),
        ),
      undefined,
      { timeout: 10_000 },
    );
    // Retrieve: `[` suggests dataset resource types (the default
    // dataset only carries Patients).
    await page.keyboard.press("Escape");
    await page.keyboard.press("Control+End");
    await page.keyboard.press("Backspace");
    await page.keyboard.press("Backspace");
    await page.keyboard.type("exists([");
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".suggest-widget .monaco-list-row")].some(
          (r) => r.textContent?.includes("Patient"),
        ),
      undefined,
      { timeout: 10_000 },
    );
  });
});

test.describe("hover evaluation (visual editor 3)", () => {
  test("hovering a define shows its live per-patient values", async ({
    page,
  }) => {
    await bootReady(page);
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 120_000,
    });
    const line = page
      .locator(".view-lines .view-line", { hasText: "Has Name" })
      .first();
    await line.hover({ position: { x: 100, y: 8 } });
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".monaco-hover")].some(
          (h) =>
            !h.classList.contains("hidden") &&
            (h.textContent || "").includes("p1") &&
            (h.textContent || "").includes("Has Name"),
        ),
      undefined,
      { timeout: 60_000 },
    );
  });
});

test.describe("outline + jump-to-define (visual editor 4)", () => {
  test("outline lists symbols; clicking jumps to the declaration", async ({
    page,
  }) => {
    await bootReady(page);
    // The outline needs the mounted Monaco instance (jump target) —
    // wait for it, or the click races the dynamic import and no-ops.
    await page.waitForSelector("[data-testid=cql-editor] .monaco-editor");
    await page.click("[data-testid=editor-outline]");
    const panel = page.locator("[data-testid=outline-panel]");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("Defines");
    await expect(panel).toContainText("Initial Population");
    await expect(panel).toContainText("Has Name");
    // Line pins are MARKER-DEPENDENT: the buffer may carry auto-injected
    // `// # %%` cell markers (+2 lines) or not. Assert both defines have
    // line refs without pinning exact numbers.
    await expect(panel).toContainText(/L(6|8)/);
    await expect(panel).toContainText(/L(10|12)/);
    // Jump: the current-line highlight must land on the "Has Name"
    // declaration (line 8) — same viewport row as that view-line.
    await panel
      .locator("[data-testid=outline-item]", { hasText: "Has Name" })
      .first()
      .click();
    await expect(panel).toHaveCount(0);
    const target = page
      .locator(".view-lines .view-line", { hasText: "Has Name" })
      .first();
    await expect(target).toBeVisible({ timeout: 10_000 });
    const box = await target.boundingBox();
    await page.waitForFunction(
      (ty) => {
        const cur = document.querySelector(".view-overlays .current-line");
        return cur
          ? Math.abs(cur.getBoundingClientRect().top - (ty as number)) < 20
          : false;
      },
      box!.y,
      { timeout: 10_000 },
    );
  });
});
