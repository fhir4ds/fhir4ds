import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S16: required-parameter cell runs succeed WITHOUT manual entry when the
// workspace carries a Parameters resource (file-based defaults), and
// toolbar merge + evidence-on-click live here too.

const BASE = "http://127.0.0.1:19121";
let dir: string | null = null;
let server: ChildProcess | null = null;

const PARAM_LIB = `library ParamLib version '1.0.0'
using FHIR version '4.0.1'
context Patient

parameter "Measurement Period" Interval<DateTime>

// # %% [name: InMP]
define "InMP":
  Patient.birthDate during day of "Measurement Period"
`;

// A Parameters resource in the DATA dir (default source).
const PARAMS_RESOURCE = JSON.stringify({
  resourceType: "Parameters",
  parameter: [
    {
      name: "Measurement Period",
      valuePeriod: { start: "2020-01-01", end: "2024-12-31" },
    },
  ],
});

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s16-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(join(dir, "cql", "ParamLib.cql"), PARAM_LIB, "utf8");
  await writeFile(join(dir, "data", "parameters.json"), PARAMS_RESOURCE + "\n", "utf8");
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    '{"resourceType":"Patient","id":"p1","gender":"male","birthDate":"1980-05-01"}\n' +
      '{"resourceType":"Patient","id":"p2","gender":"female","birthDate":"2022-03-10"}\n',
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19121", "--no-open"],
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

test("S16-1: required-parameter cell run succeeds via workspace Parameters resource", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "ParamLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /ParamLib/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1000);
  await page.locator('[data-testid="cell-run"]').first().click();
  const out = page.locator('[data-testid="cell-out"]').first();
  await expect(out).toBeVisible({ timeout: 30000 });
  // The REQUIRED parameter is satisfied — no 'no supplied value' error,
  // AND rows actually evaluated (both fixture patients render).
  const text = await out.textContent();
  expect(text ?? "").not.toMatch(/has no supplied value/i);
  const table = page.locator('[data-testid="cell-table"]').first();
  expect(await table.locator("tbody tr").count()).toBeGreaterThanOrEqual(2);
  const cells = await table.locator("tbody td").allTextContents();
  expect(cells.join(" ")).toContain("p1");
  expect(cells.join(" ")).toContain("p2");
});

test("S16-2: single toolbar row — Run All / Clear All merged into the header", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel ').first();
  await libPanel.locator(".nav-item", { hasText: "ParamLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /ParamLib/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1000);
  // Run All + Clear All live in the EDITOR HEADER row (same row as the
  // toggle), not a second toolbar row.
  const header = page.locator(".editor-header");
  await expect(header.locator('[data-testid="cell-runall"]')).toBeVisible();
  // The old cell-toolbar row is GONE (merged).
  await expect(page.locator(".cell-toolbar")).toHaveCount(0);
  // Run All executes sequentially and populates EVERY cell's table;
  // Clear All empties them.
  await header.locator('[data-testid="cell-runall"]').click();
  await expect(page.locator('[data-testid="cell-table"]').first()).toBeVisible({ timeout: 60000 });
  await header.locator('[data-testid="cell-clearall"]').click();
  await expect(page.locator('[data-testid="cell-table"]')).toHaveCount(0);
  // Text view keeps the plain Run button.
  await toggle.click();
  await page.waitForTimeout(800);
  await expect(page.locator('[data-testid="editor-run"]')).toBeVisible();
});

test("S16-3: clicking a results-table row opens the evidence popover", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "ParamLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /ParamLib/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1000);
  await page.locator('[data-testid="cell-run"]').first().click();
  const table = page.locator('[data-testid="cell-table"]').first();
  await expect(table).toBeVisible({ timeout: 30000 });
  // Click a row -> the evidence popover opens.
  await table.locator("tbody tr").first().click();
  await expect(
    page.locator('[data-testid="evidence-popover"], .evidence-popover'),
  ).toBeVisible({ timeout: 15000 });
});
