import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S30: nav version pills replace the "on disk" chip; connected workspaces
// list DISK ViewDefinitions only (no duplicate derived "View 1"); loading
// states are the shared spinner (not bare text).
const BASE = "http://127.0.0.1:19240";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", "/mnt/d/fhir4ds/examples/cms125-workspace", "--port", "19240", "--no-open"],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {
      /* wait */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
    } catch {
      /* gone */
    }
  }
});

async function boot(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(16000);
}

test("S30-1: version pills on disk rows; no 'on disk' chip", async ({ page }) => {
  await boot(page);
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const libRow = libPanel
    .locator(".nav-item", { hasText: "CMS125FHIRBreastCancerScreening" })
    .first();
  await expect(libRow).toBeVisible({ timeout: 20000 });
  // CQL header version '0.4.000' is the library pill.
  await expect(libRow.locator(".nav-item-pill")).toHaveText(/0\.4\.000/);
  await expect(page.getByText("on disk", { exact: true })).toHaveCount(0);

  // ValueSet rows carry the ValueSet.version (e.g. 20210820).
  await page.locator('[data-testid="nav-toggle-valuesets"]').click();
  const vsRow = page
    .locator('[data-testid="nav-panel"], .nav-panel')
    .first()
    .locator(".nav-item", { hasText: "OfficeVisit" })
    .first();
  await expect(vsRow).toBeVisible({ timeout: 20000 });
  await expect(vsRow.locator(".nav-item-pill")).toHaveText(/20180310/);
});

test("S30-2: connected Views list disk ViewDefinitions only (no 'View 1')", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-views"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(
    panel.locator(".nav-item", { hasText: "MeasureReportPopulations" }).first(),
  ).toBeVisible({ timeout: 20000 });
  await expect(panel.locator(".nav-item", { hasText: "View 1" })).toHaveCount(0);
});

test("S30-3: loading states use the shared spinner, not text", async ({ page }) => {
  // Delay the SERVER explain call so the evidence popover's loading state
  // is observable deterministically (the view flatten runs in-browser).
  await page.route("**/api/explain", async (route) => {
    await new Promise((r) => setTimeout(r, 4000));
    await route.continue();
  });
  await boot(page);
  // Cells view auto-opens and is console-free — switch to Text so the
  // Results console (and its population cells) exist.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
  }
  // The heartbeat rendered the population table; click one population cell.
  const cell = page.locator('[data-testid^="cell-"][title^="why:"]').first();
  await expect(cell).toBeVisible({ timeout: 60000 });
  await cell.click();
  const loading = page.locator('[data-testid="evidence-loading"]');
  await expect(loading).toBeVisible({ timeout: 20000 });
  // The loading state IS the shared spinner (no "explaining…" text).
  await expect(loading.locator('[data-testid="spinner"]')).toBeVisible();
  expect((await loading.textContent())?.trim() ?? "").toBe("");
});
