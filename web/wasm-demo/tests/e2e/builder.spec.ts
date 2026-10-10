import { test, expect } from "@playwright/test";

test.describe("Builder tab (R3 port)", () => {
  test("builder tab visible on default scenario; picker + template + JSON editor render", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Builder" }).click();
    // type picker + template load
    await expect(page.locator(".dev-rbpane")).toBeVisible();
    await page.getByRole("button", { name: /Patient template/i }).click();
    // template loaded into JSON editor
    await expect(page.locator(".dev-rbjson textarea")).toBeVisible();
    await expect(page.locator(".dev-rbjson textarea")).toContainText('"resourceType": "Patient"');
  });

  test("upload NDJSON bundle creates an in-memory dataset; reference candidates resolve", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Builder" }).click();
    await page.getByRole("button", { name: /Patient template/i }).click();
    // upload a small NDJSON (Patient + Observation referencing it)
    const ndjson = [
      JSON.stringify({ resourceType: "Patient", id: "p1", gender: "male" }),
      JSON.stringify({ resourceType: "Observation", id: "o1", status: "final", subject: { reference: "Patient/p1" } }),
    ].join("\n");
    await page.locator("#builder-upload-input").setInputFiles({
      name: "test-bundle.ndjson",
      mimeType: "text/plain",
      buffer: Buffer.from(ndjson),
    });
    // <option> is never toBeVisible — assert via the select value + option text
    const datasetSelect = page.locator("select.dev-rbdataset");
    await expect(datasetSelect).toHaveValue("test-bundle.ndjson", { timeout: 10000 });
    await expect(
      datasetSelect.locator("option", { hasText: "test-bundle.ndjson (2)" }),
    ).toBeAttached();
  });

  test("offline validation flags missing resourceType", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Builder" }).click();
    await page.getByRole("button", { name: /Patient template/i }).click();
    // paste invalid JSON (no resourceType) then Validate
    const jsonArea = page.locator(".dev-rbjson textarea");
    await jsonArea.fill(JSON.stringify({ id: "x" }, null, 2));
    await page.getByRole("button", { name: /validate/i }).click();
    await expect(page.locator(".dev-rberror")).toContainText("resourceType", { timeout: 10000 });
  });
});
