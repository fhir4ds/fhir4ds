import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S27-3 REPRO: Joel's browser carries an IndexedDB workspace from an
// earlier session (expectedReports authored for the OLD 6 MADiE cases,
// patient ids BCS*). The run now has 66 UUID patients. If the persisted
// expectations are restored and NOT superseded by the disk store, every
// expected patient is absent from the run → every compare cell reads
// "exp true · got —". This seeds exactly that state and boots connected.

const BASE = "http://127.0.0.1:19235";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", "/mnt/d/fhir4ds/examples/cms125-workspace", "--port", "19235", "--no-open"],
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
    } catch {
      /* gone */
    }
  }
});

function oldReport(pid: string) {
  return {
    resourceType: "MeasureReport",
    id: `expected-${pid}`,
    status: "complete",
    type: "individual",
    subject: { reference: `Patient/${pid}` },
    group: [
      {
        id: "Group_1",
        population: [
          { code: { coding: [{ code: "initial-population" }] }, count: 1 },
          { code: { coding: [{ code: "denominator" }] }, count: 1 },
          { code: { coding: [{ code: "denominator-exclusion" }] }, count: 0 },
          { code: { coding: [{ code: "numerator" }] }, count: 0 },
        ],
      },
    ],
  };
}

test("S27-3: stale persisted expectedReports must not break the compare", async ({ page }) => {
  // 1. Establish the origin, then seed the stale workspace record.
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(4000);
  await page.evaluate(async (reports: unknown[]) => {
    const db: IDBDatabase = await new Promise((resolve, reject) => {
      const req = indexedDB.open("cql-cleanroom", 1);
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains("workspace")) {
          req.result.createObjectStore("workspace");
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    const record = {
      schemaVersion: 7,
      libraries: [],
      dataset: null,
      cases: null,
      prefs: {},
      measures: [
        {
          id: "msr_0",
          mainLibraryId: "lib_0",
          resource: {
            resourceType: "Measure",
            id: "CMS125FHIRBreastCancerScreening",
            name: "CMS125FHIRBreastCancerScreening",
            library: ["CMS125FHIRBreastCancerScreening"],
            group: [],
          },
        },
      ],
      activeMeasureId: "msr_0",
      expectedReports: { msr_0: reports },
      viewDefs: [],
      paramValues: {},
      runHistory: [],
      activeTabPref: "cql",
      terminology: { valuesets: [] },
      viewConfig: null,
      savedAt: Date.now(),
    };
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("workspace", "readwrite");
      tx.objectStore("workspace").put(record, "current");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  }, ["BCSDenominatorPass", "BCSNumeratorObservationPass"].map(oldReport));

  // 2. Hard reload: restore runs, then the connected boot adopts disk.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(18000);

  // 3. Expected Results > CMS125 > Compare (Joel's path).
  await page.locator('[data-testid="nav-toggle-expected"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel.locator(".nav-item", { hasText: "CMS125" }).first().click({ timeout: 30000 });
  await page.locator('[data-testid="console-tab-compare"]').click({ timeout: 30000 });

  const chip = page.locator('[data-testid="tests-summary"]');
  await expect(chip).toBeVisible({ timeout: 60000 });
  const chipText = (await chip.textContent()) ?? "";
  const firstMiss = await page
    .locator('[data-testid^="compare-"]')
    .first()
    .textContent()
    .catch(() => "(none)");
  console.log("CHIP:", chipText, "| FIRST CELL:", firstMiss);

  // The disk store (66 official cases) must win over the stale seed.
  await expect(chip).toContainText("264/264 passed", { timeout: 90000 });
});
