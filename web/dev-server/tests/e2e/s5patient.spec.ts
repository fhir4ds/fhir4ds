import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-ux5-20261008";
const PORT = 19101;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = `library S5Lib
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists [Patient]
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
`;

const NDJSON = [
  '{"resourceType": "Patient", "id": "p1", "gender": "male", "birthDate": "1980-01-01"}',
  '{"resourceType": "Patient", "id": "p2", "gender": "female"}',
  '{"resourceType": "Observation", "id": "o1", "status": "final", "subject": {"reference": "Patient/p1"}, "code": {"text": "BP"}, "effectiveDateTime": "2026-01-15", "valueQuantity": {"value": 120}}',
].join("\n");

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "ux5-s5-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "S5Lib.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(join(wsDir, "data", "patients.ndjson"), NDJSON + "\n");
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
  await expect(page.locator(".dev-lib").first()).toContainText("S5Lib", { timeout: 20000 });
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    const exited = new Promise<void>((resolve) => {
      server!.once("exit", () => resolve());
      setTimeout(resolve, 5000);
    });
    await exited;
    await new Promise((r) => setTimeout(r, 200));
  }
});

test("patient slide-out: chip in measure run lists that patient's resources", async () => {
  // Scaffold + run the measure (same flow as s3expected)
  await page.locator(".dev-lib.small", { hasText: "+ S5Lib scaffold" }).click();
  await expect(page.locator(".dev-panewrap", { hasText: "Measure" })).toBeVisible();
  await page.locator(".dev-panewrap select").first().selectOption("proportion");
  await page
    .locator("tr", { hasText: "initial-population" })
    .locator("select")
    .selectOption({ label: "Initial Population" });
  await page.getByRole("button", { name: /Run measure/i }).click();
  await expect(page.locator(".dev-mssummary")).toContainText(/✓/, { timeout: 30000 });

  // Patient chips render; click p1
  const chip = page.locator(".dev-mspatientchip", { hasText: "p1" });
  await expect(chip).toBeVisible();
  await chip.click();

  // Slide-out lists p1's resources grouped by type
  const slide = page.locator(".dev-patientslide");
  await expect(slide).toBeVisible();
  await expect(slide.locator(".dev-patientslide-title")).toContainText("p1");
  await expect(slide.locator(".dev-patientslide-typehead", { hasText: "Observation" })).toBeVisible();
  await expect(slide.locator(".dev-patientslide-typehead", { hasText: "Condition" })).toHaveCount(0);

  // Row click -> JSON detail
  await slide.locator(".dev-patientslide-row", { hasText: "o1" }).click();
  await expect(slide.locator(".dev-patientslide-json")).toContainText("Observation");

  // Close
  await slide.locator(".dev-patientslide-close").first().click();
  await expect(slide).toHaveCount(0);
});
