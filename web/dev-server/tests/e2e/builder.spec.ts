import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 19001;
const BASE = `http://127.0.0.1:${PORT}`;

let server: ChildProcess | null = null;
let dir: string | null = null;

test.beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "v41-builder-"));
  mkdirSync(join(dir, "cql"));
  mkdirSync(join(dir, "valuesets"));
  mkdirSync(join(dir, "data"));
  writeFileSync(
    join(dir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "",
      "valueset \"BPVS\": 'http://example.com/bp'",
      "context Patient",
      "",
      "// # %% [name: IsMale]",
      "define IsMale: Patient.gender = 'male'",
      "",
    ].join("\n"),
  );
  writeFileSync(
    join(dir, "valuesets", "vs1.json"),
    JSON.stringify({
      resourceType: "ValueSet",
      id: "vs1",
      url: "http://example.com/bp",
      compose: { include: [{ system: "http://loinc.org", concept: [{ code: "8480-6", display: "BP" }] }] },
    }),
  );
  writeFileSync(
    join(dir, "data", "patients.ndjson"),
    [
      JSON.stringify({ resourceType: "Patient", id: "p1", gender: "male", birthDate: "1974-12-25" }),
      JSON.stringify({ resourceType: "Patient", id: "p2", gender: "female", birthDate: "1990-01-01" }),
    ].join("\n") + "\n",
  );

  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", String(PORT), "--no-open"],
    { cwd: dir, env: { PYTHONPATH: "/mnt/d/fhir4ds-cleanroom-v31-20261007", PATH: process.env.PATH ?? "" }, stdio: "ignore" },
  );
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {}
    await new Promise((res) => setTimeout(res, 500));
  }
  throw new Error("server never became healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid, "SIGKILL");
    } catch {
      /* already gone */
    }
    await new Promise((res) => setTimeout(res, 300));
  }
  server = null;
});

test("builder pane opens from rail with type picker and templates", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await expect(page.locator(".dev-rbpane")).toBeVisible();
  await expect(page.locator(".dev-rbtemplates")).toBeVisible();
  await expect(page.locator(".dev-rbtpl", { hasText: "Observation" })).toHaveCount(1);
});

test("template loads, form renders, validate passes, save appends ndjson", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();
  await expect(page.locator(".dev-rbform")).toBeVisible();
  await expect(page.locator(".dev-rbrow").first()).toBeVisible();

  // JSON writer: set a fresh id via the textarea
  const area = page.locator(".dev-rbjsonarea");
  await area.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(
    JSON.stringify({ resourceType: "Patient", id: "p9", gender: "male", birthDate: "1980-05-05" }, null, 2),
  );
  await page.locator(".dev-rbvalidate").click();
  await expect(page.locator(".dev-rbok", { hasText: "valid" })).toBeVisible();

  await page.locator(".dev-rbdataset").selectOption({ index: 0 });
  await page.locator(".dev-rbsavebtn").click();
  await expect(page.locator(".dev-rbsavemsg")).toContainText("Saved to", { timeout: 15000 });
  await expect(page.locator(".dev-rbsavemsg")).toContainText("restart the kernel");

  // file-side pin (API test also pins this, cheap to double-check)
  const text = readFileSync(join(dir!, "data", "patients.ndjson"), "utf8");
  expect(text.trim().split("\n").length).toBe(3);
  expect(text).toContain('"id": "p9"');
});

test("invalid resource blocks save with inline red", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();

  const area = page.locator(".dev-rbjsonarea");
  await area.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(JSON.stringify({ resourceType: "Patient", id: "" }, null, 2));
  await page.locator(".dev-rbvalidate").click();
  await expect(page.locator(".dev-rberror").first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator(".dev-rbsavebtn")).toBeDisabled();
});

test("dataset click opens the dataset pane with stats (no crash)", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-dataset").first()).toBeVisible();
  await page.locator(".dev-dataset").first().click();
  const pane = page.locator(".dev-dspane");
  await expect(pane).toBeVisible();
  await expect(pane.locator(".dev-dstotal")).toContainText("total: 2", { timeout: 20000 });
  await expect(pane.locator(".dev-dschipstat").first()).toContainText("Patient");
});
