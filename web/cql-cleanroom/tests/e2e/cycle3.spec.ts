import { test } from "@playwright/test";

/**
 * C2-U3 e2e: EvidencePane Compare mode + share-link round-trip.
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}


async function setMaleLibrary(page: import("@playwright/test").Page) {
  // Monaco doesn't honor fill() on its textarea — focus, select all, type.
  await page.click("[data-testid=cql-editor]");
  await page.keyboard.press("Control+Home");
  await page.keyboard.press("Control+Shift+End");
  await page.keyboard.insertText('library CleanroomDemo version \'1.0.0\'\nusing FHIR version \'4.0.1\'\ninclude FHIRHelpers version \'4.0.1\' called FHIRHelpers\n\ndefine "Initial Population":\n  exists([Patient] P where P.gender = \'male\')\n\ndefine "Has Name":\n  exists([Patient] P where P.name.first().given.first() is not null)\n');
  // Debounced parse
  await page.waitForTimeout(1200);
}

test.describe("cleanroom cycle-3 capabilities", () => {
  test("run-history compare shows a moved delta", async ({ page }) => {
    await bootReady(page);
    await page.click('[data-testid=workspace-reset]');
    await page.waitForTimeout(600);

    // 1. load dataset + ensure the Evidence drawer is open (starts
    //    open; only click when the <details> is actually closed).
    await page.click('[data-testid=load-dataset]');
    await page.waitForSelector('[data-testid=dataset-loaded]', { timeout: 30_000 });
    const evOpen = await page.evaluate(
      () =>
        (document.querySelector(
          "[data-testid=drawer-evidence] details",
        ) as HTMLDetailsElement | null)?.open ?? false,
    );
    if (!evOpen) {
      await page.click('[data-testid=drawer-evidence-toggle]');
    }

    await page.click('[data-testid=run-eval]');
    await page.waitForSelector('[data-testid=results-table]', { timeout: 60_000 });
    await page.waitForFunction(
      () =>
        document.querySelectorAll(
          '[data-testid=compare-select] option[value]:not([value=""])',
        ).length >= 1,
      undefined,
      { timeout: 30_000 },
    );

    // 2. change the logic: female-only → male-only flips p1/p2 IPP
    await setMaleLibrary(page);

    // 3. evaluate again — the new current differs from the saved run
    await page.click('[data-testid=run-eval]');
    await page.waitForFunction(
      () =>
        document.querySelectorAll(
          '[data-testid=compare-select] option[value]:not([value=""])',
        ).length >= 2,
      undefined,
      { timeout: 60_000 },
    );

    // 4. compare current vs the first saved run (list is
    //    newest-first; the female baseline is the LAST option)
    const runCount = await page
      .locator('[data-testid=compare-select] option')
      .count();
    await page.selectOption('[data-testid=compare-select]', {
      index: runCount - 1,
    });
    await page.click('[data-testid=compare-run]');
    await page.waitForSelector('[data-testid=compare-delta]', { timeout: 30_000 });

    const rows = await page.locator('[data-testid=compare-row]').allTextContents();
    console.log("COMPARE_ROWS:", JSON.stringify(rows));
    // p1/p2 initial_population must appear as moved deltas
    const moved = rows.filter((r) => r.includes("initial_population") && r.includes("moved"));
    if (moved.length === 0) throw new Error(`no moved rows: ${JSON.stringify(rows)}`);

    // reset so later tests start clean
    await page.click('[data-testid=workspace-reset]');
    await page.waitForTimeout(400);
  });

  test("share link round-trips libraries", async ({ page }) => {
    await bootReady(page);

    // open a new tab with a distinctive name via the editor
    await page.click('[data-testid=library-tab-add]');
    await page.waitForSelector('[data-testid=library-tab-1]', { timeout: 10_000 });

    // click Share — writes the fragment
    await page.click('[data-testid=share-btn]');
    await page.waitForTimeout(300);
    const hash = await page.evaluate(() => location.hash);
    console.log("SHARE_HASH_LEN:", hash.length, "PREFIX_OK:", hash.startsWith("#s="));

    // hard reload: fragment must restore BOTH tabs
    await page.reload();
    await page.waitForSelector('.version-badge', { timeout: 150_000 });
    await page.waitForSelector('[data-testid=library-tab-1]', { timeout: 30_000 });
    const tabCount = await page.locator('[data-testid^=library-tab-]').count();
    console.log("SHARE_RESTORE_TABS:", tabCount);

    // reset so later tests start clean
    await page.click('[data-testid=workspace-reset]');
    await page.waitForTimeout(400);
  });
});
