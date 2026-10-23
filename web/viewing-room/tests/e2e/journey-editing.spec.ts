/**
 * JOURNEY tests #2-4 (design §6, from the design's own words):
 *  - "editing the VD and re-running reflects the edit"
 *  - "invalid VD shows typed diagnostics, never a blank screen"
 *  - "wrong-resourceType input yields the 0-rows hint"
 */

import { test, expect } from "@playwright/test";

/** Set the VD editor content via the app's editor test hook (Monaco
 *  auto-closing brackets make keyboard-typed JSON non-deterministic). */
async function setVdEditor(page: import("@playwright/test").Page, text: string) {
  await page.evaluate((t) => {
    (window as any).__vrVdEditor.setValue(t);
  }, text);
}

test("journey: editing the VD and re-running reflects the edit", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(2, { timeout: 30_000 });

  // Drop the gender column: edit the VD JSON (remove the gender column block)
  // and re-run; the output table must reflect the edit (no gender column).
  const vdText = await page.evaluate(() => {
    const ed = (window as any).__vrVdEditor as any;
    return ed ? ed.getValue() : null;
  });
  expect(vdText).toBeTruthy();
  const edited = vdText!
    .split("\n")
    .filter((l: string) => !/"gender"/.test(l) && !/"path": "gender"/.test(l))
    .join("\n")
    // remove the now-dangling gender column object lines is fragile; instead
    // rebuild a minimal VD deterministically:
    .replace(/\{\s*"path": "gender",\s*"name": "gender"\s*\},?/s, "");
  await setVdEditor(page, JSON.stringify({
    resource: "Patient",
    select: [{ column: [{ name: "id", path: "getResourceKey()" }] }],
  }));
  await page.getByRole("button", { name: /Run view/ }).click();
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(2, { timeout: 30_000 });
  // The edited view has exactly one data column: id (no gender).
  await expect(page.getByTestId("output-table").locator("thead th")).toHaveCount(1);
  await expect(page.getByTestId("output-table")).toContainText("p1");
});

test("journey: invalid VD shows typed diagnostics, never a blank screen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });

  // Break the VD structurally (missing select) and run.
  await setVdEditor(page, JSON.stringify({ resource: "Patient" }));
  await page.getByRole("button", { name: /Run view/ }).click();
  const list = page.getByTestId("diagnostics-list");
  await expect(list).toBeVisible({ timeout: 30_000 });
  await expect(list.locator(".diagnostic-card").first()).toBeVisible();
  await expect(list).toContainText(/select/i);

  // Non-JSON text: typed vd_json_error diagnostic (still not a blank screen).
  await setVdEditor(page, "not json at all {");
  await page.getByRole("button", { name: /Run view/ }).click();
  await expect(page.getByTestId("diagnostics-list")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("diagnostics-list")).toContainText("not valid JSON");
});

test("journey: wrong-resourceType input yields the 0-rows hint", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(2, { timeout: 30_000 });

  // Replace the resources with Observations (VD targets Patient).
  await page.evaluate(() => {
    (window as any).__vrResourcesEditor.setValue(
      JSON.stringify({ resourceType: "Observation", id: "o1", status: "final", code: { text: "BP" } }) + "\n",
    );
  });
  await page.getByRole("button", { name: /Run view/ }).click();
  const hint = page.getByTestId("empty-hint");
  await expect(hint).toBeVisible({ timeout: 30_000 });
  await expect(hint).toContainText('ViewDefinition.resource="Patient"');
  await expect(hint).toContainText("Observation");
});
