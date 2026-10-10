import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

const BASE = "http://127.0.0.1:19051";
let dir: string | null = null;
let server: ChildProcess | null = null;

const LIB = [
  "library Demographics version '1.0.0'",
  "using FHIR version '4.0.1'",
  "",
  "valueset \"BPVS\": 'http://example.com/bp'",
  "",
  "// # %% [name: IsMale]",
  "define IsMale: Patient.gender = 'male'",
  "",
].join("\n");

const VS = {
  resourceType: "ValueSet",
  id: "vs1",
  url: "http://example.com/bp",
  compose: {
    include: [
      { system: "http://loinc.org", concept: [{ code: "8480-6", display: "BP" }] },
    ],
  },
};

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "v44-ds-"));
  await Promise.all([
    mkdir(join(dir, "cql")),
    mkdir(join(dir, "valuesets")),
    mkdir(join(dir, "data")),
  ]);
  await writeFile(join(dir, "cql", "Demographics.cql"), LIB);
  await writeFile(join(dir, "valuesets", "vs1.json"), JSON.stringify(VS, null, 2));
  const patients = [];
  for (let i = 1; i <= 6; i++) {
    patients.push(
      JSON.stringify({
        resourceType: "Patient",
        id: `p${i}`,
        gender: i % 2 === 1 ? "male" : "female",
      })
    );
  }
  await writeFile(join(dir, "data", "patients.ndjson"), patients.join("\n") + "\n");

  server = spawnServer(dir);
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

function spawnServer(cwd: string): ChildProcess {
  const proc = spawn("/usr/bin/python3", ["-m", "fhir4ds.cli", "dev", cwd, "--port", "19051", "--no-open"], {
    cwd,
    env: {
      ...process.env,
      PYTHONPATH: "/mnt/d/fhir4ds-shellrebuild-20261009",
      PATH: process.env.PATH ?? "",
    },
    stdio: "ignore",
  });
  return proc;
}

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

test("dataset click opens the pane with live kernel counts (not 0)", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-dataset").first().click();
  const pane = page.locator(".dev-dspane");
  await expect(pane).toBeVisible();
  // THE counts pin: fresh stats fetch on pane open — must be >= 1, never 0.
  const total = pane.locator(".dev-dstotal");
  await expect(total).toContainText(/total: [1-9]/, { timeout: 20000 });
  await expect(pane.locator(".dev-dschipstat").first()).toContainText("Patient");
  // Resource rows render from the file.
  const row = pane.locator(".dev-dslist .dev-dsrow:not(.dev-dsrowhead)").first();
  await expect(row).toContainText("Patient");
  await expect(row).toContainText("p1");
});

test("select a resource → pretty JSON + Edit in builder prefills", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-dataset").first().click();
  const pane = page.locator(".dev-dspane");
  await pane.locator(".dev-dslist .dev-dsrow:not(.dev-dsrowhead)").first().click();
  const json = pane.locator(".dev-dsjson");
  await expect(json).toContainText("Patient");
  await expect(json).toContainText("p1");
  await pane.locator(".dev-dsedit").click();
  // Builder opens prefilled with the resource + dataset path.
  const builder = page.locator(".dev-rbpane");
  await expect(builder).toBeVisible();
  const jsonArea = builder.locator(".dev-rbjsonarea");
  await expect(jsonArea).toContainText("p1");
});
