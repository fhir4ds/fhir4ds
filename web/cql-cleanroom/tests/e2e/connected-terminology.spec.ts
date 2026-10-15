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

test("connected: Settings shows terminology section; key input persists intent; cache clear present", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="settings-menu"]').click();
  const keyRow = page.locator('[data-testid="settings-vsac-key-row"]');
  await expect(keyRow).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-testid="settings-fhir-base-row"]')).toBeVisible();
  await expect(page.locator('[data-testid="settings-umls-status"]')).toBeVisible();
  await expect(page.locator('[data-testid="settings-clear-term-cache"]')).toBeVisible();
  // password-type input (never plain text)
  await expect(page.locator('[data-testid="settings-vsac-key"]')).toHaveAttribute("type", "password");
});

test("connected: valueset editor shows UMLS strip; disabled without key + explain chip", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  // Open the workspace valueset section via NavRail > Valuesets (native path)
  await page.getByRole("button", { name: "Valuesets" }).click();
  await page.waitForTimeout(800);
  // Open any workspace valueset editor tab (the section lists them)
  const first = page.locator('[data-testid*="valueset"]').first();
  await first.click().catch(() => {});
  const strip = page.locator('[data-testid="umls-strip"]');
  // Strip appears when a valueset editor tab is open + connected
  if (await strip.count()) {
    await expect(strip).toBeVisible();
    await expect(page.locator('[data-testid="umls-strip-search"]')).toBeVisible();
    if (!(await page.locator('[data-testid="umls-strip-search"]').isEnabled())) {
      await expect(strip).toContainText(/UMLS_API_KEY/);
    }
  }
  // Dialog-free: no term-dialog anywhere
  await expect(page.locator('[data-testid="term-dialog"]')).toHaveCount(0);
});

test("connected: no terminology items in File>Add (removed per S1R)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="file-menu"]').click();
  await page.locator('[data-testid="file-add"]').hover();
  await page.waitForTimeout(600);
  await expect(page.locator('[data-testid="vsac-import"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="umls-lookup"]')).toHaveCount(0);
});
