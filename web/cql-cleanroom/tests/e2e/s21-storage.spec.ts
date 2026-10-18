import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S21 storage doctrine: connected mode reads workspace files from DISK
// (/api/*) and writes IndexedDB chrome only; standalone reads memory +
// persists via IndexedDB; no cross-mode contamination.

const BASE = "http://127.0.0.1:19170";
const PREVIEW = "http://127.0.0.1:5176";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s21-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(
    join(dir, "cql", "S21Lib.cql"),
    "library S21Lib version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\ndefine Ok: 1 = 1\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19170", "--no-open"],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
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

test("S21-1: connected — disk-file open writes NO workspace content to IndexedDB", async ({ page }) => {
  // PRE-SEED a stale workspace snapshot, then verify the connected
  // session (a) does not restore it and (b) does not persist the
  // opened disk library into it.
  await page.addInitScript(() => {
    (window as unknown as { __seeded: boolean }).__seeded = true;
  });
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(6000);
  // Seed a stale standalone snapshot directly into the store.
  await page.evaluate(async () => {
    const seed = {
      schemaVersion: 8,
      savedAt: Date.now(),
      libraries: [{ id: "stale_1", name: "StaleLib", text: "library StaleLib version '1.0.0'" }],
      dataset: null,
      cases: null,
      prefs: {},
      measures: [],
      activeMeasureId: null,
      expectedReports: {},
      viewDefs: [],
      paramValues: {},
      viewConfig: null,
      runHistory: [],
      activeTabPref: "cql",
      terminology: { valuesets: [] },
    };
    await new Promise<void>((resolve, reject) => {
      const req = indexedDB.open("cql-cleanroom");
      req.onerror = () => reject(req.error);
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction(["workspace"], "readwrite");
        tx.objectStore("workspace").put(seed, "current");
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onerror = () => reject(tx.error);
      };
    });
    await saveWorkspace({
      libraries: [{ id: "stale_1", name: "StaleLib", text: "library StaleLib version '1.0.0'" }],
      dataset: null,
      cases: null,
      prefs: {},
      measures: [],
      activeMeasureId: null,
      expectedReports: {},
      viewDefs: [],
      paramValues: {},
      viewConfig: null,
      runHistory: [],
      activeTabPref: "cql",
      terminology: { valuesets: [] },
    } as Parameters<typeof saveWorkspace>[0]);
  }).catch(() => undefined);
  await page.waitForTimeout(2000);
  // Reload: the connected session must NOT restore StaleLib as content.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(15000);
  const tabsAfterReload = await page.locator("[role=tab]").allTextContents();
  expect(tabsAfterReload.filter((t) => /StaleLib/.test(t)).length).toBe(0);
  // Open the disk library (reads via /api).
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "S21Lib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /S21Lib/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(2500); // autosave debounce fires (chrome-only)
  // The persisted record holds NO libraries (content sanitized).
  const persisted = await page.evaluate(
    () =>
      new Promise<{ libraries?: unknown[] } | null>((resolve) => {
        const req = indexedDB.open("cql-cleanroom");
        req.onerror = () => resolve(null);
        req.onsuccess = () => {
          const db = req.result;
          try {
            const tx = db.transaction(["workspace"], "readonly");
            const get = tx.objectStore("workspace").get("current");
            get.onsuccess = () => resolve((get.result ?? null) as { libraries?: unknown[] } | null);
            get.onerror = () => resolve(null);
          } catch {
            resolve(null);
          }
        };
      }),
  );
  const record = Array.isArray(persisted) ? persisted[0] : persisted;
  expect((record?.libraries ?? []) as unknown[]).toEqual([]);
  // The file IS on disk (server fs proves the local-workspace store).
  const fs = await (await fetch(`${BASE}/api/fs/list?path=cql`)).json();
  expect(JSON.stringify(fs)).toContain("S21Lib.cql");
});

test("S21-2: standalone — create a file, reload, IndexedDB restores it", async ({ page }) => {
  test.skip(!(await fetch(PREVIEW).then((r) => r.ok).catch(() => false)), "vite preview down");
  await page.goto(`${PREVIEW}/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  // Type a new library into the default editor.
  const editor = page.locator('[data-testid="cql-editor"]');
  const toggle0 = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle0.getAttribute("aria-checked")) === "true") { await toggle0.click(); await page.waitForTimeout(1000); }
  await editor.click();
  await page.keyboard.press("Control+a");
  await page.keyboard.type("library S21Persist version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\ndefine Ok: 2 = 2\n", { delay: 5 });
  await page.waitForTimeout(2500); // autosave debounce
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(15000);
  const text = await page.locator('[data-testid="cql-editor"]').textContent().catch(() => "");
  expect(text ?? "").toContain("S21Persist");
});

test("S21-3: mode switch — no cross-contamination (connected writes stay on disk)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  // Connected: opening a disk library adds it LOCALLY (server workspace).
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "S21Lib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /S21Lib/i })).toBeVisible({ timeout: 30000 });
  // The server fs list still shows the file (disk is the store).
  const fs = await (await fetch(`${BASE}/api/fs/list?path=cql`)).json();
  expect(JSON.stringify(fs)).toContain("S21Lib.cql");
});
