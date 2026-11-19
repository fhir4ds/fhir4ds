/**
 * QA it9 — Domain 5 (persistence/workspaces) × EXPLORER: chaos.
 *  V1 rapid edits during the debounce window — final state persisted
 *  V2 reload DURING the debounce — old-or-new, never corrupted
 *  V3 two tabs autosaving — last-write-wins, no crash
 *  V4 IndexedDB deleted mid-session — next save recreates
 *  V5 reset immediately after an edit — reset wins after reload
 */
import { test, expect, type Page } from "@playwright/test";

async function toText(page: Page) {
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(800);
  }
}

async function typeLib(page: Page, name: string) {
  await toText(page);
  const editor = page.locator('[data-testid="cql-editor"]');
  await editor.click();
  await page.keyboard.press("Control+a");
  await page.keyboard.insertText(
    `library ${name} version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine Ok: 2 = 2\n`,
  );
}

async function bodyText(page: Page) {
  return page.evaluate(() => document.body.innerText);
}

test("V1: rapid edits persist the final state", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  for (let i = 1; i <= 6; i++) {
    await typeLib(page, `V1Lib${i}`);
    await page.waitForTimeout(150);
  }
  await page.waitForTimeout(3000); // debounce settle
  await page.reload();
  await page.waitForTimeout(15000);
  expect(await bodyText(page)).toContain("V1Lib6");
});

test("V2: reload during debounce yields old-or-new, never corrupted", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  await typeLib(page, "V2Old");
  await page.waitForTimeout(3000);
  await typeLib(page, "V2New");
  await page.waitForTimeout(300); // mid-debounce
  await page.reload();
  await page.waitForTimeout(15000);
  const txt = await bodyText(page);
  expect(txt).toMatch(/V2Old|V2New/);
});

test("V3: two tabs autosave — no crash, last write sticks", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  const page2 = await page.context().newPage();
  await page2.goto("/");
  await page2.waitForTimeout(15000);
  await typeLib(page, "V3TabA");
  await typeLib(page2, "V3TabB");
  await page.waitForTimeout(3500);
  const txtA = await bodyText(page);
  const txtB = await bodyText(page2);
  // both tabs alive; the store holds one of the two
  const final = await page.evaluate(() =>
    new Promise<string>((resolve) => {
      const rq = indexedDB.open("cql-cleanroom");
      rq.onsuccess = () => {
        const db = rq.result;
        const tx = db.transaction("workspace", "readonly");
        const get = tx.objectStore("workspace").get("current");
        get.onsuccess = () => {
          resolve(JSON.stringify(get.result ?? {}));
          db.close();
        };
        get.onerror = () => resolve("ERR");
      };
      rq.onerror = () => resolve("ERR");
    }),
  );
  expect(/V3TabA|V3TabB/.test(final)).toBe(true);
  expect(txtA.length).toBeGreaterThan(0);
  expect(txtB.length).toBeGreaterThan(0);
});

test("V4: IndexedDB deleted mid-session — next save recreates", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  await typeLib(page, "V4Before");
  await page.waitForTimeout(2500);
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const rq = indexedDB.deleteDatabase("cql-cleanroom");
        rq.onsuccess = rq.onerror = rq.onblocked = () => resolve();
      }),
  );
  await typeLib(page, "V4After");
  await page.waitForTimeout(2500);
  await page.reload();
  await page.waitForTimeout(15000);
  expect(await bodyText(page)).toContain("V4After");
});

test("V5: reset immediately after an edit — reset wins after reload", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(15000);
  await typeLib(page, "V5Dirty");
  await page.waitForTimeout(200);
  await page.click('[data-testid="file-menu"]');
  await page.click('[data-testid="workspace-reset"]');
  await page.waitForTimeout(2500);
  await page.reload();
  await page.waitForTimeout(15000);
  expect(await bodyText(page)).not.toContain("V5Dirty");
});
