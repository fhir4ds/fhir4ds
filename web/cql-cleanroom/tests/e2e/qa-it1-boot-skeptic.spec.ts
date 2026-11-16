/**
 * it1 SKEPTIC — Domain 1: Boot & Engine Lifecycle.
 *
 * Findings so far (see campaign issue list):
 *  - DEFECT D1 (FIXED here): worker-chunk load failure hung the boot overlay
 *    on "Loading engine…" forever — module workers that fail to LOAD never
 *    postMessage, so the boot protocol's error path was unreachable.
 *    Fix: Worker.onerror dispatches a synthetic boot-fail message.
 *  - FINDING F1 (logged): blocked IndexedDB boots fine but persistence
 *    degrades silently — no storage notice. Owned by Domain 5.
 *
 * S31 doctrine: boot is LAZY. Every hypothesis triggers the engine via the
 * window.__cleanroomReady() e2e bridge; the user-visible contract is the
 * body text (boot overlay states), not internal promises.
 */
import { test, expect, type Page } from "@playwright/test";

test.setTimeout(180_000);

/**
 * Chromium shares the disk cache across contexts in one browser: a worker
 * chunk cached by an earlier test bypasses page.route interception (it1
 * lesson). Boot-failure tests must start from a cold cache.
 */
async function coldCache(page: Page) {
  try {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Network.clearBrowserCache");
  } catch {
    /* CDP unavailable (e.g. firefox) — acceptable; chrome is primary */
  }
}

const BOOT_FAIL = /boot fail|engine boot|failed|worker failed/i;

async function triggerBoot(page: Page) {
  await page.waitForLoadState("domcontentloaded");
  await page
    .evaluate(() => {
      const w = window as unknown as { __cleanroomReady?: () => Promise<boolean> };
      void w.__cleanroomReady?.().catch(() => undefined);
    })
    .catch(() => undefined);
}

test("H1 wheel 404 surfaces actionable error", async ({ page }) => {
  await coldCache(page);
  await page.route(/fhir4ds_v2-.*\.whl/, r => r.abort("failed"));
  await page.goto("/");
  await triggerBoot(page);
  await expect
    .poll(() => page.evaluate(() => document.body.innerText), { timeout: 90_000 })
    .toMatch(BOOT_FAIL);
});

test("H2 worker chunk 404 surfaces actionable error", async ({ page }) => {
  // RED->GREEN repro for D1: a module worker whose chunk fails to load never
  // posts a boot message; the onerror wiring must surface it.
  await coldCache(page);
  await page.route(/cleanroom\.worker-.*\.js/, r => r.abort("failed"));
  await page.goto("/");
  await triggerBoot(page);
  await expect
    .poll(() => page.evaluate(() => document.body.innerText), { timeout: 30_000 })
    .toMatch(/engine worker failed to load|boot fail/i);
  // the misleading eternal "Loading engine…" state must be gone
  const txt = await page.evaluate(() => document.body.innerText);
  expect(txt).not.toMatch(/Loading engine…[\s\S]*First boot downloads/);
});

test("H2b early worker failure (before overlay subscribes) still surfaces", async ({ page }) => {
  // D1 second face: the worker can fail during the server-detect window,
  // BEFORE the overlay mounts. The cached boot result must replay so the
  // overlay still reaches the error state instead of hanging.
  await coldCache(page);
  await page.route(/cleanroom\.worker-.*\.js/, r => r.abort("failed"));
  await page.goto("/");
  // trigger the boot IMMEDIATELY — before server detection resolves
  await page.evaluate(() => {
    const w = window as any;
    void w.__cleanroomReady?.().catch(() => undefined);
  }).catch(() => undefined);
  await expect
    .poll(() => page.evaluate(() => document.body.innerText), { timeout: 45_000 })
    .toMatch(/engine worker failed to load|boot fail/i);
});

test("H3 no-COI page gives SharedArrayBuffer guidance", async ({ page }) => {
  // The coi-serviceworker may RELOAD the page when isolation is missing —
  // wait out any navigation, then require either isolation guidance or a
  // successful boot (SW fixed it).
  await page.addInitScript(() => {
    Object.defineProperty(window, "crossOriginIsolated", { get: () => false });
  });
  await page.goto("/");
  await triggerBoot(page).catch(() => undefined);
  let outcome = "";
  for (let i = 0; i < 18 && !outcome; i++) {
    await page.waitForTimeout(5000);
    const txt = await page.evaluate(() => document.body.innerText).catch(() => "");
    if (/cross-origin|SharedArrayBuffer|isolat/i.test(txt)) outcome = "guidance";
    else if (/\d+\.\d+\.\d+/.test(txt)) outcome = "booted";
  }
  expect(["guidance", "booted"]).toContain(outcome);
});

test("H4 refresh mid-boot recovers", async ({ page }) => {
  await coldCache(page);
  await page.goto("/");
  await triggerBoot(page);
  // wait for boot overlay (boot started) then reload mid-boot
  await page.waitForSelector("[data-testid=boot-step]", { timeout: 15_000 }).catch(() => {});
  await page.reload();
  await triggerBoot(page);
  await expect
    .poll(() => page.evaluate(() => document.body.innerText), { timeout: 120_000 })
    .not.toMatch(BOOT_FAIL);
  await expect(page.locator(".version-badge")).toContainText(/\d+\.\d+\.\d+/, {
    timeout: 30_000,
  });
});

test("H5 blocked IndexedDB still boots", async ({ page }) => {
  await page.addInitScript(() => {
    // Simulate storage-unavailable environments (some private modes).
    Object.defineProperty(window, "indexedDB", {
      get: () => {
        throw new DOMException("blocked");
      },
    });
  });
  await page.goto("/");
  await triggerBoot(page);
  await expect
    .poll(() => page.evaluate(() => document.body.innerText), { timeout: 120_000 })
    .not.toMatch(BOOT_FAIL);
  // FINDING F1 (logged for Domain 5): boot succeeds with IndexedDB
  // unavailable but NO storage notice is surfaced.
  const body = await page.evaluate(() => document.body.innerText);
  console.log(
    "H5 storage-notice present:",
    /storage|persist|IndexedDB/i.test(body),
  );
});
