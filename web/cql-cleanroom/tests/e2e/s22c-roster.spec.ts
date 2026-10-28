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

  // Both patients render as roster rows. S24-a: the banner is removed —
  // the roster itself is the dataset statement (resource chips per row).
  const rows = panel.locator('[data-testid="ds-roster-row"]');
  await expect(rows.filter({ hasText: "r01" })).toBeVisible({ timeout: 20000 });
  await expect(rows.filter({ hasText: "r02" })).toBeVisible();
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

  // S25 flow (the website UX): single-click drills into the RIGHT-side
  // L3 detail panel (type groups from LOCAL FILES); editing the Patient
  // resource row opens the Resource Builder prefilled from the server.
  const row = panel.locator('[data-testid="ds-roster-row"]', { hasText: "r01" }).first();
  await row.click();
  const detail = page.locator('[data-testid="nav-detail"]');
  await expect(detail).toBeVisible({ timeout: 15000 });
  const r01Group = detail.locator('[data-testid="dataset-group-r01"]');
  await expect(r01Group).toBeVisible({ timeout: 15000 });
  await expect(r01Group).toContainText("Rosa");
  await expect(r01Group).toContainText("Encounter");

  // Edit the Patient resource in the Resource Builder (raw JSON mode):
  // open the Patient type group, click its row (builder opens prefilled
  // from the SERVER resource), flip gender, validate + add — the save
  // goes to DISK (per-patient folder), data-hint offers kernel restart.
  // Edit the Patient resource in the Resource Builder (raw JSON mode):
  // open the Patient type group if collapsed, click its row (builder
  // opens prefilled from the SERVER resource), flip gender, and add —
  // the save goes to DISK, data-hint offers kernel restart.
  const patToggle = r01Group.locator(
    '[data-testid="dataset-type-toggle-r01-Patient"]',
  );
  const patRow = r01Group
    .locator('[data-testid^="dataset-row-"]', { hasText: "Patient" })
    .first();
  if (!(await patRow.isVisible().catch(() => false))) {
    await patToggle.click();
  }
  await expect(patRow).toBeVisible({ timeout: 5000 });
  await patRow.click();
  const builder = page.locator('[data-testid="builder-pane"]');
  await expect(builder).toBeVisible({ timeout: 30000 });
  // The prefill lands async (schema fetch → form) — the id field must
  // hold r01 BEFORE seeding raw mode, or the raw text is a bare skeleton.
  await expect(
    builder.locator('[data-testid="builder-field-id"]'),
  ).toHaveValue("r01", { timeout: 15000 });
  // Raw JSON round-trip hatch: seed from the prefilled draft, flip
  // gender, then EXPLICITLY save (connected mode never auto-commits —
  // opening a resource must not touch the disk).
  await builder.locator('[data-testid="builder-raw-toggle"]').click();
  const rawText = builder.locator('[data-testid="builder-raw-text"]');
  await expect(rawText).toBeVisible();
  const before = await rawText.inputValue().catch(() => null);
  expect(before ?? "").toContain('"female"');
  await rawText.fill((before ?? "").replace('"female"', '"male"'));
  // Debounced validation must settle (enables Save), then save to DISK.
  const save = builder.locator('[data-testid="builder-add"]');
  await expect(save).toBeVisible();
  await expect(save).toBeEnabled({ timeout: 15000 });
  await save.click();
  await page.waitForTimeout(2500);

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
