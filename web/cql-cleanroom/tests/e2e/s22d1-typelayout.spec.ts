import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S22d-1 (AM5–AM8): the FHIR-type workspace. A LEGACY workspace boots
// the devserver, auto-migrates one-time to the type layout (originals
// archived to _attic/), the kernel evaluates from Patient/ folders, and
// the cleanroom UI lists the type-layout library + patient roster.

const BASE = "http://127.0.0.1:19195";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s22d-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await mkdir(join(dir, "valuesets"), { recursive: true });
  await writeFile(
    join(dir, "cql", "TypeLib.cql"),
    [
      "library TypeLib version '1.0.0'",
      "using FHIR version '4.0.1'",
      "include FHIRHelpers version '4.0.1' called FHIRHelpers",
      "context Patient",
      "",
      "define \"Female\":",
      "  Patient.gender = 'female'",
      "",
    ].join("\n"),
    "utf8",
  );
  await writeFile(
    join(dir, "valuesets", "vs1.json"),
    '{"resourceType":"ValueSet","id":"tv1","url":"http://example.org/t/vs1","compose":{"include":[]}}',
    "utf8",
  );
  const pats = [
    { resourceType: "Patient", id: "t1", gender: "female", birthDate: "1980-01-01" },
    { resourceType: "Patient", id: "t2", gender: "male", birthDate: "1975-01-01" },
    { resourceType: "Encounter", id: "en1", status: "finished", subject: { reference: "Patient/t1" } },
  ];
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    pats.map((p) => JSON.stringify(p)).join("\n") + "\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19195", "--no-open"],
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

test("S22d1-1: boot auto-migrates legacy -> FHIR-type layout", async ({ request }) => {
  // The workspace listing reads the MIGRATED shape: library under
  // Library/, valueset under ValueSet/, patients in the roster.
  const res = await request.get(`${BASE}/api/workspace`);
  const body = (await res.json()) as {
    workspace?: { libraries?: { name: string; path?: string }[] };
    data?: { libraries?: { name: string; path?: string }[] };
  };
  const libs = (body.workspace ?? body.data)?.libraries ?? [];
  expect(libs.map((l) => l.name)).toContain("TypeLib");
  expect(libs.find((l) => l.name === "TypeLib")?.path).toContain("Library");

  // Patients evaluated from Patient/ folders.
  const pats = await (await request.get(`${BASE}/api/patients`)).json();
  expect((pats?.patients ?? pats?.data?.patients) ?? pats.patients).toEqual(["t1", "t2"]);

  // The measure of proof: patient drill-in sees the Encounter (the
  // type-folder attribution round-trips through the kernel).
  const p1 = await (await request.get(`${BASE}/api/patient/t1`)).json();
  const d = p1?.data ?? p1;
  expect((d?.resources ?? []).map((r: { resourceType: string }) => r.resourceType).sort()).toEqual([
    "Encounter",
    "Patient",
  ]);
});

test("S22d1-2: UI boots on the type layout (library tab + roster)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);

  // Boot purity opens the type-layout library.
  await expect(page.getByRole("tab", { name: /TypeLib/i })).toBeVisible({ timeout: 30000 });

  // The roster lists the two patients (kernel data from Patient/ folders).
  await page.locator('[data-testid="nav-toggle-tests"]').click();
  const rosterRow = page.locator('[data-testid="ds-roster-row"]').first();
  if (!(await rosterRow.isVisible().catch(() => false))) {
    await page.locator('[data-testid="nav-toggle-tests"]').click();
    await page.waitForTimeout(800);
  }
  await expect(rosterRow).toBeVisible({ timeout: 15000 });
  const ids = await page.locator('[data-testid="ds-roster-row"]').allTextContents();
  expect(ids).toContain("t1");
  expect(ids).toContain("t2");
});
