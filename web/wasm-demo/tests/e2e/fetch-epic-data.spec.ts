import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

test("Fetch fhircamila data from Epic", async ({ page }) => {
  const clientId = process.env.EPIC_NON_PROD_CLIENT_ID;
  const username = process.env.EPIC_NON_PROD_TEST_USER1_USERNAME;
  const password = process.env.EPIC_NON_PROD_TEST_USER1_PASS;

  if (!clientId || !username || !password) {
    console.error("Missing Epic credentials");
    return;
  }

  await page.goto("/");
  await page.click("button.tab-btn:has-text('SMART on FHIR')");
  await page.selectOption("#provider-select", "epic-sandbox");
  await page.fill("#client-id", clientId);
  await page.click("button:has-text('Connect to Epic')");

  await page.waitForURL(/fhir.epic.com/i, { timeout: 60000 });
  await page.getByLabel(/MyChart Username/i).fill(username);
  await page.locator('input[id="Password"]').fill(password);
  await page.locator('input[id="submit"]').click();

  // Handling Epic Post-Login Screens
  for (let i = 0; i < 6; i++) {
    try {
      await page.waitForTimeout(3000);
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      const allowAccessBtn = page.getByRole('button', { name: /Allow access/i });
      if (await allowAccessBtn.isVisible({ timeout: 5000 })) {
        await allowAccessBtn.click({ force: true });
        await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      } else {
        await page.evaluate(() => {
          const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]'));
          const target = buttons.find(b => {
            const txt = (b.textContent || (b as HTMLInputElement).value || "").toLowerCase();
            return (txt.includes("continue") || txt.includes("allow") || txt.includes("authorize") || txt.includes("connect"))
                   && !txt.includes("deny") && !txt.includes("cancel");
          });
          if (target) (target as HTMLElement).click();
        });
      }
      if (page.url().includes("localhost:5173") && page.url().includes("code=")) break;
    } catch (e) {}
  }

  await page.waitForURL(/localhost:5173/i, { timeout: 90000 });
  await page.click("button.tab-btn:has-text('SMART on FHIR')");
  
  // Wait for data load - the stat card for resources loaded should eventually be > 0
  const resourceCountLocator = page.locator(".smart-stat-value").first();
  await expect(resourceCountLocator).not.toHaveText("0", { timeout: 60000 });

  // Extract from DuckDB
  const resources = await page.evaluate(async () => {
    const conn = (window as any).duckdbConn;
    if (!conn) return "NO_CONN";
    const res = await conn.query("SELECT resource FROM resources");
    // DuckDB-WASM query returns a Table object (Apache Arrow)
    return res.toArray().map((row: any) => JSON.parse(row.resource));
  });

  if (Array.isArray(resources)) {
    console.log(`Successfully fetched ${resources.length} resources`);
    fs.writeFileSync("fhircamila_data.json", JSON.stringify(resources, null, 2));
  } else {
    console.error("Failed to fetch resources:", resources);
  }
});
