import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S22c (AM3): the Tests drawer is the PATIENT ROSTER — one row per
// patient with a source badge; clicking a patient opens their data in
// the resource editor (JSON edit + validate + save-back to that one
// file); edits hot-reload via the data-hint/restart contract.

const BASE = "http://127.0.0.1:19190";
let dir: string | null = null;
let server: ChildProcess | null = null;

const P1 = { resourceType: "Patient", id: "r01", gender: "female", birthDate: "1980-05-05", name: [{ given: ["Rosa"], family: ["Luxe"] }] };
const E1 = { resourceType: "Encounter", id: "e1", status: "finished", subject: { reference: "Patient/r01" }, period: { start: "2024-03-01" } };
const P2 = { resourceType: "Patient", id: "r02", gender: "male", birthDate: "1972-01-02" };

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s22c-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "RosterLib.cql"),
    "library RosterLib version '1.0.0'\nusing FHIR version '4.0.1'\ninclude FHIRHelpers version '4.0.1' called FHIRHelpers\ncontext Patient\n\ndefine Ok: 1 = 1\n",
    "utf8",
  );
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    [P1, E1, P2].map((r) => JSON.stringify(r)).join("\n") + "\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19190", "--no-open"],
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

test("S22c-1: roster lists patients grouped by source with badges", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);

  // The rail may start COLLAPSED (») — the first toggle expands it, the
  // second opens the tests panel (or the single click does both when
  // already expanded).
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await page.locator('[data-testid="nav-toggle-tests"]').click();
  if (!(await panel.isVisible().catch(() => false))) {
    await page.locator('[data-testid="nav-toggle-tests"]').click();
  }
  await expect(panel).toBeVisible();

  // Both patients render as roster rows (read-only server roster).
  const rows = panel.locator('[data-testid="ds-roster-row"]');
  await expect(rows.filter({ hasText: "r01" })).toBeVisible({ timeout: 20000 });
  await expect(rows.filter({ hasText: "r02" })).toBeVisible();

  // The source banner names the dataset (grouped-by-source contract).
  await expect(panel.locator('[data-testid="dataset-source-banner"]')).toContainText(
    /server workspace \(2 patients\)/,
  );
});

test("S22c-2: clicking a patient opens their data in the resource editor; save writes back", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);

  // Rail may start collapsed; open the Tests drawer robustly: click the
  // toggle, then confirm the PANEL holds roster rows (retry once).
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const rosterRow = page.locator('[data-testid="ds-roster-row"]').first();
  await page.locator('[data-testid="nav-toggle-tests"]').click();
  if (!(await rosterRow.isVisible().catch(() => false))) {
    await page.locator('[data-testid="nav-toggle-tests"]').click();
    await page.waitForTimeout(500);
  }
  await expect(rosterRow).toBeVisible({ timeout: 15000 });

  // Click r01's roster row -> the patient editor opens (tab + JSON).
  // Focus + Enter (the row is a role=button with keyboard activation —
  // dodges a transient rail-overlay pointer interception at this width).
  const row = panel.locator('[data-testid="ds-roster-row"]', { hasText: "r01" }).first();
  await row.focus();
  await page.keyboard.press("Enter");
  const editor = page.locator('[data-testid="patient-editor"]');
  await expect(editor).toBeVisible({ timeout: 30000 });
  // The patient's resources are listed (Patient + their Encounter).
  await expect(editor).toContainText("Rosa");
  await expect(editor).toContainText("Encounter");

  // Edit the Patient resource JSON (gender -> male) and save.
  const jsonArea = editor.locator("textarea, [contenteditable=true]").first();
  await expect(jsonArea).toBeVisible();
  const before = await jsonArea.inputValue?.().catch(() => null);
  expect(before ?? "").toContain('"female"');
  await jsonArea.fill((before ?? "").replace('"female"', '"male"'));
  await editor.locator('[data-testid="patient-save"]').click();
  await expect(editor.locator('[data-testid="patient-status"]')).toContainText(
    /saved patient r01/i,
    { timeout: 20000 },
  );

  // Data never auto-reloads (locked decision): restart the kernel, then
  // the patient endpoint (kernel-backed) reflects the edit — proving the
  // file write round-tripped through the server.
  await fetch(`${BASE}/api/kernel/restart`, { method: "POST" });
  let after: { patient?: { gender?: string } } | null = null;
  for (let i = 0; i < 10; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    const res = await (await fetch(`${BASE}/api/patient/r01`)).json();
    after = (res?.data ?? res) as { patient?: { gender?: string } };
    if (after?.patient?.gender === "male") break;
  }
  expect(after?.patient?.gender).toBe("male");
});
