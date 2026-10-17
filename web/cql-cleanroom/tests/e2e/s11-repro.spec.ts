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
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "CellLib.cql"),
    "library CellLib version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\n// # %% [name: IsAdult]\ndefine IsAdult: AgeInYearsAt(Today()) >= 18\n\n// # %% [name: Long]\ndefine Long:\n  1 = 1\n  and 2 = 2\n  and 3 = 3\n  and 4 = 4\n  and 5 = 5\n  and 6 = 6\n  and 7 = 7\n  and 8 = 8\n  and 9 = 9\n  and 10 = 10\n  and 11 = 11\n  and 12 = 12\n\n// # %% [name: Combined]\ndefine Combined: IsAdult and true\n",
    "utf8",
  );
  // Two patients so retrieving/boolean cells return populated rows.
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    '{"resourceType":"Patient","id":"p1","gender":"male","birthDate":"1980-05-01"}\n' +
      '{"resourceType":"Patient","id":"p2","gender":"female","birthDate":"2015-03-10"}\n',
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
  // Fixture: IsAdult (1 line), Long (13 lines), Combined (1 line).
  expect(heights.length).toBe(3);
  const longH = heights[1];
  for (const h of [heights[0], heights[2]]) expect(longH).toBeGreaterThan(h + 60);
  expect(longH).toBeGreaterThan(200);
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

test("S12: cells -> text shows NON-EMPTY editor; toggle labels name the destination", async ({ page }) => {
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
  await page.waitForTimeout(800);
  // In cell view the label names the DESTINATION (Text).
  await expect(toggle).toHaveText(/Text ⇄/);
  // Switch back -> editor renders with content (S12 blank-editor fix).
  await toggle.click();
  await page.waitForTimeout(1200);
  const host = page.locator('[data-testid="cql-editor"]');
  await expect(host).toBeVisible();
  const box = await host.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThan(100);
  // S13: Monaco must ACTUALLY attach (the root cause was a mount-once
  // effect bound to the first host div; the new div stayed empty).
  const attached = await host.evaluate(
    (el) => el.querySelectorAll(".monaco-editor").length,
  );
  expect(attached).toBeGreaterThan(0);
  const text = await host.textContent();
  expect((text ?? "").trim().length).toBeGreaterThan(0);
  await expect(toggle).toHaveText(/Cells ⇄/);
});

test("S12: cell run output renders a TABLE with headers", async ({ page }) => {
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
  await page.waitForTimeout(1000);
  await page.locator('[data-testid="cell-run"]').first().click();
  const table = page.locator('[data-testid="cell-table"]').first();
  await expect(table).toBeVisible({ timeout: 30000 });
  const headers = await table.locator("thead th").allTextContents();
  expect(headers.length).toBeGreaterThan(0);
  expect(headers).toContain("patient_id");
  expect(await table.locator("tbody tr").count()).toBeGreaterThan(0);
  // Scrollable container + NO raw pipe-delimited <pre> alongside the table.
  const cls = await table.evaluate((el) => el.className);
  expect(cls).toContain("cell-table-wrap");
  const out = table.locator("..");
  await expect(out.locator("pre")).toHaveCount(0);
});

test("S13: dep cells EACH show a populated table after running a dependents", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "CellLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CellLib/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1000);
  // Run the LAST cell (Combined -> closure includes IsAdult).
  const n = await page.locator('[data-testid="cell-run"]').count();
  await page.locator('[data-testid="cell-run"]').nth(n - 1).click();
  await page.waitForTimeout(2000);
  // BOTH cells show a POPULATED table (S13 item 2 pin — no collapse).
  for (const cellName of ["Combined", "IsAdult"]) {
    const card = page.locator(`[data-testid="cell-card"][data-cell="${cellName}"]`);
    const table = card.locator('[data-testid="cell-table"]');
    await expect(table).toBeVisible({ timeout: 30000 });
    expect(await table.locator("tbody tr").count()).toBeGreaterThan(0);
    // S13 item 1: results render expanded — no expand button anywhere.
    await expect(card.locator(".cell-expand")).toHaveCount(0);
  }
});

test("S14: many-define library — cards keep floor height, list scrolls, resize works", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  // Type a >=10-define library into the default editor. Auto-adoption may
  // have opened cells on the default library — switch to TEXT first.
  const toggle0 = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle0.getAttribute("aria-checked")) === "true") await toggle0.click();
  await page.waitForTimeout(800);
  const editor = page.locator('[data-testid="cql-editor"]');
  await editor.click();
  await page.keyboard.press("Control+a");
  const defs = Array.from({ length: 12 }, (_, i) => `// # %% [name: D${i + 1}]\ndefine D${i + 1}: ${i + 1} = ${i + 1}`).join("\n\n");
  await page.keyboard.type(`library ManyLib version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\n${defs}\n`, { delay: 5 });
  await page.waitForTimeout(2500);
  // Open cells.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1500);
  // (4) 12 cards, EACH >= 160px tall (editor floor) — no slivers.
  const heights = await page.locator('[data-testid="cell-monaco"]').evaluateAll((els) =>
    els.map((el) => el.getBoundingClientRect().height),
  );
  expect(heights).toHaveLength(12);
  for (const h of heights) expect(h).toBeGreaterThanOrEqual(158);
  // The LIST scrolls (total content exceeds the viewport).
  const scroll = await page.locator(".cell-list").evaluate(
    (el) => ({ s: el.scrollHeight, c: el.clientHeight }),
  );
  expect(scroll.s).toBeGreaterThan(scroll.c);
  // (3) Drag-resize: keyboard-resize the first handle, assert its editor grew.
  const handle = page.locator('[data-testid="cell-resize"]').first();
  await handle.focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(400);
  const grown = await page.locator('[data-testid="cell-monaco"]').first().evaluate((el) => el.getBoundingClientRect().height);
  expect(grown).toBeGreaterThanOrEqual(heights[0] + 30);
  // Reset: Enter cycles override off -> back to natural height.
  await handle.focus();
  await page.keyboard.press("Enter");
  await page.waitForTimeout(400);
  const reset = await page.locator('[data-testid="cell-monaco"]').first().evaluate((el) => el.getBoundingClientRect().height);
  expect(Math.abs(reset - heights[0])).toBeLessThan(8);
  // Persistence: re-apply a resize, reload, verify it is restored.
  await handle.focus();
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(300);
  const persisted = await page.locator('[data-testid="cell-monaco"]').first().evaluate((el) => el.getBoundingClientRect().height);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(15000);
  const toggle2 = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle2.getAttribute("aria-checked")) !== "true") await toggle2.click();
  await page.waitForTimeout(1500);
  const restored = await page.locator('[data-testid="cell-monaco"]').first().evaluate((el) => el.getBoundingClientRect().height);
  expect(Math.abs(restored - persisted)).toBeLessThan(8);
});
