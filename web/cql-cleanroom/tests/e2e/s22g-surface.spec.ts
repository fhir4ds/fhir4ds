import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S22g (§8): cell runs render INLINE ONLY — no bottom-console
// duplication for cell runs — while run history keeps BOTH surfaces
// tagged payload.surface ("console" | "cell").

const BASE = "http://127.0.0.1:19205";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s22g-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "SurfLib.cql"),
    [
      "library SurfLib version '1.0.0'",
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
    ].join("\n"),
    "utf8",
  );
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    [
      '{"resourceType":"Patient","id":"s1","gender":"female","name":[{"given":["Ann"]}]}',
      '{"resourceType":"Patient","id":"s2","gender":"male"}',
    ].join("\n") + "\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19205", "--no-open"],
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

async function openLibrary(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "SurfLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /SurfLib/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3000);
}

test("S22g-1: cell run renders inline ONLY — no console run entry", async ({ page }) => {
  await openLibrary(page);
  // Cells view (library ships with markers).
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") {
    await toggle.click();
    await page.waitForTimeout(1000);
  }
  // Run ONE cell.
  const card = page.locator('[data-testid="cell-card"]', { hasText: "Female" }).first();
  await card.locator('[data-testid="cell-run"]').click();
  await expect(card.locator('[data-testid="cell-table"]')).toBeVisible({ timeout: 60000 });

  // The bottom console shows NO new run for the cell execution: the
  // run-history switcher (last runs) carries no cell-surface entry.
  const history = await page.evaluate(() => {
    return new Promise<unknown[]>((resolve) => {
      const req = indexedDB.open("cql-cleanroom");
      req.onsuccess = () => {
        const db = req.result;
        try {
          const tx = db.transaction(["workspace"], "readonly");
          const get = tx.objectStore("workspace").get("current");
          get.onsuccess = () => {
            const rec = get.result as { runHistory?: Array<{ payload?: { surface?: string } }> } | null;
            resolve(rec?.runHistory ?? []);
          };
          get.onerror = () => resolve([]);
        } catch {
          resolve([]);
        }
      };
      req.onerror = () => resolve([]);
    });
  });
  const surfaces = history.map((r) => (r as { payload?: { surface?: string } }).payload?.surface);
  // No cell-surface run leaked into the console history.
  expect(surfaces).not.toContain("cell");

  // The cell card carries its OWN last-run log (surface: cell).
  const cellLog = card.locator('[data-testid="cell-runs"]');
  await expect(cellLog).toBeVisible();
  await expect(cellLog).toContainText(/ok|error/);
});

test("S22g-2: text-mode console run tags surface console", async ({ page }) => {
  await openLibrary(page);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(1500);
  }
  const runBtn = page.getByRole("button", { name: /^Run$/ });
  if ((await runBtn.count()) > 0) await runBtn.click();
  else await page.getByRole("button", { name: /Run All/ }).click();
  await page.waitForTimeout(12000);

  const history = await page.evaluate(() => {
    return new Promise<Array<{ payload?: { surface?: string; mode?: string } }>>((resolve) => {
      const req = indexedDB.open("cql-cleanroom");
      req.onsuccess = () => {
        const db = req.result;
        try {
          const tx = db.transaction(["workspace"], "readonly");
          const get = tx.objectStore("workspace").get("current");
          get.onsuccess = () => resolve((get.result as { runHistory?: Array<{ payload?: { surface?: string; mode?: string } }> })?.runHistory ?? []);
          get.onerror = () => resolve([]);
        } catch {
          resolve([]);
        }
      };
      req.onerror = () => resolve([]);
    });
  });
  expect(history.length).toBeGreaterThan(0);
  // The whole-library console run is tagged surface: "console".
  expect(
    history.some((r) => r.payload?.surface === "console")
  ).toBe(true);
});
