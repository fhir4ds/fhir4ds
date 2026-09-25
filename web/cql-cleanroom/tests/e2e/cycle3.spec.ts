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
  test("run diff highlights changed cells in the output table", async ({ page }) => {
    await bootReady(page);
    await page.click('[data-testid=workspace-reset]');
    await page.waitForTimeout(600);

    // 1. first evaluation (auto) — female logic; p1 IPP true
    await page.waitForSelector('[data-testid=results-table]', { timeout: 90_000 });
    await page.waitForFunction(
      () =>
        (document.querySelector(
          "[data-testid=results-table] tbody tr td:nth-child(2)",
        )?.textContent ?? "").includes("true"),
      undefined,
      { timeout: 90_000 },
    );

    // 2. change the logic: female-only → male-only flips p1/p2 IPP
    await setMaleLibrary(page);

    // 3. auto re-eval vs prior run: p1 IPP true→false must highlight
    await page.waitForSelector("td.diff-down-cell", { timeout: 90_000 });
    const changed = await page.locator("td.diff-up-cell, td.diff-down-cell").count();
    if (changed < 2) throw new Error(`expected >=2 changed cells, got ${changed}`);

    // 4. footer chips carry the summary
    const chip = await page.textContent("[data-testid=diff-chip-changed]");
    if (!chip?.includes("changed")) throw new Error(`chip: ${chip}`);

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
