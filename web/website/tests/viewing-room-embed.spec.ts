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
  await expect(
    page.locator(".pagination-nav__link--next"),
  ).toHaveAttribute("href", /\/docs\/examples\/sdc-playground\/$/);

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
