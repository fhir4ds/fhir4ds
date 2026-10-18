import { mkdtemp, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S18 checkpoint: toolbar grouping, Enter-grow, evidence seams, File-menu
// MADiE scoping. Runs against the CMS125 example workspace (connected).

const BASE = "http://127.0.0.1:19141";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s18-"));
  server = spawn(
    "/usr/bin/python3",
    [
      "-m", "fhir4ds.cli", "dev",
      "/mnt/d/fhir4ds/examples/cms125-workspace",
      "--port", "19141", "--no-open",
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
  if (dir) await rm(dir, { recursive: true, force: true });
});

async function openCells(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "CMS125Demo" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CMS125/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(4000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1200);
}

test("S18-1: toolbar grouped — actions cluster left, view controls right", async ({ page }) => {
  await openCells(page);
  const header = page.locator(".editor-header");
  await expect(header.locator('[data-testid="cell-runall"]')).toBeVisible();
  // Ordering: Run All (actions) BEFORE the mode switch (view controls);
  // Outline sits AFTER the switch in the view cluster.
  const order = await header.evaluate((el) => {
    const ids = ["cell-runall", "cell-view-toggle", "editor-outline"];
    const buttons = Array.from(el.querySelectorAll("button"));
    return ids.map((id) =>
      buttons.findIndex((b) => b.getAttribute("data-testid") === id),
    );
  });
  expect(order[0]).toBeGreaterThanOrEqual(0);
  expect(order[1]).toBeGreaterThan(order[0]);
  expect(order[2]).toBeGreaterThan(order[1]);
});

test("S18-2: typing Enter in a cell grows its host (auto-fit live)", async ({ page }) => {
  await openCells(page);
  const host = page.locator('[data-testid="cell-monaco"]').first();
  const h0 = await host.evaluate((el) => el.getBoundingClientRect().height);
  await host.click();
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await page.keyboard.type("true", { delay: 5 });
  await page.waitForTimeout(2500);
  const h1 = await host.evaluate((el) => el.getBoundingClientRect().height);
  expect(h1).toBeGreaterThan(h0 + 15);
});

test("S18-3: bottom-console evidence opens (server-run rows, no error)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") { await toggle.click(); await page.waitForTimeout(1500); }
  await page.getByRole("button", { name: /^Run$/ }).click();
  // Wait for a SERVER-dataset row (w01) — the fresh server run.
  await page.locator(".results-table tbody tr td", { hasText: "w01" }).first().waitFor({ state: "visible", timeout: 45000 });
  await page.locator("td.cell-evidence").first().click();
  const pop = page.locator('[data-testid="evidence-popover"]');
  await expect(pop).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="evidence-popover-error"]')).toHaveCount(0);
});

test("S18-4: cell results row-click opens the inline evidence popover", async ({ page }) => {
  await openCells(page);
  await page.locator('[data-testid="cell-run"]').first().click();
  const table = page.locator('[data-testid="cell-table"]').first();
  await expect(table).toBeVisible({ timeout: 60000 });
  await table.locator("tbody tr").first().click();
  const pop = page.locator('[data-testid="evidence-popover"]');
  await expect(pop).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="evidence-popover-error"]')).toHaveCount(0);
});

test("S18-5: File > Open scoped to MADiE — non-MADiE zips get the typed pointer", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  await page.locator('[data-testid="file-menu"]').click();
  await page.waitForTimeout(400);
  await page.locator('[data-testid="file-open"]').hover();
  await page.waitForTimeout(600);
  // Generic import entries are GONE.
  await expect(page.locator('[data-testid="workspace-import"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="bundle-import"]')).toHaveCount(0);
  // MADiE entries present (flyout rendered on hover).
  await expect(page.locator('[data-testid="madie-import"]')).toBeVisible();
  await expect(page.locator('[data-testid="madie-tests-import"]')).toBeVisible();
  // Feed a NON-MADiE zip through the package input -> typed rejection.
  await page.setInputFiles('[data-testid="madie-import-input"]', {
    name: "not-madie.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("PK\x05\x06" + "\x00".repeat(18), "binary"),
  });
  await expect(page.locator('[data-testid="status-note"]')).toContainText(/not a MADiE measure package.*File > Add/i, { timeout: 15000 });
});

test("S18-6: Save exports the MADiE package; Open re-imports it (round-trip)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
  await page.locator('[data-testid="file-menu"]').click();
  await page.waitForTimeout(400);
  await page.locator('[data-testid="file-save"]').hover();
  await page.waitForTimeout(600);
  await page.locator('[data-testid="madie-export"]').click();
  const download = await downloadPromise;
  const path = join(dir!, "s18-roundtrip.zip");
  await download.saveAs(path);
  // The zip contains the MADiE layout + extras.
  // (Node-side check happens post-test via the re-import below.)
  // Re-import via Open.
  await page.locator('[data-testid="file-menu"]').click();
  await page.waitForTimeout(400);
  await page.locator('[data-testid="file-open"]').hover();
  await page.waitForTimeout(600);
  await page.setInputFiles('[data-testid="madie-import-input"]', path);
  await expect(page.locator('[data-testid="status-note"]')).toContainText(/imported measure package/i, { timeout: 30000 });
});
