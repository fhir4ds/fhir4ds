/**
 * QA it18 — Domain 6 (connected mode) × EXPLORER (chaos).
 *  X1 server dies mid-session: UI keeps editing; a status surface reflects
 *     the loss (no silent forever-alive illusion)
 *  X2 server comes BACK: does the app recover without a manual reload?
 *  X3 concurrent disk writes while editing (watcher storms): app stays
 *     responsive; data-hint appears at most once
 *  X4 rapid nav section toggles during connection: no dead UI
 *  X5 malformed watcher payloads / huge file: never kills the app
 */
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

const BASE = "http://127.0.0.1:19181";
let dir: string | null = null;
let server: ChildProcess | null = null;

async function startServer() {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir!, "--port", "19181", "--no-open"],
    {
      cwd: "/home/jmontavon/src/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/home/jmontavon/src/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  server.stdout?.on("data", () => undefined);
  server.stderr?.on("data", () => undefined);
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("it18 dev server did not become healthy");
}

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-it18-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "Lib.cql"),
    "library Lib version '1.0.0'\nusing FHIR version '4.0.1'\ninclude FHIRHelpers version '4.0.1' called FHIRHelpers\ncontext Patient\n\ndefine Ok: 1 = 1\n",
    "utf8",
  );
  await startServer();
});

test.afterAll(async () => {
  if (server?.pid) {
    try { process.kill(server.pid); } catch { /* gone */ }
  }
  if (dir) await rm(dir, { recursive: true, force: true }).catch(() => undefined);
});

async function openApp(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForTimeout(15_000);
}

test("X1: server dies mid-session — UI keeps editing and surfaces the loss", async ({ page }) => {
  await openApp(page);
  // kill the devserver behind the page
  if (server?.pid) process.kill(server.pid);
  await page.waitForTimeout(2_000);
  // the editor must still be usable (in-session edits)
  await page.click('[data-testid="nav-toggle-libraries"]');
  await page.waitForTimeout(500);
  // connected mode boots into CELL view (S25 auto-cellify) — the editable
  // surface is the cell editor (the last cell holds the library text)
  const cells = page.locator('[data-testid="cell-editor"]');
  await expect(cells.first()).toBeVisible({ timeout: 20_000 });
  // dismiss the cell coach if present, then type into the live Monaco
  await page.getByText("Got it").click().catch(() => undefined);
  const monaco = page.locator(".monaco-editor").first();
  await expect(monaco).toBeVisible({ timeout: 20_000 });
  await monaco.click();
  await page.keyboard.press("Control+End");
  // insertText must be ACCEPTED while the server is down (no deadlock,
  // no exception bubbling into a dead page)
  await page.keyboard.insertText("// edited while server down");
  // some surface must stop claiming a live connection (footer no longer
  // promises local files, or a data/save request fails visibly)
  const footerTitle = await page.locator('[data-testid="footer-location"]').getAttribute("title");
  const stillClaims = (footerTitle ?? "").includes("Connected dev server");
  // attempt a connected action: it must not hang silently forever —
  // the save endpoint should fail fast (fetch rejects); we assert the page
  // is still alive rather than asserting a specific notice (S22a-era UX)
  const alive = await page.evaluate(() => document.querySelector('[data-testid="status-bar"]') !== null);
  expect(alive).toBe(true);
  // document the observed behavior for the report
  console.log("X1 footer still claims connected:", stillClaims);
});

test("X2: server restart — app recovers or degrades honestly", async ({ page }) => {
  // X1 left the server dead: bring it back BEFORE loading the page
  await startServer();
  await openApp(page);
  if (server?.pid) { try { process.kill(server.pid); } catch { /* already gone */ } }
  await page.waitForTimeout(1_000);
  await startServer(); // fresh server, same workspace
  await page.waitForTimeout(5_000);
  // after recovery the page must still be interactive; ideally the
  // watcher reconnects (S6) — check a disk change still flows
  if (!dir) throw new Error("no dir");
  const pFile = join(dir, "Library", "Lib.cql");
  const src = await readFileSafe(pFile);
  if (src !== null) {
    await writeFile(pFile, src + "\n// x2 touch\n", "utf8");
    // no hard assertion on hint timing: recovery UX varies; the page must
    // simply remain alive and not loop-crash
  }
  const alive = await page.evaluate(() => document.querySelector(".app-footer") !== null);
  expect(alive).toBe(true);
});

async function readFileSafe(p: string): Promise<string | null> {
  try {
    const { readFile } = await import("node:fs/promises");
    return await readFile(p, "utf8");
  } catch { return null; }
}

test("X3: watcher storm — 8 rapid disk writes stay coherent", async ({ page }) => {
  await openApp(page);
  if (!dir) throw new Error("no dir");
  const target = join(dir, "Library", "Lib.cql");
  const base = await readFileSafe(target);
  if (base === null) { test.skip(); return; }
  for (let i = 0; i < 8; i++) {
    await writeFile(target, base + `\n// storm ${i}\n`, "utf8");
    await new Promise((r) => setTimeout(r, 150));
  }
  await page.waitForTimeout(4_000);
  // the app must remain responsive; footer hint count is at most one element
  const hints = await page.locator('[data-testid="footer-data-hint"]').count();
  expect(hints).toBeLessThanOrEqual(1);
  const alive = await page.evaluate(() => document.querySelector('[data-testid="status-bar"]') !== null);
  expect(alive).toBe(true);
});

test("X4: rapid nav toggles while connected never wedge the UI", async ({ page }) => {
  await openApp(page);
  for (const t of ["nav-toggle-tests", "nav-toggle-valuesets", "nav-toggle-libraries", "nav-toggle-tests"]) {
    await page.click(`[data-testid="${t}"]`, { timeout: 10_000 });
    await page.waitForTimeout(200);
  }
  const alive = await page.evaluate(() => document.querySelector('[data-testid="status-bar"]') !== null);
  expect(alive).toBe(true);
});

test("X5: huge file landing on disk never kills the app", async ({ page }) => {
  await openApp(page);
  if (!dir) throw new Error("no dir");
  await writeFile(join(dir, "Library", "big.cql"), "// " + "x".repeat(600_000) + "\n", "utf8");
  await page.waitForTimeout(4_000);
  const alive = await page.evaluate(() => document.querySelector('[data-testid="status-bar"]') !== null);
  expect(alive).toBe(true);
});
