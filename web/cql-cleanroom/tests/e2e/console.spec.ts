import { expect, test } from "@playwright/test";

/**
 * WORKBENCH_REORG phase 4: the CQL console below the editor — Run
 * evaluates the whole library; Run-Selection evaluates the highlighted
 * expression in context (replaces the retired FHIRPath scratchpad; its
 * "p1 → Ann" coverage migrated here as the female-population select).
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

test.describe("cql console", () => {
  test("Run evaluates the whole library", async ({ page }) => {
    await bootReady(page);
    await expect(page.locator("[data-testid=results-console]")).toBeVisible();
    await page.click("[data-testid=console-run-library]");
    const table = page.locator("[data-testid=console-table]");
    await expect(table).toBeVisible({ timeout: 60_000 });
    // Default dataset: p1/p2/p3 all present, population columns included.
    await expect(table).toContainText("p1");
    await expect(table).toContainText("p2");
    await expect(table).toContainText("Initial Population");
  });

  test("Run selection evaluates the highlighted expression in context", async ({
    page,
  }) => {
    await bootReady(page);
    // Run-Selection is disabled until the editor reports a selection.
    await expect(page.locator("[data-testid=console-run-selection]")).toBeDisabled();
    // Select line 6 of the default library (the Initial Population
    // expression body):
    // `  exists([Patient] P where P.gender = 'female')`
    await page.click("[data-testid=cql-editor] .monaco-editor");
    await page.keyboard.press("Control+Home");
    for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Home");
    await page.keyboard.press("Shift+End");
    await page.click("[data-testid=console-run-selection]");
    const table = page.locator("[data-testid=console-table]");
    await expect(table).toBeVisible({ timeout: 60_000 });
    // Narrowed output: patient_id + snippet only.
    const header = await page.locator("[data-testid=console-table] th").allTextContents();
    expect(header).toEqual(["patient_id", "snippet"]);
    // p1/p3 female → true, p2 male → false.
    const rows = await page.locator("[data-testid=console-table] tbody tr").allTextContents();
    const p1 = rows.find((r) => r.includes("p1")) ?? "";
    const p2 = rows.find((r) => r.includes("p2")) ?? "";
    expect(p1).toContain("true");
    expect(p2).toContain("false");
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
    await page.click("[data-testid=console-run-selection]");
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
