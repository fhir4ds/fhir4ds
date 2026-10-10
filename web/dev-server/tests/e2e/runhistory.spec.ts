import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-shellrebuild-20261009";
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
  await page.evaluate((t) => { (window as unknown as { __histLib?: string }).__histLib = t; }, CQL);
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    await new Promise((r) => setTimeout(r, 200));
  }
});

test("run history: measure run recorded, bottom-bar tab lists it, filter + detail + copy-sql", async () => {
  // Generate a measure run deterministically via the same API the pane uses.
  const made = await page.evaluate(async () => {
    const cql = (window as unknown as { __histLib?: string }).__histLib!;
    const scaf = await fetch("/api/measure/scaffold", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        libraries: [{ name: "HistLib", text: cql }],
        library: "HistLib",
        mapping: [
          { define: "Initial Population", code: "initial-population" },
          { define: "Numerator", code: "numerator" },
        ],
        scoring: "proportion",
        measure_name: "CleanroomMeasure",
      }),
    }).then((r) => r.json());
    const run = await fetch("/api/measure/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        libraries: [{ name: "HistLib", text: cql }],
        library: "HistLib",
        measure: scaf.measure,
      }),
    }).then((r) => r.json());
    return { ok: run.ok, reports: (run.reports ?? []).length };
  });
  expect(made.ok).toBe(true);
  expect(made.reports).toBe(2);

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

  // History bottom-bar tab lists the event
  await page.locator(".dev-tabs button", { hasText: "history" }).click();
  const hist = page.locator(".dev-runhistory");
  await expect(hist).toBeVisible({ timeout: 10000 });
  await expect(hist.locator(".dev-rhrow", { hasText: "CleanroomMeasure" })).toBeVisible({ timeout: 10000 });

  // filter: cell shows empty; measure shows the row
  await hist.locator(".dev-rhfilter", { hasText: "cell" }).click();
  await expect(hist.locator(".dev-rhrow")).toHaveCount(0);
  await hist.locator(".dev-rhfilter", { hasText: "measure" }).click();
  await expect(hist.locator(".dev-rhrow")).toHaveCount(1);

  // expand detail: dataset context + copy SQL resolves the CURRENT sql store
  await hist.locator(".dev-rhrow").first().click();
  const detail = hist.locator(".dev-rhdetail");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("p.ndjson");
  await detail.getByRole("button", { name: /copy sql/i }).click();
  await expect(hist.locator(".dev-vsimportmsg")).toContainText(/copied|clipboard/i, { timeout: 10000 });
});
