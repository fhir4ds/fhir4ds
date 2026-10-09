import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-ux5-20261008";
const PORT = 19081;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = `library ExpectedLib
using FHIR version '4.0.1'

valueset "MV": 'http://example.org/mv'

context Patient

define "Initial Population":
  exists [Patient]

define "Denominator":
  "Initial Population"

define "Numerator":
  "Initial Population"
`;

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "ux5-s3b-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "ExpectedLib.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(
    join(wsDir, "data", "patients.ndjson"),
    '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n' +
      '{"resourceType": "Patient", "id": "p2", "gender": "female"}\n',
  );
});

test.afterAll(async () => {
  rmSync(wsDir, { recursive: true, force: true });
});

test.beforeEach(async ({ browser }) => {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", wsDir, "--port", String(PORT), "--no-open"],
    {
      cwd: wsDir,
      env: { PATH: process.env.PATH ?? "", PYTHONPATH: WORKTREE },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) break;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
    if (i === 59) throw new Error("dev server did not become healthy");
  }
  const ctx = await browser.newContext();
  page = await ctx.newPage();
  await page.goto(BASE);
  await expect(page.locator(".dev-lib").first()).toContainText("ExpectedLib", { timeout: 20000 });
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    await new Promise((r) => setTimeout(r, 300));
  }
});

test("expected results: scaffold+run in Measure pane enables capture->save->run-tests", async () => {
  // Open the Measure scaffold pane for the library (rail entry "+ ExpectedLib scaffold")
  await page
    .locator(".dev-lib.small", { hasText: "+ ExpectedLib scaffold" })
    .first()
    .click();
  await expect(
    page.locator(".dev-panewrap", { hasText: "Measure" }),
  ).toBeVisible({ timeout: 10000 });

  // Map scoring + initial population, then Run (scaffold+run lifts measure to App)
  await page.locator(".dev-panewrap select").first().selectOption("proportion");
  const ipSelect = page
    .locator(".dev-panewrap tr", { hasText: "initial-population" })
    .locator("select");
  await ipSelect.selectOption({ label: "Initial Population" });
  const runBtn = page.getByRole("button", { name: /Run measure/i });
  await expect(runBtn).toBeEnabled({ timeout: 10000 });
  await runBtn.click();
  // Wait until the Expected pane shows the measure is armed (capture enabled)
  const captureBtn = page.getByRole("button", { name: /Capture from run/i });
  await expect(captureBtn).toBeEnabled({ timeout: 30000 });

  // Capture seeds the grid from actual run results (unsaved)
  await captureBtn.click();
  const grid = page.locator(".dev-expectedpane .dev-expectedgrid");
  await expect(grid).toBeVisible({ timeout: 20000 });
  // p1 + p2 rows seeded with initial-population counts of 1
  await expect(grid.locator(".dev-expectedpatient", { hasText: "p1" })).toBeVisible();
  await expect(grid.locator(".dev-expectedpatient", { hasText: "p2" })).toBeVisible();

  // Save expectations
  await page.getByRole("button", { name: /Save expectations/i }).click();
  await expect(
    page.locator(".dev-expectedpane").getByText(/Saved/i),
  ).toBeVisible({ timeout: 15000 });

  // Run tests: all pass
  await page.getByRole("button", { name: /Run tests/i }).click();
  const runHead = page.locator(".dev-expectedrunhead");
  await expect(runHead).toContainText(/checks pass/i, { timeout: 30000 });
  await expect(page.locator(".dev-expectedfail")).toHaveCount(0);

  // Edit p2's initial-population count to 0 -> mismatch row appears
  const p2Row = grid.locator(".dev-expectedrow", { hasText: "p2" }).first();
  const countInput = p2Row.locator(".dev-expectedcount").first();
  await countInput.fill("0");
  await page.getByRole("button", { name: /Save expectations/i }).click();
  await expect(
    page.locator(".dev-expectedpane").getByText(/Saved/i),
  ).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: /Run tests/i }).click();
  await expect(page.locator(".dev-expectedfail")).toBeVisible({ timeout: 30000 });

  // Delete p2: its expectation file is removed, so p2 surfaces as
  // "missing expectation" rows (patient in run, no saved expectation)
  await p2Row.locator(".dev-expecteddel").click();
  await page.getByRole("button", { name: /Save expectations/i }).click();
  await expect(
    page.locator(".dev-expectedpane").getByText(/Saved/i),
  ).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: /Run tests/i }).click();
  await expect(page.locator(".dev-expectedfail")).toHaveCount(1, { timeout: 30000 });
  await expect(page.locator(".dev-expectedfail").first()).toContainText("missing expectation");
});
