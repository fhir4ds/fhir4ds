import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-cleanroom-redo S5: cell-based editor — per-buffer toggle, cell cards
// with dep chips, RunMode control, per-cell inline results. Server-backed
// legs run connected (auto target: cells evaluate via /api/evaluate).

const BASE = "http://127.0.0.1:19104";
let dir: string | null = null;
let server: ChildProcess | null = null;

const CELL_LIB = `library CellLib version '1.0.0'
using FHIR version '4.0.1'
context Patient

// # %% [name: IsAdult]
define IsAdult: AgeInYearsAt(Today()) >= 18

// # %% [name: Label]
define "LabelText": 'ok'

// # %%
define Combined: IsAdult and true
`;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s5-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(join(dir, "cql", "CellLib.cql"), CELL_LIB, "utf8");
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19104", "--no-open"],
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

test("cell mode: markers split into cards with dep info; run produces inline output", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  // The server workspace has CellLib.cql; open it from the Workspace rail
  // (S6 will dissolve this into the type drawers — legs will follow).
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const diskRow = libPanel.locator(".nav-item", { hasText: "CellLib" }).first();
  await diskRow.click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CellLib/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(4000);
  // Toggle the cell view (EditorPane header button appears only when the
  // buffer has markers).
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  await expect(toggle).toBeVisible({ timeout: 15000 });
  await toggle.click();
  // Cards render immediately (the per-buffer toggle IS the view toggle).
  const chip = page.locator('[data-testid="cell-namechip"]', { hasText: "IsAdult" });
  await expect(chip).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-testid="cell-card"]')).toHaveCount(3);
  // The Combined cell (quoted define authored bare) carries dep info.
  const combined = page.locator('[data-testid="cell-namechip"]', { hasText: "Combined" });
  await expect(combined).toHaveAttribute(
    "aria-label",
    /dependencies IsAdult/,
  );
  // Run the Combined cell (server-connected → /api/evaluate per define).
  await page.locator('[data-testid="cell-run"]').nth(2).click();
  const out = page.locator('[data-testid="cell-out"]').first();
  await expect(out).toBeVisible({ timeout: 30000 });
  // Server runs carry NO 'computed locally' badge (connected mode).
  await expect(out.locator(".cell-localbadge")).toHaveCount(0);
});

test("cell mode: runmode control present with the three modes", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const diskRow = libPanel.locator(".nav-item", { hasText: "CellLib" }).first();
  await diskRow.click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CellLib/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(4000);
  await page.locator('[data-testid="cell-view-toggle"]').click();
  const radios = page.locator('[data-testid="cell-runmode"] [role="radio"]');
  await expect(radios).toHaveCount(3);
  await expect(radios.nth(1)).toHaveAttribute("aria-checked", "true"); // default cell_deps
  await radios.nth(0).click();
  await expect(radios.nth(0)).toHaveAttribute("aria-checked", "true");
});
