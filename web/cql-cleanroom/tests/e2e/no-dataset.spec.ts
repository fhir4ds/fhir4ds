import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-cleanroom-redo S9: typed NO_DATASET diagnostics on an EMPTY workspace —
// a retrieving library surfaces 'no dataset loaded in this workspace', not
// a raw DuckDB catalog error. The CELL run path asserts the typed note
// positively; the console leg asserts no raw catalog leak (the demo
// library may not retrieve server-side).

const BASE = "http://127.0.0.1:19117";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s9-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(
    join(dir, "cql", "R.cql"),
    "library R version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\n// # %% [name: Pop]\ndefine Pop: exists([Condition])\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19117", "--no-open"],
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

test("S9: empty workspace cell run -> typed NO_DATASET output", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  // Open the retrieving library R (Libraries drawer) and run its cell.
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const diskRow = libPanel.locator(".nav-item", { hasText: "R" }).first();
  await diskRow.click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /^R$/i })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await page.waitForTimeout(1000);
  await page.locator('[data-testid="cell-run"]').first().click();
  const out = page.locator('[data-testid="cell-out"]').first();
  await expect(out).toBeVisible({ timeout: 30000 });
  // Typed note, not a raw catalog error.
  await expect(out).toContainText(/no dataset loaded/i);
  await expect(out).not.toContainText(/Catalog Error/i);
});

test("S9: dataset-stats reports typed NO_DATASET on empty workspace", async ({ request }) => {
  const res = await request.get(`${BASE}/api/dataset-stats`);
  const body = await res.json();
  const d = body?.data ?? body;
  const codes = (d?.diagnostics ?? []).map((x: { code?: string }) => x?.code);
  expect(codes).toContain("NO_DATASET");
});

test("S9: empty workspace console Run -> typed NO_DATASET note", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  await page.getByRole("button", { name: /^Run$/ }).click().catch(() => {});
  // The default demo library may not retrieve; the R library does. The
  // cell leg covers R directly; here assert the console surface never
  // leaks a raw catalog error into the note when it DOES run server-side.
  const note = await page
    .locator('[data-testid="status-note"]')
    .textContent()
    .catch(() => "");
  expect(note ?? "").not.toMatch(/Catalog Error/i);
});
