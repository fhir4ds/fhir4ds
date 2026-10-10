import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-shellrebuild-20261009";
const PORT = 19131;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = "library EvLib\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"Initial Population\": exists [Patient]\ndefine \"Numerator\": exists [Observation]\n";

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "ux5-ev-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "EvLib.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(
    join(wsDir, "data", "p.ndjson"),
    '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n' +
      '{"resourceType": "Observation", "id": "o1", "status": "final", "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]}, "subject": {"reference": "Patient/p1"}}\n',
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
  await expect(page.locator(".dev-iconrail")).toBeVisible({ timeout: 20000 });
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    await new Promise((r) => setTimeout(r, 200));
  }
});

test("evidence modal: measure run -> explain chip opens payload", async () => {
  // open the measure scaffold pane and run it (same flow as s3expected)
  await page.locator(".dev-lib.small", { hasText: "+ EvLib scaffold" }).first().click();
  const pane = page.locator(".dev-panewrap", { hasText: "Measure" });
  await expect(pane).toBeVisible({ timeout: 15000 });
  await pane.locator("select").first().selectOption("proportion");
  const ipRow = pane.locator("tr", { hasText: "initial-population" }).first();
  await ipRow.locator("select").selectOption({ label: "Initial Population" });
  const numRow = pane.locator("tr", { hasText: "numerator" }).first();
  await numRow.locator("select").selectOption({ label: "Numerator" });
  await pane.getByRole("button", { name: /Run measure/i }).click();
  await expect(pane.locator(".dev-mspatients")).toBeVisible({ timeout: 30000 });

  // explain chip next to patient chip opens the modal
  await pane.locator(".dev-msexplainchip").first().click();
  const modal = page.locator(".dev-evmodal");
  await expect(modal).toBeVisible({ timeout: 15000 });
  await expect(modal.locator(".dev-evheader")).toContainText("p1");
  // both defines render with boolean results + evidence rows
  await expect(modal.locator(".dev-evsection")).toHaveCount(2, { timeout: 20000 });
  await expect(modal.locator(".dev-evcol", { hasText: "Initial Population" })).toBeVisible();
  await expect(modal.locator(".dev-evcol", { hasText: "Numerator" })).toBeVisible();
  await expect(modal.locator(".dev-evtable tbody tr").first()).toContainText("Patient/p1", { timeout: 15000 });
  // Esc closes (dispatch on window — playwright focus may sit on a pane button)
  await page.evaluate(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
  await expect(modal).toBeHidden({ timeout: 10000 });
  // reopen and close via ✕
  await pane.locator(".dev-msexplainchip").first().click();
  await expect(modal).toBeVisible({ timeout: 15000 });
  await modal.locator(".dev-evclose").click();
  await expect(modal).toBeHidden({ timeout: 10000 });
});
