import { chromium } from "playwright";

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1560, height: 950 } });
page.on("pageerror", (e) => console.log("PAGEERROR:", String(e).slice(0, 300)));

await page.addInitScript(() => { localStorage.clear(); });
await page.goto("http://localhost:5176/", { waitUntil: "domcontentloaded" });
await page.waitForSelector(".version-badge", { timeout: 150_000 });
await page.waitForSelector("[data-testid=cql-editor]", { timeout: 30_000 });
await page.click("[data-testid=file-menu]");
await page.click("[data-testid=workspace-reset]");
await page.waitForTimeout(1200);
await page.waitForSelector("[data-testid=dataset-tree]", { timeout: 30_000 });

await page.click("[data-testid=nav-add-tests]");
await page.waitForSelector("[data-testid=builder-field-id]", { timeout: 15_000 });
await page.fill("[data-testid=builder-field-id]", "probe-rm");
await page.selectOption("[data-testid=builder-add-element]", "gender");
await page.fill("[data-testid=builder-field-gender]", "other");

// Sample BEFORE the auto-save debounce lands (t≈0.5s), then AFTER (t≈4s).
for (const t of [500, 2000, 4000, 6000]) {
  await page.waitForTimeout(t === 500 ? 500 : t - (t === 2000 ? 500 : t === 4000 ? 2000 : 4000));
  const s = await page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    return {
      id: q("[data-testid=builder-field-id]") ? q("[data-testid=builder-field-id]").value : null,
      gender: q("[data-testid=builder-field-gender]") ? q("[data-testid=builder-field-gender]").value : null,
      addSelectPresent: Boolean(q("[data-testid=builder-add-element]")),
    };
  });
  console.log(`t=${t}ms`, JSON.stringify(s));
}

// how many resources did we end with?
const cnt = await page.evaluate(async () => {
  const r = await window.__cleanroom({ type: "get_dataset" }).catch(() => null);
  return r ? JSON.stringify(r).slice(0, 80) : "no-resp";
});
console.log("DATASET:", cnt);
await b.close();
