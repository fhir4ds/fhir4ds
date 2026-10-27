import { test, expect } from "@playwright/test";

// S7 website integration: the /docs/examples/viewing-room page embeds the
// <sqlonfhir-viewing-room> web component from static/viewing-room-app/
// (direct embed + popout pill, matching the cql-clinic/cleanroom example
// page convention — no lazy-launch card on example pages).

test.setTimeout(240_000);

test("viewing-room example page embeds and boots the component", async ({ page }) => {
  await page.goto("/docs/examples/viewing-room");

  // Page chrome: title + sidebar entry between Quality Measures and SDC Forms.
  await expect(page.locator("h1")).toHaveText("SQL-on-FHIR Viewing Room");
  const sidebar = page.locator('nav[aria-label="Docs sidebar"]');
  await expect(sidebar.getByRole("link", { name: "Viewing Room" })).toBeVisible();

  // Prev/next pagination flows Quality Measures -> Viewing Room -> SDC Forms.
  await expect(
    page.locator(".pagination-nav__link--prev"),
  ).toHaveAttribute("href", /\/docs\/examples\/cms-measures\/$/);
  // Sidebar order: Quality Measures -> Viewing Room -> OMOP Step by Step -> ...
  await expect(
    page.locator(".pagination-nav__link--next"),
  ).toHaveAttribute("href", /\/docs\/examples\/omop-step-by-step\/$/);

  // The popout pill points at the standalone app; the embed boots directly.
  const wc = page.locator("sqlonfhir-viewing-room");
  await expect(wc).toBeAttached();
  const badge = wc.locator(".version-badge");
  await expect(badge).toContainText(/fhir4ds \d+\.\d+\.\d+/, { timeout: 120_000 });

  // Default sample auto-ran inside the Docusaurus embed (reference set: 35).
  await expect(
    wc.locator('[data-testid="output-table"] tbody tr'),
  ).toHaveCount(35, { timeout: 60_000 });
});

test("OMOP step-by-step page documents the three artifacts", async ({ page }) => {
  await page.goto("/docs/examples/omop-step-by-step");
  await expect(page.locator("h1")).toHaveText("OMOP, Step by Step");

  const sidebar = page.locator('nav[aria-label="Docs sidebar"]');
  await expect(sidebar.getByRole("link", { name: "OMOP Step by Step" })).toBeVisible();

  // Pagination: Viewing Room -> OMOP Step by Step -> OMOP Demo.
  await expect(page.locator(".pagination-nav__link--prev")).toHaveAttribute(
    "href",
    /\/docs\/examples\/viewing-room\/$/,
  );
  await expect(page.locator(".pagination-nav__link--next")).toHaveAttribute(
    "href",
    /\/docs\/examples\/omop-viewer\/$/,
  );

  // One section per step, each with the real artifact.
  for (const h2 of [
    "Step 1 — SQL-on-FHIR basics: person from Patient",
    "Step 2 — ConceptMap: codes in, concept ids out",
    "Step 3 — SQLQuery: unioning views across resource types",
  ]) {
    await expect(page.locator("article h2", { hasText: h2 })).toBeVisible();
  }
  await expect(page.locator("article pre")).toHaveCount(11);

  // Each step deep-links the live sample it describes.
  for (const sample of ["omop-patient", "omop-drug-exposure", "omop-drug-exposure-sqlquery"]) {
    await expect(
      page.locator(`article a[href*="sample=${sample}"]`).first(),
    ).toBeVisible();
  }
});

test("OMOP demo page embeds the suite-filtered component", async ({ page, request }) => {
  const probe = await request
    .get("https://huggingface.co/datasets/fhir4ds/omop-demo/resolve/main/patient-resources.ndjson", {
      timeout: 30_000,
    })
    .catch(() => null);
  if (!probe || !probe.ok()) test.skip(true, "Hugging Face dataset unreachable");

  await page.goto("/docs/examples/omop-viewer");
  await expect(page.locator("h1")).toHaveText("OMOP Demo");
  const sidebar = page.locator('nav[aria-label="Docs sidebar"]');
  await expect(sidebar.getByRole("link", { name: "OMOP Demo" })).toBeVisible();
  await expect(
    page.locator(".pagination-nav__link--prev"),
  ).toHaveAttribute("href", /\/docs\/examples\/omop-step-by-step\/$/);
  await expect(
    page.locator(".pagination-nav__link--next"),
  ).toHaveAttribute("href", /\/docs\/examples\/sdc-playground\/$/);

  const wc = page.locator("sqlonfhir-viewing-room");
  await expect(wc).toBeAttached();
  await expect(wc.locator(".version-badge")).toContainText(/fhir4ds \d+\.\d+\.\d+/, {
    timeout: 120_000,
  });
  // suite="omop": OMOP-only gallery + the 25-patient cohort as default.
  await expect(wc.locator("header select option")).toHaveCount(4, { timeout: 60_000 });
  await expect(wc.locator('[data-testid="output-table"] tbody tr')).toHaveCount(25, {
    timeout: 180_000,
  });
});
