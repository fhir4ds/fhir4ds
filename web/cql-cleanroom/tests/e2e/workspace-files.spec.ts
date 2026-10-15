import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-cleanroom-redo S2: workspace files panel (connected) — NavRail gains a
// Workspace section listing server cql/valuesets via /api/fs/list; CQL click
// opens the library in the native editor; valueset click opens the native
// valueset editor; standalone shows the connect hint.

const BASE = "http://127.0.0.1:19096";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s2b-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "valuesets"), { recursive: true });
  await writeFile(
    join(dir, "cql", "WsLib.cql"),
    "library WsLib version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\ndefine \"OK\": 1 = 1\n",
  );
  await writeFile(
    join(dir, "valuesets", "vs1.json"),
    '{"resourceType":"ValueSet","id":"wsvs","url":"http://example.org/ws/vs1","compose":{"include":[{"system":"http://loinc.org","concept":[{"code":"1","display":"one"}]}]}}',
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19096", "--no-open"],
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

test("connected: Workspace nav section lists server files by group", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-workspace"], button:has-text("Workspace")').first().click();
  const panel = page.locator('[data-testid="ws-files"]').first();
  await expect(panel).toBeVisible({ timeout: 15000 });
  await expect(panel.locator('[data-testid="ws-group-cql"]')).toContainText("WsLib.cql");
  await expect(panel.locator('[data-testid="ws-group-valuesets"]')).toContainText("vs1.json");
  await expect(panel.locator('[data-testid="ws-files-refresh"]')).toBeVisible();
});

test("connected: CQL click opens the library in the native editor", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-workspace"], button:has-text("Workspace")').first().click();
  const panel = page.locator('[data-testid="ws-files"]').first();
  await expect(panel).toBeVisible({ timeout: 15000 });
  await panel.locator('[data-testid="ws-file-cql-WsLib.cql"]').click();
  // The library opens as a native editor tab (tab bar gains WsLib).
  await expect(page.getByRole("tab", { name: /WsLib/i })).toBeVisible({ timeout: 15000 });
});

test("connected: valueset click opens the native valueset editor", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-workspace"], button:has-text("Workspace")').first().click();
  const panel = page.locator('[data-testid="ws-files"]').first();
  await expect(panel).toBeVisible({ timeout: 15000 });
  await panel.locator('[data-testid="ws-file-valuesets-vs1.json"]').click();
  await expect(page.locator('[data-testid="valueset-editor"], [data-testid="valueset-code-count"]').first()).toBeVisible({ timeout: 15000 });
});

test("STANDALONE: no workspace section, no /api/fs traffic", async ({ page }) => {
  const fsHits: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/fs/") || r.url().includes("/api/workspace")) {
      fsHits.push(r.url());
    }
  });
  await page.goto("http://127.0.0.1:5176/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  await expect(page.locator('[data-testid="ws-files"]')).toHaveCount(0);
  // Standalone rail: no Workspace button at all (S2 Muse MF2)
  await expect(page.getByRole("button", { name: /^Workspace/ })).toHaveCount(0);
  expect(fsHits, `standalone made ${fsHits.join(", ")}`).toEqual([]);
});

test("S3 checkpoint ruling: connected → Run goes to SERVER automatically (no picker)", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  // No picker chrome anywhere
  await expect(page.locator('[data-testid="run-target-picker"]')).toHaveCount(0);
  // Whole-library Run on a connected server MUST produce the server-run note
  await page.getByRole("button", { name: /^Run$/ }).click();
  await expect(page.locator('[data-testid="status-note"]')).toContainText(/server run/, { timeout: 60000 });
});

test("S3 checkpoint ruling: standalone → Run stays in-browser (no server traffic)", async ({ page }) => {
  const evalHits: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/evaluate")) evalHits.push(r.url());
  });
  await page.goto("http://127.0.0.1:5176/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(15000);
  await expect(page.locator('[data-testid="run-target-picker"]')).toHaveCount(0);
  await page.getByRole("button", { name: /^Run$/ }).click().catch(() => {});
  await page.waitForTimeout(3000);
  expect(evalHits, `standalone made ${evalHits.join(", ")}`).toEqual([]);
});
