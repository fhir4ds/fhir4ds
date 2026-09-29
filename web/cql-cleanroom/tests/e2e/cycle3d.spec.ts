import { expect, test } from "@playwright/test";

/**
 * Visual editor 5 e2e: the drawer builder round-trips a define —
 * text→form (Initial Population parses into structured predicates)
 * and form→text (a new HEDIS-style define applies back into the
 * library after a parse guard).
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  await page.waitForSelector("[data-testid=cql-editor] .monaco-editor");
}

test("builder parses the population define into structured predicates", async ({
  page,
}) => {
  await bootReady(page);
  await page.click("[data-testid=drawer-graph-toggle]");
  await page.waitForSelector("[data-testid=builder-pane]");
  await page.selectOption("[data-testid=builder-define-select]", "Initial Population");
  await expect(page.locator("[data-testid=builder-type]")).toHaveValue("Patient");
  await expect(page.locator("[data-testid=builder-alias]")).toHaveValue("P");
  await expect(page.locator("[data-testid=builder-cond-path]").first()).toHaveValue(
    "P.gender",
  );
  await expect(page.locator("[data-testid=builder-cond-op]").first()).toHaveValue("=");
  await expect(page.locator("[data-testid=builder-cond-value]").first()).toHaveValue(
    "female",
  );
  await expect(page.locator("[data-testid=builder-preview]")).toContainText(
    "exists([Patient] P where P.gender = 'female')",
  );
});

test("builder: new expression applies into the library and parses", async ({
  page,
}) => {
  await bootReady(page);
  await page.click("[data-testid=drawer-graph-toggle]");
  await page.waitForSelector("[data-testid=builder-pane]");
  await page.selectOption("[data-testid=builder-define-select]", "__new__");
  await page.fill("[data-testid=builder-name]", "Builder Check");
  await page.fill("[data-testid=builder-cond-path]", "P.gender");
  await page.fill("[data-testid=builder-cond-value]", "female");
  await expect(page.locator("[data-testid=builder-preview]")).toHaveText(
    'define "Builder Check":\n  exists([Patient] P where P.gender = \'female\')',
  );
  await page.click("[data-testid=builder-apply]");
  await expect(page.locator("[data-testid=builder-applied]")).toBeVisible({
    timeout: 30_000,
  });
  // The library text now carries the new statement — the define
  // dropdown derives from the text, so it lists the new expression
  // (Monaco virtualizes off-screen lines, so we can't read them).
  await expect(
    page.locator("[data-testid=builder-define-select] option", {
      hasText: "Builder Check",
    }),
  ).toHaveCount(1, { timeout: 30_000 });
  // …and the editor's parse round-trip confirms it (parsed ✓).
  await expect(page.locator("[data-testid=parse-status]")).toContainText(
    "parsed ✓",
    { timeout: 30_000 },
  );
});
