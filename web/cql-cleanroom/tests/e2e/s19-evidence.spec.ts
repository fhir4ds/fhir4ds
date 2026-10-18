import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S19: evidence must explain EXACTLY the run that produced the clicked
// row — same composed closure library + define + parameters. Repros:
// (1) cms69-style: a cell whose closure does NOT include the parameter
//     declaration cell still yields 'Measurement Period has no supplied
//     value' on evidence (full-buffer explain).
// (2) cms125-style: bottom-console evidence requests measure-mapped
//     output_columns the current library never defined (Denominator...).
// (3) mismatch: cell evidence computed from a different composition.

const BASE = "http://127.0.0.1:19150";
let dir: string | null = null;
let server: ChildProcess | null = null;

// Library shaped like cms69's trap: the parameter lives in the HEADER,
// but the clicked cell's closure references defines whose evaluation
// never needed it standalone... actually the honest shape: parameter in
// header (always in composition). The REAL (1) shape: run composed from
// cells that don't reference the parameter, full buffer requires it via
// ANOTHER cell. Model exactly that.
const LIB = `library CellLib version '1.0.0'
using FHIR version '4.0.1'
context Patient

parameter "Measurement Period" Interval<DateTime>
  default Interval[@2024-01-01, @2024-12-31]

// # %% [name: HasName]
define "HasName":
  Patient.name.first() is not null

// # %% [name: Initial Population]
define "Initial Population":
  "HasName"

// # %% [name: InMP]
define "InMP":
  Patient.birthDate during day of "Measurement Period"
`;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s19-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(join(dir, "cql", "CellLib.cql"), LIB, "utf8");
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    '{"resourceType":"Patient","id":"p1","gender":"male","birthDate":"1980-05-01","name":[{"family":"A","given":["Al"]}]}\n' +
      '{"resourceType":"Patient","id":"p2","gender":"female","birthDate":"2015-03-10","name":[{"family":"B","given":["Bo"]}]}\n',
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19150", "--no-open"],
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
  await libPanel.locator(".nav-item", { hasText: "CellLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /CellLib/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(4000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1200);
}

test("S19-1+3: cell evidence uses the RUN's composition — no param error, matching library", async ({ page }) => {
  await openCells(page);
  // Run the FIRST cell (HasName — closure: HasName only; the composed
  // library must NOT require Measurement Period).
  await page.locator('[data-testid="cell-run"]').first().click();
  const table = page.locator('[data-testid="cell-table"]').first();
  await expect(table).toBeVisible({ timeout: 60000 });
  await table.locator("tbody tr").first().click();
  const pop = page.locator('[data-testid="evidence-popover"]');
  await expect(pop).toBeVisible({ timeout: 20000 });
  // No parameter error (full-buffer explain would hit the parameter).
  const errText = (await page.locator('[data-testid="evidence-popover-error"]').count())
    ? ((await page.locator('[data-testid="evidence-popover-error"]').first().textContent()) ?? "")
    : "";
  expect(errText).not.toMatch(/Measurement Period|no supplied value/i);
  // S19 Muse: no error node at all (regex alone would pass on unrelated
  // failures).
  await expect(page.locator('[data-testid="evidence-popover-error"]')).toHaveCount(0);
  // Popover names the CLICKED define.
  await expect(pop).toContainText(/HasName/);
});

test("S19-2: bottom-console evidence never requests unknown defines (filtered mapping)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") { await toggle.click(); await page.waitForTimeout(1500); }
  await page.getByRole("button", { name: /^Run$/ }).click();
  await page.locator(".results-table tbody tr td", { hasText: "p1" }).first().waitFor({ state: "visible", timeout: 45000 });
  // The default measure maps numerator -> "Has Name" (not defined in
  // CellLib) — with the S19 filter the explain must NOT request it.
  await page.locator("td.cell-evidence").first().click();
  const pop = page.locator('[data-testid="evidence-popover"]');
  await expect(pop).toBeVisible({ timeout: 20000 });
  await expect(page.locator('[data-testid="evidence-popover-error"]')).toHaveCount(0);
});
