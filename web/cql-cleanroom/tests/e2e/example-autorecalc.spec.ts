import { expect, test } from "@playwright/test";

/**
 * CMS69 include tabs + Measurement Period default + auto-recalc.
 */
test("example loads include tabs, prefills MP, auto-recalcs", async ({ page }) => {
  test.setTimeout(300_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));
  await page.click("[data-testid=workspace-reset]");

  // 1. Load the example.
  await page.click("[data-testid=import-menu]");
  await page.click("[data-testid=load-example-cms69]");
  await page.waitForFunction(
    () => document.querySelector(".status-note")?.textContent?.includes("loaded example"),
    undefined,
    { timeout: 120_000 },
  );

  // 2. Include tabs are present: main + Hospice/Palliative/QICoreCommon/SDE.
  await page.waitForSelector("[data-testid=library-tab-1]", { timeout: 30_000 });
  const tabCount = await page.locator("[data-testid^=library-tab-]").count();
  if (tabCount < 5) throw new Error(`expected ≥5 tabs (main+4 includes), got ${tabCount - 1}`);
  await page.click("[data-testid=library-tab-1]");
  await page.waitForTimeout(600);
  const incText = await page.evaluate(() => {
    // Editor content via the model, not DOM (line numbers pollute textContent).
    const lines = [...document.querySelectorAll(".view-lines .view-line")].map(
      (l) => l.textContent ?? "",
    );
    return lines.slice(0, 3).join(" ");
  });
  if (!/library\s*(H|P|Q|S)/.test(incText.replace(/\u00a0/g, " "))) {
    throw new Error(`include tab content: ${incText}`);
  }

  // 3. Measurement Period prefilled → single Evaluate arms auto mode.
  await page.click("[data-testid=drawer-parameters-toggle]");
  const mp = await page.locator('[data-testid="param-input-Measurement Period"]').inputValue();
  if (!mp.includes("2026-01-01")) throw new Error(`MP prefill: ${mp}`);
  // Wait for the CMS69 result specifically (the default demo's 3-row
  // table may still be showing; the pager must read "of 62").
  await page.waitForFunction(
    () =>
      (document
        .querySelector("[data-testid=results-table-pager]")
        ?.textContent ?? ""
      ).includes("of 62"),
    undefined,
    { timeout: 180_000 },
  );
  const rows1 = await page.locator("[data-testid=results-table] tbody tr").count();
  if (rows1 !== 10) throw new Error(`expected 10 rows on page 1, got ${rows1}`);
  const pager = await page.textContent("[data-testid=results-table-pager]");
  if (!pager?.includes("of 62")) throw new Error(`pager: ${pager}`);

  // 4. AUTO-RECALC: clear the MP → diagnostics appear; refill it →
  //    results return WITHOUT clicking Evaluate.
  await page.fill('[data-testid="param-input-Measurement Period"]', "");
  await page.waitForSelector("[data-testid=eval-diags]", { timeout: 120_000 });

  await page.fill(
    '[data-testid="param-input-Measurement Period"]',
    "2026-01-01T00:00:00.0..2026-12-31T23:59:59.999",
  );
  await page.waitForSelector("[data-testid=results-table]", { timeout: 120_000 });
  await page.waitForFunction(
    () => document.querySelectorAll("[data-testid=results-table] tbody tr").length === 10,
    undefined,
    { timeout: 120_000 },
  );
  expect(true).toBe(true);
});
