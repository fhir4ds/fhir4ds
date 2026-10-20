import { mkdtemp, mkdir, rm, copyFile } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S22b (Q3): population result tables show ALL evaluated patients with
// boolean columns + a summary line "Evaluated N · <col> T · …" — display
// completeness only (the engine already returns every patient row).

const BASE = "http://127.0.0.1:19185";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s22b-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await mkdir(join(dir, "valuesets"), { recursive: true });
  await copyFile(
    "/mnt/d/fhir4ds/examples/cms125-workspace/cql/CMS125Demo.cql",
    join(dir, "cql", "CMS125Demo.cql"),
  );
  for (const vs of ["mammography.json", "preventive-encounter.json"]) {
    await copyFile(
      `/mnt/d/fhir4ds/examples/cms125-workspace/valuesets/${vs}`,
      join(dir, "valuesets", vs),
    );
  }
  await copyFile(
    "/mnt/d/fhir4ds/examples/cms125-workspace/data/patients.ndjson",
    join(dir, "data", "patients.ndjson"),
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19185", "--no-open"],
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

test("S22b-1: server run table shows ALL 22 patients + summary counts", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);

  // Open the CMS125 library and switch to TEXT mode for the console run.
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "CMS125Demo" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CMS125/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(1500);
  }

  // Whole-library run (text-mode Run = server console run).
  const runBtn = page.getByRole("button", { name: /^Run$/ });
  if ((await runBtn.count()) > 0) await runBtn.click();
  else await page.getByRole("button", { name: /Run All/ }).click();

  // The console table renders ALL evaluated patients: PaginatedTable
  // pages at 10, so assert the pager's "of 22" total (and the summary).
  const results = page.locator('[data-testid="results-table"] tbody tr');
  await expect(results.first()).toBeVisible({ timeout: 60000 });
  await expect(page.locator('[data-testid="results-table-pager"]')).toContainText(
    "of 22",
    { timeout: 20000 },
  );

  // The summary line names the evaluated count + true-counts for the
  // boolean population columns.
  const summary = page.locator('[data-testid="results-summary"]');
  await expect(summary).toBeVisible({ timeout: 20000 });
  await expect(summary).toContainText("Evaluated 22");
  await expect(summary).toContainText("InAgeRange 20");
});

test("S22b-2: cell table shows ALL patients (not just truthy rows)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);

  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "CMS125Demo" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CMS125/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3000);

  // Cells view: CMS125 ships with cell markers (hand-authored), so the
  // S7 rule adopts without forcing the view open — toggle it on.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") {
    await toggle.click();
    await page.waitForTimeout(1500);
  }
  const runAll = page.locator('[data-testid="cell-runall"]');
  await expect(runAll).toBeVisible({ timeout: 30000 });
  await runAll.click();
  const anyTable = page.locator('[data-testid="cell-table"]').first();
  await expect(anyTable).toBeVisible({ timeout: 90000 });

  // At least one cell table shows all 22 patients.
  const tables = page.locator('[data-testid="cell-table"]');
  const n = await tables.count();
  let full = false;
  for (let i = 0; i < n; i++) {
    const rows = await tables.nth(i).locator("tbody tr").count();
    if (rows === 22) full = true;
  }
  expect(full).toBe(true);
});
