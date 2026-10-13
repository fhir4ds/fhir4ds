import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-wasm-bolton S4: terminology pane — status (provider + key presence +
// UMLS env-var display per FDD Q3), VSAC preview/import wired to the real
// endpoints, UMLS search disabled without a key.

const BASE = "http://127.0.0.1:19065";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "bolton-s4-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(join(dir, "cql", "T.cql"), "library T version '1.0.0'\n");

  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19065", "--ui", "wasm", "--no-open"],
    {
      cwd: dir,
      env: {
        ...process.env,
        PYTHONPATH: "/mnt/d/fhir4ds-wasm-bolton",
        PATH: process.env.PATH ?? "",
        UMLS_API_KEY: "",
        FHIR4DS_UMLS_API_KEY: "",
      },
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
  throw new Error("dev server (--ui wasm) did not become healthy");
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

test("terminology slide-out shows status incl. UMLS env-var display", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".loading-overlay")).toHaveCount(0, { timeout: 60000 });
  const term = page.locator(".cleanroom-rail-btn", { hasText: "Terminology" });
  await expect(term).toBeEnabled({ timeout: 20000 });
  await term.click();
  const pane = page.locator(".term-pane");
  await expect(pane).toBeVisible();
  // Status dl renders provider + UMLS env-var display (never a key value)
  const status = pane.locator(".term-status");
  await expect(status).toContainText(/provider/i, { timeout: 15000 });
  await expect(status.getByText("UMLS", { exact: true })).toBeVisible();
  // No key configured in this env → guidance + recheck visible
  await expect(pane.locator(".term-hint")).toContainText(/UMLS_API_KEY/i);
  await expect(pane.locator(".term-recheck")).toBeVisible();
});

test("import section renders preview/import actions; bad URL yields typed error", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".loading-overlay")).toHaveCount(0, { timeout: 60000 });
  await page.locator(".cleanroom-rail-btn", { hasText: "Terminology" }).click();
  const pane = page.locator(".term-pane");
  await expect(pane).toBeVisible({ timeout: 15000 });
  const input = pane.locator(".term-input").first();
  await input.fill("http://127.0.0.1:1/fhir/ValueSet/does-not-exist");
  await pane.getByRole("button", { name: "Preview" }).click();
  // Server responds ok:false with a typed diagnostic — rendered as error msg
  await expect(pane.locator(".term-message.error")).toBeVisible({ timeout: 30000 });
});

test("UMLS search disabled without key; inputs present", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".loading-overlay")).toHaveCount(0, { timeout: 60000 });
  await page.locator(".cleanroom-rail-btn", { hasText: "Terminology" }).click();
  const pane = page.locator(".term-pane");
  await expect(pane).toBeVisible({ timeout: 15000 });
  const searchBtn = pane.getByRole("button", { name: "Search", exact: true });
  await expect(searchBtn).toBeDisabled();
  await expect(pane.locator(".term-input").nth(1)).toBeVisible();
});
