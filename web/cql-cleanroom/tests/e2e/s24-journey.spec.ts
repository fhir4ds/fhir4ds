import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S24 journey tests (from Joel's checkpoint words + the published docs):
// (1) "editing cells STILL shows e2e results in the bottom console" —
//     type a REAL edit in a cell, wait past the debounce, console
//     receives NO new run.
// (2) stray text above the results table — the cell output region
//     carries ONLY the table (no leftover labels).
// (3) data section = patient list BY ID with resource-count chips;
//     click -> slideout of that patient's resources grouped BY TYPE.
//     The 'Live dataset:' banner is REMOVED entirely.

const BASE = "http://127.0.0.1:19220";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s24-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "JourneyLib.cql"),
    [
      "library JourneyLib version '1.0.0'",
      "using FHIR version '4.0.1'",
      "include FHIRHelpers version '4.0.1' called FHIRHelpers",
      "context Patient",
      "",
      "// # %% [name: Female]",
      'define "Female":',
      "  Patient.gender = 'female'",
      "",
      "// # %% [name: HasEnc]",
      'define "HasEnc":',
      "  exists([Encounter] E where E.status = 'finished')",
      "",
    ].join("\n"),
    "utf8",
  );
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    [
      '{"resourceType":"Patient","id":"j1","gender":"female","name":[{"given":["Jo"]}]}',
      '{"resourceType":"Encounter","id":"je1","status":"finished","subject":{"reference":"Patient/j1"}}',
      '{"resourceType":"Observation","id":"jo1","status":"final","subject":{"reference":"Patient/j1"}}',
      '{"resourceType":"Patient","id":"j2","gender":"male"}',
    ].join("\n") + "\n",
    "utf8",
  );
  for (let attempt = 0; attempt < 3; attempt++) {
    server = spawn(
      "/usr/bin/python3",
      ["-m", "fhir4ds.cli", "dev", dir, "--port", "19220", "--no-open"],
      {
        cwd: "/mnt/d/fhir4ds",
        env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
        stdio: "ignore",
      },
    );
    let ok = false;
    for (let i = 0; i < 30; i++) {
      try {
        const r = await fetch(`${BASE}/health`);
        if (r.ok) { ok = true; break; }
      } catch { /* not up yet */ }
      await new Promise((r) => setTimeout(r, 1000));
    }
    if (ok) return;
    if (server.pid) { try { process.kill(server.pid); } catch { /* gone */ } }
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

async function openCells(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "JourneyLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /JourneyLib/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") {
    await toggle.click();
    await page.waitForTimeout(1500);
  }
}

test("S24-1: typing a real cell edit does NOT leak a run into the console", async ({ page }) => {
  await openCells(page);
  const historyCount = () =>
    Promise.race([
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
            } catch { resolve(-1); }
          };
          req.onerror = () => resolve(-1);
        });
      }),
      new Promise<number>((r) => setTimeout(() => r(-1), 5000)),
    ]);
  const before = await historyCount();

  // TYPE a real edit into the first cell's Monaco (Joel's exact flow).
  const monaco = page.locator('[data-testid="cell-card"]').first().locator(".view-lines").first();
  await monaco.click({ timeout: 15000 });
  await page.keyboard.press("Control+End");
  await page.keyboard.type("\n// s24 real edit", { delay: 5 });
  // Wait WELL past the 2s debounce — a leaked heartbeat would land here.
  await page.waitForTimeout(9000);

  const after = await historyCount();
  expect(after).toBe(before);
});

test("S24-2: nothing above the cell results table but the table", async ({ page }) => {
  await openCells(page);
  const card = page.locator('[data-testid="cell-card"]', { hasText: "Female" }).first();
  await card.locator('[data-testid="cell-run"]').click();
  const table = card.locator('[data-testid="cell-table"]');
  await expect(table).toBeVisible({ timeout: 60000 });

  // The output region contains ONLY the table text (plus the optional
  // locally-computed badge) — no stray labels, captions, or funnel text.
  const outText = ((await card.locator('[data-testid="cell-out"]').textContent()) ?? "").trim();
  const tableText = ((await table.textContent()) ?? "").trim();
  const above = outText.replace(tableText, "")
    .replace("computed locally", "").trim();
  expect(above).toBe("");
});

test("S24-3: data section = patient list with chips; click -> type-grouped slideout", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);

  // The banner is GONE entirely (rider a).
  await page.locator('[data-testid="nav-toggle-tests"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const rosterRow = panel.locator('[data-testid="ds-roster-row"]').first();
  if (!(await rosterRow.isVisible().catch(() => false))) {
    await page.locator('[data-testid="nav-toggle-tests"]').click();
    await page.waitForTimeout(800);
  }
  await expect(rosterRow).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="dataset-source-banner"]')).toHaveCount(0);

  // Patients listed BY ID with a resource-count chip (j1 owns 3
  // resources incl its Patient row; j2 owns 1).
  const j1 = panel.locator('[data-testid="ds-roster-row"]', { hasText: "j1" }).first();
  await expect(j1).toBeVisible();
  await expect(j1.locator('[data-testid="ds-roster-count"]')).toHaveText("3");

  // Click j1 -> slideout lists their resources grouped BY TYPE.
  await j1.click();
  const slideout = page.locator('[data-testid="ds-patient-slideout"]');
  await expect(slideout).toBeVisible({ timeout: 15000 });
  const types = await slideout.locator('[data-testid="ds-slideout-type"]').allTextContents();
  const typeNames = types.map((t) => t.replace(/\d+.*$/, "").trim());
  expect(typeNames).toEqual(expect.arrayContaining(["Encounter", "Observation", "Patient"]));
  // Closing works.
  await slideout.locator('[data-testid="ds-slideout-close"]').click();
  await expect(slideout).toHaveCount(0);
});
