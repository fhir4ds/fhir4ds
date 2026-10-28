import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S26a bug_fix journey tests — Joel's live repro words (2026-10-21):
// (4) "switching to cms125-workspace still evaluated 3 patients" —
//     the auto-recalc heartbeat is browser-origin and evaluates the
//     in-browser default 3-patient demo dataset. JOURNEY: connected,
//     open the workspace's disk library, wait past the debounce, the
//     results table shows THE WORKSPACE's patients (not p1/p2/p3 demo
//     ids) and the run history's latest entry is server-origin.
// (5) "Valuesets pane shows nothing in connected mode" — JOURNEY:
//     connected on a canonical-layout workspace (ValueSet/ folder),
//     the nav Valuesets section lists the disk valuesets.
// (6) "click InAgeRange -> initial_population evidence" — JOURNEY:
//     click a define column cell in the results table, the evidence
//     popover titles THAT define and its own evidence (no fallback to
//     a different population's definitions).

const BASE = "http://127.0.0.1:19230";
let dir: string | null = null;
let server: ChildProcess | null = null;

// Canonical S22e layout: Library/, ValueSet/, Patient/<pid>/.
const PAT_W = {
  resourceType: "Patient",
  id: "w77",
  gender: "female",
  birthDate: "1980-05-05",
};
const PAT_M = {
  resourceType: "Patient",
  id: "w78",
  gender: "male",
  birthDate: "1972-01-02",
};

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s26a-"));
  await mkdir(join(dir, "Library"), { recursive: true });
  await mkdir(join(dir, "ValueSet"), { recursive: true });
  await mkdir(join(dir, "Patient", "w77"), { recursive: true });
  await mkdir(join(dir, "Patient", "w78"), { recursive: true });
  await writeFile(
    join(dir, "Library", "TruthLib.cql"),
    [
      "library TruthLib version '1.0.0'",
      "using FHIR version '4.0.1'",
      "include FHIRHelpers version '4.0.1' called FHIRHelpers",
      "context Patient",
      "",
      'define "IsFemale":',
      "  Patient.gender = 'female'",
      "",
      'define "AgeYears":',
      "  AgeInYearsAt(@2026-01-01)",
      "",
    ].join("\n") + "\n",
    "utf8",
  );
  await writeFile(
    join(dir, "ValueSet", "TruthVS.json"),
    JSON.stringify(
      {
        resourceType: "ValueSet",
        id: "truth-vs",
        url: "http://example.org/fhir/ValueSet/truth",
        name: "TruthVS",
        compose: {
          include: [{ system: "http://loinc.org", concept: [{ code: "8480-6" }] }],
        },
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );
  await writeFile(
    join(dir, "Patient", "w77", "Patient-w77.json"),
    JSON.stringify(PAT_W) + "\n",
    "utf8",
  );
  await writeFile(
    join(dir, "Patient", "w78", "Patient-w78.json"),
    JSON.stringify(PAT_M) + "\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19230", "--no-open"],
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
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
      await new Promise((r) => setTimeout(r, 300));
    } catch { /* already gone */ }
  }
  if (dir) await rm(dir, { recursive: true, force: true });
});

async function openWorkspaceLibrary(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel
    .locator(".nav-item", { hasText: "TruthLib" })
    .first()
    .click({ timeout: 15000 });
  await expect(
    page.getByRole("tab", { name: /TruthLib/i }),
  ).toBeVisible({ timeout: 30000 });
  // These are TEXT-editor journeys: dismiss the auto-cellify tips and
  // switch back to text view (the heartbeat is suppressed while cells
  // view is open — S23-2 doctrine).
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) await gotIt.click();
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  try {
    await toggle.waitFor({ state: "visible", timeout: 10000 });
    if ((await toggle.getAttribute("aria-checked")) === "true") {
      await toggle.click();
      await page.waitForFunction(
        () =>
          (document
            .querySelector('[data-testid="parse-status"]')
            ?.textContent ?? "").includes("parsed ✓"),
        { timeout: 30000 },
      );
    }
  } catch { /* cell toggle absent — text view already */ }
  // Let a heartbeat (or several) fire past the default 1s debounce.
  await page.waitForTimeout(6000);
}

test("S26a-1 (item 4): connected heartbeat evaluates the SERVER workspace dataset", async ({ page }) => {
  await openWorkspaceLibrary(page);

  // The results table must contain the workspace's OWN patient ids —
  // never the standalone demo's p1/p2/p3.
  const results = page.locator('[data-testid="results-table"]');
  await expect(results).toBeVisible({ timeout: 30000 });
  await expect(results).toContainText("w77", { timeout: 30000 });
  await expect(results).toContainText("w78");
  const body = await results.innerText();
  expect(body).not.toContain("p1");
  expect(body).not.toContain("p2");
  expect(body).not.toContain("p3");

  // The latest run-history entry is SERVER-origin (the heartbeat went
  // through /api/evaluate, not the in-browser worker).
  const origin = await page.evaluate(() => {
    return new Promise<string | null>((resolve) => {
      const req = indexedDB.open("cql-cleanroom");
      req.onsuccess = () => {
        const db = req.result;
        try {
          const tx = db.transaction(["workspace"], "readonly");
          const get = tx.objectStore("workspace").get("current");
          get.onsuccess = () => {
            const rec = get.result as {
              runHistory?: Array<{ payload?: { origin?: string } }>;
            } | null;
            const runs = rec?.runHistory ?? [];
            resolve(runs.length ? runs[runs.length - 1].payload?.origin ?? null : null);
          };
          get.onerror = () => resolve(null);
        } catch { resolve(null); }
      };
      req.onerror = () => resolve(null);
    });
  });
  expect(origin).toBe("server");
});

test("S26a-2 (item 5): nav Valuesets section lists disk valuesets on a canonical workspace", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  await page.locator('[data-testid="nav-toggle-valuesets"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(panel).toBeVisible();
  // S26d review fix doctrine: the disk valueset labels by NAME (not the
  // FHIR id/OID) — the fixture's ValueSet carries name "TruthVS".
  const item = panel.locator(".nav-item", { hasText: "TruthVS" }).first();
  await expect(item).toBeVisible({ timeout: 20000 });
});

test("S26a-3 (item 6): clicking a define column explains THAT define", async ({ page }) => {
  await openWorkspaceLibrary(page);

  // Click the IsFemale cell for patient w77 — the popover must title
  // IsFemale and show IsFemale's OWN evidence (Patient/w77 gender),
  // never another define's. (The original repro: clicking one define
  // showed initial_population/Encounter/gender evidence via the
  // all-definitions fallback.)
  const cell = page.locator('[data-testid="cell-w77-IsFemale"]');
  await expect(cell).toBeVisible({ timeout: 30000 });
  const pop = page.locator('[data-testid="evidence-popover"]');
  // The first explain can race under full-suite load (server cold
  // start) — click, and if no def section lands within a short window,
  // re-click once (the popover closes on re-open; a fresh explain fires).
  for (let attempt = 0; attempt < 2; attempt++) {
    await cell.click();
    await expect(pop).toBeVisible({ timeout: 30000 });
    try {
      await pop
        .locator(".dataset-type-name")
        .first()
        .waitFor({ state: "visible", timeout: 20000 });
      break;
    } catch {
      if (attempt === 1) throw new Error("IsFemale explain never landed a definition section");
      await pop.locator('[data-testid="evidence-popover-close"]').click().catch(() => {});
    }
  }
  await expect(pop.locator("h3")).toContainText("IsFemale");
  await expect(pop.locator("h3")).toContainText("w77");
  // IsFemale's own evidence row: the patient's gender comparison.
  await expect(
    pop.locator('[data-testid="evidence-row-0"]'),
  ).toContainText("Patient/w77", { timeout: 15000 });
  await expect(pop.locator('[data-testid="evidence-row-0"]')).toContainText(
    "gender",
  );
  await pop.locator('[data-testid="evidence-popover-close"]').click();

  // A non-boolean define (AgeYears — patient-property derived): S26
  // item 7 — the evidence popover shows the PATIENT-PROPERTY leaf
  // (birthDate-derived age), not the "no evidence recorded" placeholder.
  const ageCell = page.locator('[data-testid="cell-w77-AgeYears"]');
  await expect(ageCell).toBeVisible({ timeout: 30000 });
  await ageCell.click();
  const pop2 = page.locator('[data-testid="evidence-popover"]');
  await expect(pop2).toBeVisible({ timeout: 30000 });
  await expect(pop2.locator("h3")).toContainText("AgeYears");
  // The property leaf: target Patient/w77, attribute birthDate, the age
  // value, operator "derived".
  const leaf = pop2.locator('[data-testid="evidence-row-0"]');
  await expect(leaf).toBeVisible({ timeout: 30000 });
  await expect(leaf).toContainText("Patient/w77");
  await expect(leaf).toContainText("birthDate");
  await expect(leaf).toContainText("derived");
});
