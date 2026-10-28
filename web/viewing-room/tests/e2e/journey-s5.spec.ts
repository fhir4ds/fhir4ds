/**
 * JOURNEY tests for S5 (Joel checkpoint feedback, from his own words):
 *  - Browse: "switch to Browse, see resources grouped by type; select a
 *    resource -> its JSON; VD.resource mismatch -> highlightTypes shows"
 *  - Auto-recalc: "just recalc after a change instead of hitting a button"
 *    (rapid multi-edits -> final state only)
 *  - Reference alignment: "default sample renders the reference's patient
 *    set (pin a name/id from the reference data)"
 */

import { test, expect } from "@playwright/test";

test("journey: default sample is the reference playground's patient set", async ({ page }) => {
  await page.goto("/?data=local");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });

  // The reference bundles 25 Synthea patients; the default VD (reference's
  // own) yields one row per name (35). Pin the Bechtelar572 maiden name.
  const table = page.getByTestId("output-table");
  await expect(table.locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });
  await expect(table).toContainText("Bechtelar572");
  await expect(table).toContainText("Cole117");
  // Reference VD columns: id / birthDate / last_name / first_name.
  const headers = await table.locator("thead th").allTextContents();
  expect(headers).toEqual(["id", "birthDate", "last_name", "first_name"]);
});

test("journey: editing the VD recalcs automatically — no button press", async ({ page }) => {
  await page.goto("/?data=local");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  const table = page.getByTestId("output-table");
  await expect(table.locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  // Change the VD to a single-column view; WITHOUT clicking Run, the output
  // updates after the debounce.
  await page.evaluate(() => {
    (window as any).__vrVdEditor.setValue(
      JSON.stringify(
        { resource: "Patient", select: [{ column: [{ name: "id", path: "id" }] }] },
        null,
        2,
      ),
    );
  });
  await expect(table.locator("thead th")).toHaveText(["id"], { timeout: 15_000 });
  await expect(table.locator("tbody tr")).toHaveCount(25, { timeout: 15_000 });

  // Rapid multi-edits collapse to the final state only: type a sequence of
  // changes quickly, then assert ONLY the last one's result.
  for (const col of ["gender", "birthDate", "id"]) {
    await page.evaluate((c) => {
      (window as any).__vrVdEditor.setValue(
        JSON.stringify({ resource: "Patient", select: [{ column: [{ name: c, path: c }] }] }, null, 2),
      );
    }, col);
  }
  await expect(table.locator("thead th")).toHaveText(["id"], { timeout: 15_000 });
  await expect(table.locator("tbody tr")).toHaveCount(25, { timeout: 15_000 });
});

test("journey: Browse tab groups resources by type and highlights the VD target", async ({ page }) => {
  await page.goto("/?data=local");
  await expect(page.getByTestId("version-badge")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("output-table").locator("tbody tr")).toHaveCount(35, { timeout: 60_000 });

  // Switch to Browse: resources grouped by type.
  await page.getByRole("tab", { name: "Browse" }).click();
  const viewer = page.getByTestId("resource-viewer");
  await expect(viewer).toBeVisible();
  const group = page.getByTestId("resource-group-Patient");
  await expect(group).toBeVisible();
  await expect(group.locator(".resource-viewer-count")).toHaveText("25");

  // VD targets Patient -> the Patient group carries the highlight.
  await expect(group).toHaveClass(/resource-highlight/);

  // Resource-type groups start collapsed; open the group, then the item
  // (JSON trees mount lazily so large datasets stay cheap to render).
  await group.locator("summary").first().click();
  const item = group.locator(".resource-viewer-item").first();
  await item.locator("summary").click();
  await expect(item).toContainText("resourceType");
  await expect(item.locator(".json-tree-key").filter({ hasText: "birthDate" })).toBeVisible();

  // Highlight follows the VD: switch the VD to Observation with wrong-type
  // resources loaded -> after recalc the Patient group loses the highlight.
  await page.getByRole("tab", { name: "Editor" }).click();
  await page.evaluate(() => {
    (window as any).__vrVdEditor.setValue(
      JSON.stringify({ resource: "Observation", select: [{ column: [{ name: "id", path: "id" }] }] }, null, 2),
    );
  });
  await page.getByRole("tab", { name: "Browse" }).click();
  await expect(page.getByTestId("resource-group-Patient")).not.toHaveClass(/resource-highlight/, {
    timeout: 15_000,
  });
});
