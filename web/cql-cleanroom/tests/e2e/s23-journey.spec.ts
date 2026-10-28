import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S23 journey tests (derived from PLAN §8's own words, not slice
// mechanics): "text editor mode -> results at the bottom console (as
// today); CELL mode -> results inline per cell ONLY, no
// bottom-console duplication for cell runs."
//
// Gap 1 (S23-1): text-mode whole-library Run must show ALL define
// columns — the measure-mapped narrowing belongs to the measure
// surface, not the text editor's Run.
// Gap 2 (S23-2): with cells open, editing a cell must NOT leak a new
// run into the bottom console (auto-recalc heartbeat suppressed while
// cell view is open).

const BASE = "http://127.0.0.1:19215";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s23-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "SixLib.cql"),
    [
      "library SixLib version '1.0.0'",
      "using FHIR version '4.0.1'",
      "include FHIRHelpers version '4.0.1' called FHIRHelpers",
      "context Patient",
      "",
      "// # %% [name: Female]",
      'define "Female":',
      "  Patient.gender = 'female'",
      "",
      "// # %% [name: Named]",
      'define "Named":',
      "  Patient.name.first().given.first() is not null",
      "",
      "// # %% [name: Young]",
      'define "Young":',
      "  AgeInYearsAt(@2024-01-01) < 40",
      "",
      "// # %% [name: HasEnc]",
      'define "HasEnc":',
      "  exists([Encounter] E where E.status = 'finished')",
      "",
      "// # %% [name: FemaleAndYoung]",
      'define "FemaleAndYoung":',
      '  "Female" and "Young"',
      "",
      "// # %% [name: SummaryTuple]",
      'define "SummaryTuple":',
      '  Tuple { female: "Female", young: "Young" }',
      "",
    ].join("\n"),
    "utf8",
  );
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    [
      '{"resourceType":"Patient","id":"q1","gender":"female","birthDate":"1995-04-04","name":[{"given":["Zoe"]}]}',
      '{"resourceType":"Encounter","id":"qe1","status":"finished","subject":{"reference":"Patient/q1"}}',
      '{"resourceType":"Patient","id":"q2","gender":"male","birthDate":"1970-01-01"}',
    ].join("\n") + "\n",
    "utf8",
  );
  // Retry spawn: a previous worker's server teardown can hold :19215
  // briefly — bind failures surface as an unhealthy endpoint, never an
  // exception, so re-spawn up to 3 times.
  for (let attempt = 0; attempt < 3; attempt++) {
    server = spawn(
      "/usr/bin/python3",
      ["-m", "fhir4ds.cli", "dev", dir, "--port", "19215", "--no-open"],
      {
        cwd: "/mnt/d/fhir4ds",
        env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
        stdio: "ignore",
      },
    );
    for (let i = 0; i < 30; i++) {
      try {
        const r = await fetch(`${BASE}/health`);
        if (r.ok) return;
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    // Bind likely failed — kill and retry.
    if (server.pid) {
      try {
        process.kill(server.pid);
      } catch {
        /* already gone */
      }
    }
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

async function openLibrary(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "SixLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /SixLib/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3000);
}

test("S23-1: text-mode whole-library Run shows ALL define columns (journey)", async ({ page }) => {
  await openLibrary(page);

  // A measure IS active (the default demo measure maps populations) —
  // the journey: the TEXT EDITOR's Run still shows every define.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(1500);
  }
  const runBtn = page.getByRole("button", { name: /^Run$/ });
  if ((await runBtn.count()) > 0) await runBtn.click();
  else await page.getByRole("button", { name: /Run All/ }).click();

  // ALL 6 defines render as columns in the bottom console table.
  const header = page.locator('[data-testid="results-table"] thead');
  await expect(header).toBeVisible({ timeout: 60000 });
  for (const col of ["Female", "Named", "Young", "HasEnc", "FemaleAndYoung", "SummaryTuple"]) {
    await expect(header).toContainText(col, { timeout: 10000 });
  }
});

test("S23-2: cell view suppresses the auto-recalc console leak (journey)", async ({ page }) => {
  await openLibrary(page);

  // Switch to CELLS view (the library ships with markers).
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") {
    await toggle.click();
    await page.waitForTimeout(1500);
  }

  // Baseline: note the console's persisted run history length.
  const historyCount = async () =>
    page.evaluate(() => {
      return new Promise<number>((resolve) => {
        const req = indexedDB.open("cql-cleanroom");
        req.onsuccess = () => {
          const db = req.result;
          try {
            const tx = db.transaction(["workspace"], "readonly");
            const get = tx.objectStore("workspace").get("current");
            get.onsuccess = () => {
              const rec = get.result as { runHistory?: unknown[] } | null;
              resolve(rec?.runHistory?.length ?? 0);
            };
            get.onerror = () => resolve(-1);
          } catch {
            resolve(-1);
          }
        };
        req.onerror = () => resolve(-1);
      });
    });
  const before = await historyCount();
  console.log("[S23-2] before:", before);

  // Edit a cell's text (splices the master buffer -> would fire the
  // auto-recalc heartbeat). Type into the first cell's Monaco editor
  // (bounded waits — the S23-2 hang was an unbounded interaction).
  console.log("[S23-2] typing into cell editor");
  const monaco = page.locator('[data-testid="cell-card"]').first().locator(".view-lines").first();
  await monaco.click({ timeout: 15000 });
  console.log("[S23-2] monaco clicked");
  await page.keyboard.press("Control+End");
  await page.keyboard.type("\n// s23 edit", { delay: 5 });
  console.log("[S23-2] typed");
  // Debounce is ~2s; auto-recalc would land a NEW console run.
  await page.waitForTimeout(8000);

  const after = await historyCount();
  console.log("[S23-2] after:", after);
  // No new console run while cell view is open (manual runs only).
  expect(after).toBe(before);

  // And the console shows no fresh table for the leaked run (the
  // displayed console would have re-rendered with new results). Bounded
  // — an unguarded locator.textContent() can hang the runner teardown.
  const summaryText =
    (await page
      .locator('[data-testid="results-summary"]')
      .textContent({ timeout: 5000 })
      .catch(() => "")) ?? "";
  expect(summaryText).not.toContain("s23");
});
