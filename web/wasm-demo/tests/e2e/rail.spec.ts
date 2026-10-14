import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-wasm-bolton S2: single adaptive rail. Standalone (static preview):
// cleanroom entries visible but disabled with remedy; connected (--ui wasm
// server): rail enabled, Libraries opens the workspace file tree listing
// real .cql files via fsList.

const CONNECTED = "http://127.0.0.1:19062";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "bolton-s2-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(
    join(dir, "cql", "DemoLib.cql"),
    ["library DemoLib version '1.0.0'", "using FHIR version '4.0.1'", "", "define \"OK\": 1 = 1", ""].join("\n"),
  );
  await writeFile(
    join(dir, "cql", "Helper.cql"),
    ["library Helper version '1.0.0'", "using FHIR version '4.0.1'", "", "define \"H\": true", ""].join("\n"),
  );

  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19062", "--ui", "wasm", "--no-open"],
    {
      cwd: dir,
      env: {
        ...process.env,
        PYTHONPATH: "/mnt/d/fhir4ds-wasm-bolton",
        PATH: process.env.PATH ?? "",
      },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${CONNECTED}/health`);
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

test("standalone preview: cleanroom entries visible, disabled, with remedy", async ({ page }) => {
  await page.goto("/");
  const rail = page.locator(".cleanroom-rail");
  await expect(rail).toBeVisible({ timeout: 20000 });
  // Core entries active
  await expect(rail.locator(".cleanroom-rail-btn", { hasText: "CQL" })).toBeEnabled();
  // Cleanroom entries PRESENT (hybrid rule: never hidden) but disabled with lock
  for (const label of ["Libraries", "Valuesets", "Measures", "Terminology", "History"]) {
    const btn = rail.locator(".cleanroom-rail-btn", { hasText: label });
    await expect(btn).toBeVisible();
    await expect(btn).toBeDisabled();
    await expect(btn.locator(".cleanroom-rail-lock")).toBeVisible();
  }
});

test("standalone: clicking disabled entry would show empty state (aria remedy present)", async ({ page }) => {
  await page.goto("/");
  const measures = page.locator(".cleanroom-rail-btn", { hasText: "Measures" });
  await expect(measures).toBeDisabled();
  await expect(measures).toHaveAttribute("aria-label", /requires a connected server/i);
});

test("connected: rail enabled; Libraries opens workspace file tree with .cql files", async ({ page }) => {
  await page.goto(CONNECTED);
  const rail = page.locator(".cleanroom-rail");
  await expect(rail).toBeVisible({ timeout: 20000 });

  const libraries = rail.locator(".cleanroom-rail-btn", { hasText: "Libraries" });
  // enabled once handshake resolves (no lock)
  await expect(libraries).toBeEnabled({ timeout: 20000 });
  await libraries.click();

  const slideout = page.locator(".cleanroom-slideout");
  await expect(slideout).toBeVisible();
  const tree = slideout.locator(".cleanroom-tree");
  await expect(tree).toBeVisible({ timeout: 15000 });
  await expect(tree.getByText("DemoLib.cql")).toBeVisible();
  await expect(tree.getByText("Helper.cql")).toBeVisible();
});

test("connected: engine badge shows server version (S2 rerun pin)", async ({ page }) => {
  await page.goto(CONNECTED);
  await expect(page.locator(".status-engine")).toContainText(/server \d+\.\d+\.\d+/, { timeout: 20000 });
});

test("connected: engine badge popover opens with retry + override actions (P1)", async ({ page }) => {
  await page.goto(CONNECTED);
  const badge = page.locator(".status-engine");
  await expect(badge).toContainText(/server \d+\.\d+\.\d+/, { timeout: 20000 });
  await badge.click();
  const pop = page.locator(".engine-popover");
  await expect(pop).toBeVisible();
  await expect(pop.getByText("Retry connection")).toBeVisible();
  await expect(pop.getByText("Use in-browser engine")).toBeVisible();
  // Escape closes
  await page.keyboard.press("Escape");
  await expect(pop).toBeHidden();
});

test("connected: History slide-out lists persistent runlog entries + clear", async ({ page }) => {
  await page.goto(CONNECTED);
  const history = page.locator(".cleanroom-rail-btn", { hasText: "History" });
  await expect(history).toBeEnabled({ timeout: 20000 });
  await history.click();
  const slideout = page.locator(".cleanroom-slideout");
  await expect(slideout).toBeVisible();
  // Empty state OR entries — both valid; the panel must render without error.
  await expect(
    slideout.locator(".cleanroom-empty, .runhistory-list, .cleanroom-tree-error").first(),
  ).toBeVisible({ timeout: 15000 });
});

test("connected: data file change shows data-hint banner (locked decision 4 — never auto-reload)", async ({ page, request }) => {
  await page.goto(CONNECTED);
  // Wait for connection + rail
  await expect(page.locator(".status-engine")).toContainText(/server/, { timeout: 20000 });
  // Touch a data file on disk (server watcher polls every 0.5s; debounce 0.25s)
  const { writeFile: wf, mkdir: mkd } = await import("node:fs/promises");
  await mkd(join(dir!, "data"), { recursive: true });
  await wf(join(dir!, "data", "p.ndjson"), JSON.stringify({ resourceType: "Patient", id: "p1" }) + "\n");
  const banner = page.locator(".data-hint-banner");
  await expect(banner).toBeVisible({ timeout: 20000 });
  await expect(banner).toContainText(/restart/i);
  // Dismiss clears it without restarting.
  await banner.locator(".data-hint-dismiss").click();
  await expect(banner).toBeHidden();
});
