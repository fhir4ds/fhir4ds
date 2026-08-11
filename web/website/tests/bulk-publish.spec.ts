import { test, expect } from "@playwright/test";

// Smoke test for the embedded Bulk Publish demo at /docs/examples/bulk-publish.
// Verifies the page mounts, all five sections render, and DuckDB-WASM +
// Pyodide boot to the point where data is ingestable. This is NOT a full
// re-run of the demo's verify-slice scripts — those live alongside the
// standalone demo and exercise deeper behavior (cross-schema normalization,
// geo-search, etc.). This test is the website-gate canary.

test.describe("Bulk Publish demo", () => {
  test("page mounts with all five sections", async ({ page }) => {
    test.setTimeout(120000);
    await page.goto("/docs/examples/bulk-publish");

    await expect(page).toHaveTitle(/Bulk Publish Demo/);

    // H1 from the MDX frontmatter title.
    await expect(
      page.getByRole("heading", { level: 1, name: "Bulk Publish + FHIR4DS Demo" }),
    ).toBeVisible();

    // Section headings — the five vertical sections of the walkthrough.
    // They render as H2s inside the demo's Section component, but they can
    // also appear in the right-side ToC. Scope to .bulk-publish-demo-app
    // so we only count the in-page ones.
    const demoRoot = page.locator(".bulk-publish-demo-app");
    const expectedHeadings = [
      /Connect to a Bulk Publish endpoint/i,
      /Browse the raw published FHIR resources/i,
      /From ViewDefinition to a flat queryable table/i,
      /Filter the materialized table with plain SQL/i,
      /The same engine, as a patient-facing app/i,
    ];
    for (const pattern of expectedHeadings) {
      await expect(demoRoot.locator("h2", { hasText: pattern }).first()).toBeVisible();
    }
  });

  test("DuckDB-WASM and Pyodide boot successfully", async ({ page }) => {
    test.setTimeout(180000); // first Pyodide load is slow (wheel fetch + micropip)

    const readyLogs: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (
        text.includes("DuckDB] Ready") ||
        text.includes("Pyodide Worker] Initialization complete")
      ) {
        readyLogs.push(text);
      }
    });

    await page.goto("/docs/examples/bulk-publish");

    // Wait for the DuckDB ready log (extensions loaded + connection open).
    // The demo emits "[DuckDB] Ready — extensions loaded" verbatim.
    await expect
      .poll(() => readyLogs.some((l) => l.includes("DuckDB] Ready")), {
        timeout: 120000,
        message: "DuckDB should reach Ready state",
      })
      .toBeTruthy();

    // Wait for the Pyodide worker to finish installing fhir4ds.
    await expect
      .poll(
        () =>
          readyLogs.some((l) =>
            l.includes("Pyodide Worker] Initialization complete"),
          ),
        {
          timeout: 120000,
          message: "Pyodide worker should finish initialization",
        },
      )
      .toBeTruthy();
  });
});
