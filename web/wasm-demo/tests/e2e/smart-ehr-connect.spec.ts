import { test, expect } from "@playwright/test";

const INIT_TIMEOUT = 120_000;

test.describe("SMART on FHIR E2E Connect", () => {
  test("Connect to Epic Sandbox and Authorize", async ({ page }) => {
    const clientId = process.env.EPIC_NON_PROD_CLIENT_ID;
    const username = process.env.EPIC_NON_PROD_TEST_USER1_USERNAME;
    const password = process.env.EPIC_NON_PROD_TEST_USER1_PASS;

    if (!clientId || !username || !password) {
      test.skip(true, "Epic credentials missing in .env");
      return;
    }

    console.log("Starting Epic E2E test on port 5173...");
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: INIT_TIMEOUT });

    await page.click("button.tab-btn:has-text('SMART on FHIR')");
    await page.selectOption("#provider-select", "epic-sandbox");
    await page.fill("#client-id", clientId);

    console.log("Clicking Connect to Epic...");
    await page.click("button:has-text('Connect to Epic')");

    // Wait for Epic login redirect
    console.log("Waiting for Epic login page...");
    await page.waitForURL(/fhir.epic.com/i, { timeout: 60_000 });

    console.log("Entering Epic credentials...");
    await page.getByLabel(/MyChart Username/i).fill(username);
    await page.locator('input[id="Password"]').fill(password);
    await page.locator('input[id="submit"]').click();

    console.log("Handling Epic Post-Login Screens (Patient/Scopes/Privacy)...");
    
    // Aggressive interaction loop to find and click the 'Allow' or 'Continue' buttons
    for (let i = 0; i < 6; i++) {
        try {
            await page.waitForTimeout(3000);
            
            // Scroll to bottom
            await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            
            // Try specific "Allow access" button from screenshot
            const allowAccessBtn = page.getByRole('button', { name: /Allow access/i });
            if (await allowAccessBtn.isVisible({ timeout: 5000 })) {
                console.log("Found 'Allow access' button, clicking...");
                await allowAccessBtn.click({ force: true });
                await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
            } else {
                // Fallback to generic click
                const clicked = await page.evaluate(() => {
                    const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], .button.positive'));
                    const target = buttons.find(b => {
                        const txt = (b.textContent || (b as HTMLInputElement).value || "").toLowerCase();
                        return (txt.includes("continue") || txt.includes("allow") || txt.includes("authorize") || txt.includes("connect"))
                               && !txt.includes("deny") && !txt.includes("cancel");
                    });
                    if (target) {
                        (target as HTMLElement).click();
                        return true;
                    }
                    return false;
                });
                if (clicked) {
                    console.log(`Generic button click in attempt ${i+1}`);
                    await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
                }
            }
            
            // Check if we already redirected back
            if (page.url().includes("localhost:5173") && page.url().includes("code=")) break;
        } catch (e) {
            // Ignore errors in loop
        }
    }

    // Should redirect back to http://localhost:5173/ with code/state
    console.log("Waiting for redirect back to app (localhost:5173)...");
    await page.waitForURL(/localhost:5173/i, { timeout: 90_000 });

    // The app should automatically process the callback and connect
    await page.click("button.tab-btn:has-text('SMART on FHIR')");
    
    console.log("Waiting for .smart-connected UI...");
    await expect(page.locator(".smart-connected")).toBeVisible({ timeout: 60_000 });
    
    // Verify resources were actually loaded (> 0)
    const resourceCountLocator = page.locator(".smart-stat-value").first();
    await expect(resourceCountLocator).not.toHaveText("0", { timeout: 45000 });
    const finalCount = await resourceCountLocator.textContent();
    console.log(`Epic Connection Successful! Loaded ${finalCount} resources.`);
  });

  // CERNER Sandbox Test
  test("Connect to Cerner Sandbox and Authorize", async ({ page }) => {
    // New Client ID provided by user
    const clientId = "22c22bb4-76e9-4509-be6f-227d9de74358";
    const username = process.env.CERNER_TEST_USER1_USERNAME;
    const password = process.env.CERNER_TEST_USER1_PASS;

    if (!username || !password) {
      test.skip(true, "Cerner credentials missing in .env");
      return;
    }

    console.log("Starting Cerner E2E test on port 5173...");
    await page.goto("/");
    await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: INIT_TIMEOUT });

    await page.click("button.tab-btn:has-text('SMART on FHIR')");
    await page.selectOption("#provider-select", "cerner-sandbox");
    await page.fill("#client-id", clientId);
    
    await page.click("button:has-text('Connect to Cerner')");

    console.log("Waiting for Cerner Login page...");
    await page.waitForURL(/cernerhealth.com\/oauth\/authenticate/i, { timeout: 60_000 });
    
    console.log("Entering Cerner credentials...");
    await page.getByLabel(/Email address or username/i).fill(username);
    await page.getByLabel(/Password/i).fill(password);
    await page.click("button:has-text('Sign In')");

    console.log("Handling Cerner Warning/Authorization...");
    
    // Aggressive interaction loop for Cerner
    for (let i = 0; i < 5; i++) {
        try {
            await page.waitForTimeout(3000);
            
            const clicked = await page.evaluate(() => {
                const linksAndButtons = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
                const target = linksAndButtons.find(b => {
                    const txt = (b.textContent || (b as HTMLInputElement).value || "").toLowerCase();
                    return (txt.includes("proceed anyway") || txt.includes("allow") || txt.includes("authorize") || txt.includes("next"));
                });
                if (target) {
                    (target as HTMLElement).click();
                    return true;
                }
                return false;
            });
            
            if (clicked) {
                console.log(`Aggressively clicked button in attempt ${i+1}`);
                await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
            }
            
            if (page.url().includes("localhost:5173") && page.url().includes("code=")) break;
        } catch (e) {
            // Ignore
        }
    }

    // Since we're not dealing with 5174 redirects for Cerner anymore, it should go directly to 5173
    console.log("Waiting for redirect back to app (localhost:5173)...");
    await page.waitForURL(/localhost:5173/i, { timeout: 90_000 });
    
    await page.click("button.tab-btn:has-text('SMART on FHIR')");
    
    console.log("Waiting for .smart-connected UI...");
    await expect(page.locator(".smart-connected")).toBeVisible({ timeout: 60_000 });
    
    // Verify resources were actually loaded (> 0)
    const resourceCountLocator = page.locator(".smart-stat-value").first();
    await expect(resourceCountLocator).not.toHaveText("0", { timeout: 45000 });
    const finalCount = await resourceCountLocator.textContent();
    console.log(`Cerner Connection Successful! Loaded ${finalCount} resources.`);
  });
});
