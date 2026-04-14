import { test, expect } from "@playwright/test";

test("Verify SMART on FHIR Cerner Launch", async ({ page }) => {
  console.log("Starting Cerner Launch Verification...");
  await page.goto("/");
  
  // Wait for loading overlay to hide
  await expect(page.locator(".loading-overlay")).toBeHidden({ timeout: 30000 });

  // Navigate to SMART tab
  await page.click("button.tab-btn:has-text('SMART on FHIR')");
  
  // Select Cerner Sandbox
  await page.selectOption("#provider-select", "cerner-sandbox");
  
  // Connect
  console.log("Clicking Connect to Cerner...");
  const connectBtn = page.locator("button:has-text('Connect to Cerner')");
  await expect(connectBtn).toBeVisible({ timeout: 15000 });
  await connectBtn.click();
  
  // Verify redirect to Cerner portal
  console.log("Waiting for Cerner portal redirect...");
  // EHR site might be slow
  await page.waitForURL(/cernerhealth.com/i, { timeout: 60000 });
  
  // Check for common Cerner login elements or branding
  console.log("On Cerner page, checking for login form or branding...");
  const loginForm = page.locator('input[type="email"], input[name="username"], button:has-text("Sign In")');
  await expect(loginForm.first()).toBeVisible({ timeout: 30000 });
  
  console.log("Success: Reached Cerner Patient Portal!");
});
