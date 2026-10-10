import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-shellrebuild-20261009";
const PORT = 19091;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = "library MadieHost\ndefine A: 1\n";

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "ux5-s4-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "MadieHost.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(
    join(wsDir, "data", "patients.ndjson"),
    '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n',
  );
  // A real (synthetic) MADiE tests zip the UI will upload
  const { buildMadieTestsZip } = await import("./madie_fixtures");
  writeFileSync(join(wsDir, "madie-tests.zip"), buildMadieTestsZip());
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
  await expect(page.locator(".dev-lib").first()).toContainText("MadieHost", { timeout: 20000 });
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    await new Promise((r) => setTimeout(r, 300));
  }
});

test("madie tests import: zip upload routes through the API and reports counts", async () => {
  const zipPath = join(wsDir, "madie-tests.zip");
  let captured: { zip?: string } = {};
  await page.route("**/api/madie/import-tests", async (route) => {
    const body = route.request().postDataJSON() as { zip_base64?: string };
    captured = { zip: body.zip_base64?.slice(0, 8) };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        ok: true,
        counts: { cases: 2, expected: 2 },
        cases: ["data/patient-1/case.json", "data/patient-2/case.json"],
        expected: [
          "measures/expected/patients/TestMeasure/patient-1.json",
          "measures/expected/patients/TestMeasure/patient-2.json",
        ],
      }),
    });
  });

  // Click the Measures MADiE button -> hidden file input -> zip
  const fileChooserPromise = page.waitForEvent("filechooser");
  await page
    .locator("h2", { hasText: "Measures" })
    .locator(".dev-addrail", { hasText: "MADiE" })
    .click();
  const chooser = await fileChooserPromise;
  await chooser.setFiles(zipPath);

  await expect(page.locator(".dev-importmsg")).toContainText(/MADiE tests imported/, {
    timeout: 15000,
  });
  await expect(page.locator(".dev-importmsg")).toContainText("cases");
  expect(captured.zip).toBeTruthy(); // base64 reached the API
});

test("madie package import: failure surfaces the diagnostic", async () => {
  await page.route("**/api/madie/import-package", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        ok: false,
        diagnostics: [{ code: "INPUT_ERROR", message: "no importable content found" }],
      }),
    });
  });
  const fileChooserPromise = page.waitForEvent("filechooser");
  await page
    .locator("h2", { hasText: "Libraries" })
    .locator(".dev-addrail", { hasText: "MADiE" })
    .click();
  const chooser = await fileChooserPromise;
  await chooser.setFiles({
    name: "fake.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("not really a zip"),
  });
  await expect(page.locator(".dev-importmsg")).toContainText(/failed: no importable content/, {
    timeout: 15000,
  });
});
