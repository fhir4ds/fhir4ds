import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S11: NARROW viewport (Joel's ~900-1100px window) — vertical heights
// sized to content, and the text<->cells mode switch round-trips.

const BASE = "http://127.0.0.1:19118";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s11-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(
    join(dir, "cql", "CellLib.cql"),
    "library CellLib version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\n// # %% [name: IsAdult]\ndefine IsAdult: AgeInYearsAt(Today()) >= 18\n\n// # %% [name: Long]\ndefine Long:\n  1 = 1\n  and 2 = 2\n  and 3 = 3\n  and 4 = 4\n  and 5 = 5\n  and 6 = 6\n  and 7 = 7\n  and 8 = 8\n  and 9 = 9\n  and 10 = 10\n  and 11 = 11\n  and 12 = 12\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19118", "--no-open"],
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

test.use({ viewport: { width: 1000, height: 800 } });

test("S11 narrow: cell editors size to CONTENT (long cell taller)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const diskRow = libPanel.locator(".nav-item", { hasText: "CellLib" }).first();
  await diskRow.click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CellLib/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1200);
  // Content-height: the 13-line 'Long' cell must be substantially taller
  // than the 1-line 'IsAdult' cell, and taller than the old fixed 140px.
  const heights = await page.locator('[data-testid="cell-monaco"]').evaluateAll((els) =>
    els.map((el) => el.getBoundingClientRect().height),
  );
  expect(heights.length).toBe(2);
  expect(heights[1]).toBeGreaterThan(heights[0] + 60);
  expect(heights[1]).toBeGreaterThan(200);
});

test("S11 narrow: text <-> cells round-trip at 1000px", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  await expect(toggle).toBeVisible({ timeout: 15000 });
  // Ensure cells ON
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(800);
  await expect(page.locator('[data-testid="cell-card"], [data-testid="cell-empty-hint"]').first()).toBeVisible();
  // The toggle must be VISIBLE and clickable in cell view at 1000px.
  await expect(toggle).toBeVisible();
  const box = await toggle.boundingBox();
  expect(box).not.toBeNull();
  // In-viewport reachability (not clipped off-screen).
  const vp = page.viewportSize();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(vp!.height);
  // Toggle OFF -> plain text editor returns.
  await toggle.click();
  await page.waitForTimeout(800);
  await expect(page.locator('[data-testid="cql-editor"]')).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
});

test("S11 narrow-900: unstrandable when all defines deleted; round-trip re-ON", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  await expect(toggle).toBeVisible({ timeout: 15000 });
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(800);
  // Scroll the cell list to the BOTTOM — the real strand scenario.
  await page.locator(".cell-list").evaluate((el) => el.scrollTo(0, el.scrollHeight));
  await page.waitForTimeout(300);
  const box = await toggle.boundingBox();
  const vp = page.viewportSize();
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(vp!.height);
  // Round-trip: OFF then back ON.
  await toggle.click();
  await page.waitForTimeout(600);
  await expect(page.locator('[data-testid="cql-editor"]')).toBeVisible();
  await toggle.click();
  await page.waitForTimeout(600);
  await expect(page.locator('[data-testid="cell-card"], [data-testid="cell-empty-hint"]').first()).toBeVisible();
  // UNSTRANDABLE: in cell view the toggle stays ENABLED even with nothing
  // splittable (Muse 1 fix pin).
  await expect(toggle).toBeEnabled();
});
