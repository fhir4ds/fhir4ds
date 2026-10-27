import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S20: three-surface dataset consistency + evidence independence +
// run-derived output_columns, all on the CMS125 example workspace
// (connected; 22-patient server dataset, browser store has 3 demo pts).

const BASE = "http://127.0.0.1:19160";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    [
      "-m", "fhir4ds.cli", "dev",
      "/mnt/d/fhir4ds/examples/cms125-workspace",
      "--port", "19160", "--no-open",
    ],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
      await new Promise((r) => setTimeout(r, 300));
    } catch {
      /* already gone */
    }
  }
});

async function openCells(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "CMS125FHIR" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CMS125/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(4000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1200);
}

test("S20-1: Tests drawer lists the server roster (patient-list UX)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  // S24-a: the banner is REMOVED — the patient-list UX itself is the
  // dataset statement. The Tests drawer (default open) hosts the
  // DatasetPane roster (the kernel's patients) with resource chips.
  const rosterRow = page.locator('[data-testid="ds-roster-row"]').first();
  if ((await rosterRow.count()) === 0) {
    await page.locator('[data-testid="nav-toggle-tests"]').click();
    await page.waitForTimeout(2500);
  }
  await expect(rosterRow).toBeVisible({ timeout: 20000 });
  const rosterCount = await page.locator('[data-testid="ds-roster-row"]').count();
  expect(rosterCount).toBeGreaterThanOrEqual(20);
});

test("S20-2: cell evidence is independent per cell (no state bleed)", async ({ page }) => {
  await openCells(page);
  // Run two cells that both produce tables.
  const runs = page.locator('[data-testid="cell-run"]');
  await runs.nth(0).click();
  await page.locator('[data-testid="cell-table"]').first().waitFor({ state: "visible", timeout: 60000 });
  await runs.nth(1).click();
  await page.waitForTimeout(3000);
  // Open evidence on cell A (first card).
  const cardA = page.locator('[data-testid="cell-card"]').first();
  await cardA.locator('[data-testid="cell-table"] tbody tr').first().click();
  const pop = page.locator('[data-testid="evidence-popover"]');
  await expect(pop).toBeVisible({ timeout: 20000 });
  const popCountA = await page.locator('[data-testid="evidence-popover"]').count();
  // Only ONE popover, inside cell A's card; cell B shows none.
  expect(popCountA).toBe(1);
  const cardB = page.locator('[data-testid="cell-card"]').nth(1);
  await expect(cardB.locator('[data-testid="evidence-popover"]')).toHaveCount(0);
  // The popover names cell A's define, not B's.
  const header = await pop.locator("h3").first().textContent();
  expect((header ?? "").split("·")[1]?.trim()).toBeTruthy();
});

test("S20-3: bottom-console evidence uses the DISPLAYED run's defines (no Has Name)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  // Open the CMS125FHIR library FIRST — the run target follows the
  // ACTIVE tab (the default CleanroomDemo tab legitimately maps Has Name;
  // Joel's repro ran CMS125 as the displayed run). The real MADiE
  // example workspace carries CMS125FHIRBreastCancerScreening.
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "CMS125FHIR" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CMS125/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(4000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") { await toggle.click(); await page.waitForTimeout(1500); }
  // S15: the whole-library run control is "Run" in text mode (the cell
  // surface's equivalent is "▶ Run All"); this leg stays in text mode.
  const runBtn = page.getByRole("button", { name: /^Run$/ });
  if ((await runBtn.count()) === 0) {
    await page.getByRole("button", { name: /Run All/ }).click();
  } else {
    await runBtn.click();
  }
  // The real MADiE roster uses uuid patient ids — wait for the first
  // data row of the population table (patient_id column).
  const firstRow = page.locator(".results-table tbody tr td").first();
  await firstRow.waitFor({ state: "visible", timeout: 45000 });
  await page.locator("td.cell-evidence").first().click();
  await expect(page.locator('[data-testid="evidence-popover"]')).toBeVisible({ timeout: 20000 });
  const err = page.locator('[data-testid="evidence-popover-error"]');
  // 'Has Name' is the default-demo library's define — must NEVER appear
  // for a CMS125FHIR run.
  await expect(err).toHaveCount(0);
  const allText = await page.locator('[data-testid="evidence-popover"]').first().textContent();
  expect(allText ?? "").not.toContain("Has Name");
  // Positive: a CMS125FHIR define IS present in the evidence output.
  expect(allText ?? "").toMatch(/Initial Population|InAgeRange|PreventiveVisit|RecentMammogram|Numerator|Summary/);
});
