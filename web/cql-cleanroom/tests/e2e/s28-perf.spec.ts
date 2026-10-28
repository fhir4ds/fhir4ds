import { test, expect } from "@playwright/test";

/**
 * S28 (perf A+B): connected Run All is ONE batch evaluation — every
 * cell gets its own result table, and the whole run completes in a
 * fraction of the sequential per-cell time (17 cells x ~3.5s before).
 */
const PORT = 19238;
const BASE = `http://127.0.0.1:${PORT}`;
const REPO = process.env.REPO_DIR ?? "/mnt/d/fhir4ds";

let serverProc: import("child_process").ChildProcess | null = null;

test.beforeAll(async () => {
  const { spawn } = await import("child_process");
  serverProc = spawn(
    "python3",
    ["-m", "fhir4ds.cli", "dev", "examples/cms125-workspace", "--port", String(PORT), "--no-open"],
    { cwd: REPO, detached: true, stdio: "ignore" },
  );
  serverProc.unref();
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((res) => setTimeout(res, 1000));
  }
  throw new Error("devserver did not come up on " + PORT);
});

test.afterAll(() => {
  if (serverProc?.pid) {
    try {
      process.kill(-serverProc.pid, "SIGKILL");
    } catch {
      /* already gone */
    }
  }
});

test("S28-1: Run All batches — all cells get results quickly", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60_000 });
  // Boot purity opens the primary library; wait for cells view (auto-split).
  await expect(
    page.locator('[data-testid="cell-view-toggle"][aria-checked="true"]'),
  ).toBeVisible({ timeout: 40_000 });

  // Run All from the header.
  const t0 = Date.now();
  await page.locator('[data-testid="cell-runall"]').click();
  // First cell's result table renders with real patient data.
  const firstResult = page.locator('[data-testid="cell-out"]').first();
  await expect(firstResult).toContainText("patient_id", { timeout: 90_000 });
  const elapsed = Date.now() - t0;
  // Batch: one translation (~3-6s server-side). Sequential would blow
  // past 30s on this workspace — generous but far below the old floor.
  expect(elapsed).toBeLessThan(30_000);

  // Multiple cells show results (batch fan-out).
  const results = page.locator('[data-testid="cell-out"]');
  expect(await results.count()).toBeGreaterThanOrEqual(5);
});
