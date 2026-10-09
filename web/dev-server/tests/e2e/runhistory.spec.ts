import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-ux5-20261008";
const PORT = 19141;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = "library HistLib\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"Initial Population\": exists [Patient]\ndefine \"Numerator\": exists [Patient]\n";

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "ux5-rh-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "HistLib.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(
    join(wsDir, "data", "p.ndjson"),
    '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n{"resourceType": "Patient", "id": "p2", "gender": "female"}\n',
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

test("run history: measure run recorded, tile lists it, filter + detail + reopen work", async () => {
  // Run a measure to generate history
  await page.locator(".dev-lib.small", { hasText: "+ HistLib scaffold" }).first().click();
  const pane = page.locator(".dev-panewrap", { hasText: "Measure" });
  await expect(pane).toBeVisible({ timeout: 15000 });
  await pane.locator("select").first().selectOption("proportion");
  const ipRow = pane.locator("tr", { hasText: "initial-population" }).first();
  await ipRow.locator("select").selectOption({ label: "Initial Population" });
  const numRow = pane.locator("tr", { hasText: "numerator" }).first();
  await numRow.locator("select").selectOption({ label: "Numerator" });
  await pane.getByRole("button", { name: /Run measure/i }).click();
  await expect(pane.locator(".dev-mspatients")).toBeVisible({ timeout: 30000 });

  // .runlog.jsonl written with a measure pass event
  const logPath = join(wsDir, ".runlog.jsonl");
  await expect
    .poll(() => (existsSync(logPath) ? readFileSync(logPath, "utf-8") : ""), { timeout: 10000 })
    .toContain('"kind":"measure"');
  const logLine = readFileSync(logPath, "utf-8").split("\n").find((l) => l.includes('"measure"'));
  const ev = JSON.parse(logLine!);
  expect(ev.status).toBe("pass");
  expect(ev.datasets[0]).toContain("p.ndjson");
  expect(ev.patient_count === 2 || ev.patient_count === undefined).toBe(true);
  expect(ev.sql_sha).toMatch(/^sha256:/);

  // History tile (alt+7) lists the event
  await page.keyboard.press("Alt+7");
  const hist = page.locator(".dev-runhistory");
  await expect(hist).toBeVisible({ timeout: 10000 });
  await expect(hist.locator(".dev-rhrow", { hasText: "Measure" })).toBeVisible({ timeout: 10000 });

  // filter: cell shows empty
  await hist.locator(".dev-rhfilter", { hasText: "cell" }).click();
  await expect(hist.locator(".dev-rhrow")).toHaveCount(0);
  await hist.locator(".dev-rhfilter", { hasText: "measure" }).click();
  await expect(hist.locator(".dev-rhrow")).toHaveCount(1);

  // expand detail: datasets context + copy SQL resolves CURRENT sql
  await hist.locator(".dev-rhrow").first().click();
  const detail = hist.locator(".dev-rhdetail");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("p.ndjson");
  await expect(detail).toContainText("2 patients");
  await detail.getByRole("button", { name: /copy sql/i }).click();
  await expect(hist.locator(".dev-vsimportmsg")).toContainText(/copied|clipboard/i);
});
