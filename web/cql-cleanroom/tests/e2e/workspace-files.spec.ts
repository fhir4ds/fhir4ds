import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-cleanroom-redo S2→S6: server workspace files flow into the TYPE
// drawers (S6 dissolved the Workspace rail section). Disk items carry
// 'on disk' chips; CQL click opens the library in the native editor;
// valueset click opens the native valueset editor; standalone makes NO
// /api/fs or /api/workspace requests and the Workspace section is gone.

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

test("connected: disk files appear in the TYPE drawers with on-disk chips", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  // The Workspace section is GONE (S6).
  await expect(page.locator('[data-testid="nav-toggle-workspace"]')).toHaveCount(0);
  // Disk CQL flows into the Libraries drawer.
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const diskRow = libPanel.locator(".nav-item", { hasText: "WsLib" }).first();
  await expect(diskRow).toBeVisible({ timeout: 15000 });
  await expect(diskRow.locator(".nav-item-pill.on-disk")).toBeVisible();
  // Disk valueset flows into the Valuesets drawer.
  await page.locator('[data-testid="nav-toggle-valuesets"]').click();
  const vsPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const vsRow = vsPanel.locator(".nav-item", { hasText: "wsvs" }).first();
  await expect(vsRow).toBeVisible({ timeout: 15000 });
});

test("connected: disk CQL click (Libraries drawer) opens the native editor", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const diskRow = libPanel.locator(".nav-item", { hasText: "WsLib" }).first();
  await diskRow.click({ timeout: 15000 });
  // The library opens as a native editor tab (tab bar gains WsLib).
  await expect(page.getByRole("tab", { name: /WsLib/i })).toBeVisible({ timeout: 15000 });
});

test("connected: disk valueset click (Valuesets drawer) opens the native valueset editor", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(12000);
  await page.locator('[data-testid="nav-toggle-valuesets"]').click();
  const vsPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  const vsRow = vsPanel.locator(".nav-item", { hasText: "wsvs" }).first();
  await vsRow.click({ timeout: 15000 });
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
  // S6: the Workspace section is gone EVERYWHERE; drawers render in-app
  // state only (no disk items in standalone).
  await expect(page.locator('[data-testid="nav-toggle-workspace"]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Workspace/ })).toHaveCount(0);
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  await expect(page.locator(".nav-item-pill.on-disk")).toHaveCount(0);
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

test("S4: / serves the cleanroom product with isolation + NavRail, zero failures", async ({ page }) => {
  const fails: string[] = [];
  page.on("requestfailed", (r) => fails.push(r.url().slice(-70)));
  page.on("pageerror", (e) => fails.push(String(e).slice(0, 80)));
  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(25000);
  const st = await page.evaluate(() => ({
    isolated: crossOriginIsolated,
    title: document.title,
    nav: !!document.querySelector("nav"),
  }));
  expect(st.isolated).toBe(true);
  expect(st.title).toBe("CQL Cleanroom");
  expect(st.nav).toBe(true);
  expect(fails, fails.join("; ")).toEqual([]);
});

test("S4: /legacy/ still serves the pre-bolton shell", async ({ page }) => {
  await page.goto(`${BASE}/legacy/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(3000);
  // The legacy shell's title differs from the cleanroom product.
  const title = await page.title();
  expect(title).not.toBe("CQL Cleanroom");
});
