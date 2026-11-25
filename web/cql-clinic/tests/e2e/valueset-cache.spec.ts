import { test, expect } from "@playwright/test";

/**
 * FHIR4-49 — ValueSet cache loud fallback in CQL Clinic.
 *
 * Lessons are editable and auto-run, so a learner can add a `valueset` retrieve
 * at any time. The engine answers membership from its in-process C++ cache; an
 * unseeded ValueSet makes every row disappear with no error at all. These tests
 * pin that the page says so, and that a lesson WITHOUT valuesets stays quiet.
 *
 * (CQL Clinic ships no ValueSet resources today, so the seeding path is a no-op
 * here — the shared bridge still seeds whatever a lesson bundle carries.)
 */

const VALUESET_CQL = `library ValuesetProbe version '1.0.0'

using FHIR version '4.0.1'

context Patient

valueset "Not Loaded": 'http://example.org/ValueSet/cql-clinic-probe'

define "Matches":
  Count([Condition: "Not Loaded"])
`;

const MISSING_VALUESET_URL = "http://example.org/ValueSet/cql-clinic-probe";

test.describe("ValueSet cache (FHIR4-49)", () => {
  test("lesson without valuesets shows no cache warning", async ({ page }) => {
    await page.goto("/");
    await page.locator(".lesson-card", { hasText: "Terminology" }).first().click();

    await expect(page.locator(".runtime-status.ok")).toBeVisible({
      timeout: 120_000,
    });
    // Wait for a COMPLETED run (timing summary renders only after execute) so
    // "no warning" is a real assertion, not a race with the auto-run.
    await expect(page.locator(".results-footer__timings")).toBeVisible({
      timeout: 180_000,
    });
    await expect(page.getByTestId("valueset-cache-warning")).toHaveCount(0);
  });

  test("edited lesson using an unloaded ValueSet is called out loudly", async ({
    page,
  }) => {
    // lastCql is persisted per lesson; seeding it makes the editor start from
    // our probe instead of racing a Monaco keystroke helper.
    await page.addInitScript((cql) => {
      localStorage.setItem(
        "cql-clinic-progress",
        JSON.stringify({
          terminology: { completed: false, lastCql: cql, timestamp: 1 },
        }),
      );
    }, VALUESET_CQL);

    await page.goto("/");
    await page.locator(".lesson-card", { hasText: "Terminology" }).first().click();

    const warning = page.getByTestId("valueset-cache-warning");
    await expect(warning).toBeVisible({ timeout: 180_000 });
    await expect(warning).toContainText(MISSING_VALUESET_URL);
    await expect(warning).toContainText("not loaded");
  });
});
