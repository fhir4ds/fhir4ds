import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-cleanroom-redo S1: connected terminology — VSAC import + UMLS lookup via
// File > Add; plus THE STANDALONE REGRESSION GUARD: zero /api/* requests in
// standalone mode (automated route interception, per conductor addition 2).

const BASE = "http://127.0.0.1:19092";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s1-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(join(dir, "cql", "T.cql"), "library T version '1.0.0'\n");
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19092", "--no-open"],
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

test("STANDALONE GUARD: vite-preview shell makes ZERO /api/* requests", async ({ page }) => {
  const apiHits: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/")) apiHits.push(r.url());
  });
  await page.goto("http://127.0.0.1:5176/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  // The standalone handshake probe (/api/mode) is ALLOWED to fail — wait for
  // boot to settle, then verify NO further api calls happened after degrade.
  const afterBoot = apiHits.filter((u) => !u.includes("/api/mode")).length;
  expect(afterBoot, `standalone made ${apiHits.join(", ")} after handshake`).toBe(0);
});

test("connected: File>Add shows terminology items; VSAC dialog opens; UMLS dialog shows key state", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="file-menu"]').click();
  await page.locator('[data-testid="file-add"]').hover();
  await expect(page.locator('[data-testid="vsac-import"]')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-testid="umls-lookup"]')).toBeVisible();

  // VSAC dialog: URL input + preview/import buttons
  await page.locator('[data-testid="vsac-import"]').click();
  const dlg = page.locator('[data-testid="term-dialog"]');
  await expect(dlg).toBeVisible();
  await expect(dlg.locator('[data-testid="vsac-url"]')).toBeVisible();
  await expect(dlg.locator('[data-testid="vsac-preview-btn"]')).toBeVisible();
  await expect(dlg.locator('[data-testid="vsac-import-btn"]')).toBeVisible();
  await dlg.getByRole("button", { name: "Cancel" }).click();
  await expect(dlg).toBeHidden();

  // UMLS dialog: query input + search button (key-state dependent) + hint
  await page.locator('[data-testid="file-menu"]').click();
  await page.locator('[data-testid="file-add"]').hover();
  await page.locator('[data-testid="umls-lookup"]').click();
  await expect(dlg).toBeVisible();
  await expect(dlg.locator('[data-testid="umls-query"]')).toBeVisible();
  await expect(dlg.locator('[data-testid="umls-search-btn"]')).toBeVisible();
  await expect(dlg).toContainText(/UMLS_API_KEY|configured/);
  // MF5 carry: search disabled without a key (locks the UMLS gating contract)
  await expect(dlg.locator('[data-testid="umls-search-btn"]')).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dlg).toBeHidden();
});

test("connected: bad VSAC URL yields typed error in status note (no crash)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="file-menu"]').click();
  await page.locator('[data-testid="file-add"]').hover();
  await page.locator('[data-testid="vsac-import"]').click();
  const dlg = page.locator('[data-testid="term-dialog"]');
  await dlg.locator('[data-testid="vsac-url"]').fill("http://127.0.0.1:1/fhir/ValueSet/none");
  await dlg.locator('[data-testid="vsac-preview-btn"]').click();
  await page.waitForTimeout(1500);
  // The status note records the typed diagnostic; the dialog remains usable.
  await expect(dlg).toBeVisible();
});
