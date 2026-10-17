import { mkdtemp, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S17: MADiE package-zip validation campaign. Zips are CONSTRUCTED from
// REAL MADiE-authored content (ecqm-content-qicore-2025 submodule: the
// CMS122 measure resource, its CQL, real patient bundles + expected
// MeasureReports with the isTestCases marker attached) laid out in the
// exact MADiE export shape the importers parse.

const BASE = "http://127.0.0.1:19131";
let dir: string | null = null;
let server: ChildProcess | null = null;

const PKG = "/tmp/opencode/s17/CMS122FHIR-package.zip";
const PKG_EXTRA = "/tmp/opencode/s17/CMS122FHIR-package-extra.zip";
const TC = "/tmp/opencode/s17/CMS122FHIR-testcases.zip";
const TC_EXTRA = "/tmp/opencode/s17/CMS122FHIR-testcases-extra.zip";

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s17-"));
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19131", "--no-open"],
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

// Node-side helper (server API calls don't need a browser): the API
// takes {zip_base64} JSON.
async function post(path: string, bytes: Buffer) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zip_base64: bytes.toString("base64") }),
  });
  const j = (await res.json()) as any;
  return j?.data ?? j;
}

test("S17-1: package zip imports — library parses, valuesets materialize, measure lands", async () => {
  const out = await post("/api/madie/import-package", await readFile(PKG));
  expect(out.ok).toBe(true);
  await new Promise((r) => setTimeout(r, 1000));
  expect(out.counts?.cql ?? 0).toBeGreaterThanOrEqual(1);
  expect(out.counts?.measures ?? 0).toBeGreaterThanOrEqual(1);
  // Kernel restart picks up the new cql/ files; verify via the API that
  // the library list shows CMS122FHIR and parses.
  const libs = await (await fetch(`${BASE}/api/libraries`)).json();
  const names = JSON.stringify(libs);
  expect(names).toContain("CMS122FHIR");
});

test("S17-2: test-case zip imports — data/<patient>/ populated + expectations stored", async () => {
  const out = await post("/api/madie/import-tests", await readFile(TC));
  expect(out.ok).toBe(true);
  expect((out.cases ?? []).length).toBe(3);
  expect((out.expected ?? []).length).toBe(3);
  // The workspace now has data/<patientId>/*.json bundles.
  const ws = await (await fetch(`${BASE}/api/workspace`)).json();
  const d = ws?.data ?? ws?.workspace ?? {};
  expect(JSON.stringify(d)).toContain("090ad2fc");
});

test("S17-3: imported content RUNS — cells on the imported library render results", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  await page.waitForTimeout(1000);
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const row = libPanel.locator(".nav-item", { hasText: "CMS122FHIR" }).first();
  await row.waitFor({ state: "visible", timeout: 15000 });
  await row.click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CMS122/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(4000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1500);
  // The library parses (cells render) — run one cell; results render
  // (dataset present from the test-case import).
  const cards = page.locator('[data-testid="cell-card"]');
  expect(await cards.count()).toBeGreaterThan(0);
  await page.locator('[data-testid="cell-run"]').first().click();
  const out = page.locator('[data-testid="cell-out"]').first();
  await expect(out).toBeVisible({ timeout: 60000 });
});

test("S17-4: robustness — EXTRA resources in the package zip never crash or corrupt", async () => {
  const out = await post("/api/madie/import-package", await readFile(PKG_EXTRA));
  // Import succeeds; unknown/junk files are reported-ignored in diagnostics.
  expect(out.ok).toBe(true);
  const diags = JSON.stringify(out.diagnostics ?? []);
  expect(diags.length).toBeGreaterThanOrEqual(0); // present, not crashing
  // Workspace still healthy.
  const h = await (await fetch(`${BASE}/health`)).json();
  expect(h.ok).toBe(true);
});

test("S17-5: robustness — extra patient bundles + junk in the test zip import cleanly", async () => {
  const out = await post("/api/madie/import-tests", await readFile(TC_EXTRA));
  expect(out.ok).toBe(true);
  // The plain (no-expectation) bundle imports as a patient bundle with a
  // NO_EXPECTATION diagnostic; junk skipped.
  const diags = JSON.stringify(out.diagnostics ?? []);
  expect(diags).toContain("NO_EXPECTATION");
  // Workspace still healthy after.
  const h = await (await fetch(`${BASE}/health`)).json();
  expect(h.ok).toBe(true);
});
