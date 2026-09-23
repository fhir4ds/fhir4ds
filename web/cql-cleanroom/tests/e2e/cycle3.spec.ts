import { test } from "@playwright/test";

/**
 * C2-U3 e2e: EvidencePane Compare mode + share-link round-trip.
 */

async function bootReady(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
}

test.describe("cleanroom cycle-3 capabilities", () => {
  test("compare mode shows a moved delta", async ({ page }) => {
    await bootReady(page);

    // 1. load dataset + explain p1 (fills the "current" evidence)
    await page.click('[data-testid=load-dataset]');
    await page.waitForSelector('[data-testid=dataset-loaded]', { timeout: 30_000 });

    await page.fill('[data-testid=evidence-patient-input]', 'p1');
    await page.click('[data-testid=explain-btn]');
    await page.waitForSelector('[data-testid^=ev-pop-]', { timeout: 30_000 });

    // 2. paste a baseline that differs on IPP: p1 was true → moved to false
    await page.fill(
      '[data-testid=compare-baseline]',
      JSON.stringify({ patients: { p1: { populations: { IPP: false, NAME: true } } } }),
    );
    await page.click('[data-testid=compare-run]');
    await page.waitForSelector('[data-testid=compare-delta]', { timeout: 30_000 });

    const changed = await page.textContent('[data-testid=compare-changed]');
    console.log("COMPARE_BADGE:", (changed ?? "").trim());
    const rows = await page.locator('[data-testid=compare-row]').allTextContents();
    console.log("COMPARE_ROWS:", JSON.stringify(rows));
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
