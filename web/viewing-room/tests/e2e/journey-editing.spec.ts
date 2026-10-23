/**
 * JOURNEY tests #2-4 (design §6, from the design's own words):
 *  - "editing the VD and re-running reflects the edit"
 *  - "invalid VD shows typed diagnostics, never a blank screen"
 *  - "wrong-resourceType input yields the 0-rows hint"
 */

import { test, expect } from "@playwright/test";

/** Set the VD editor content via the app's editor test hook (Monaco
 *  auto-closing brackets make keyboard-typed JSON non-deterministic).
 *  Waits for the hook (editor mounts after the app loads). */
async function setVdEditor(page: import("@playwright/test").Page, text: string) {
  await page.waitForFunction(() => !!(window as any).__vrVdEditor);
  await page.evaluate((t) => {
    (window as any).__vrVdEditor.setValue(t);
  }, text);
}

test("journey: editing the VD and re-running reflects the edit", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  await setVdEditor(page, JSON.stringify({
    resource: "Patient",
    select: [{ column: [{ name: "id", path: "getResourceKey()" }] }],
  }));
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(25, { timeout: 15_000 });
  // The edited view has exactly one data column: id (no gender).
  await expect(page.getByTestId("output-table").locator("thead th")).toHaveCount(1);
  await expect(page.getByTestId("output-table")).toContainText("269a6a02");
});

test("journey: invalid VD shows typed diagnostics, never a blank screen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  // Let the default sample's first run settle before editing (its
  // load-completion callback runs with the SAMPLE text and would otherwise
  // race the edit).
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  // Break the VD structurally (missing select): auto-recalc surfaces typed
  // diagnostics within the debounce window.
  await setVdEditor(page, JSON.stringify({ resource: "Patient" }));
  const list = page.getByTestId("diagnostics-list");
  await expect(list).toBeVisible({ timeout: 15_000 });
  await expect(list.locator(".diagnostic-card").first()).toBeVisible();
  await expect(list).toContainText(/select/i);

  // Non-JSON text: typed vd_json_error diagnostic (still not a blank screen).
  await setVdEditor(page, "not json at all {");
  await expect(page.getByTestId("diagnostics-list")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("diagnostics-list")).toContainText("not valid JSON");
});

test("journey: wrong-resourceType input yields the 0-rows hint", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  // Replace the resources with Observations (VD targets Patient).
  // Browse is the default tab — switch to Editor to edit the resources.
  await page.getByRole("tab", { name: "Editor" }).click();
  await page.evaluate(() => {
    (window as any).__vrResourcesEditor.setValue(
      JSON.stringify({ resourceType: "Observation", id: "o1", status: "final", code: { text: "BP" } }) + "\n",
    );
  });
  const hint = page.getByTestId("empty-hint");
  await expect(hint).toBeVisible({ timeout: 15_000 });
  await expect(hint).toContainText('ViewDefinition.resource="Patient"');
  await expect(hint).toContainText("Observation");
});
