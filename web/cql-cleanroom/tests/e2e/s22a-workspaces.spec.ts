import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S22a (AM1): workspace switcher — the demo is a REAL directory
// workspace (examples/demo-workspace/), the header picker lists
// server-known workspaces, and connected boot shows ONLY the selected
// workspace's files (no ghost CleanroomDemo browser state).

const BASE = "http://127.0.0.1:19175";
const DEMO_BASE = "http://127.0.0.1:19176";
let dir: string | null = null;
let server: ChildProcess | null = null;
let demoServer: ChildProcess | null = null;

async function waitHealthy(base: string) {
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`${base}/health`);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`dev server at ${base} did not become healthy`);
}

test.beforeAll(async () => {
  // Workspace A: a scratch workspace with one library on disk.
  dir = await mkdtemp(join(tmpdir(), "ccr-s22a-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(
    join(dir, "cql", "ProjLib.cql"),
    "library ProjLib version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\ndefine Ok: 1 = 1\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19175", "--no-open"],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
  await waitHealthy(BASE);

  // Workspace B: the REAL demo workspace directory from the repo.
  demoServer = spawn(
    "/usr/bin/python3",
    [
      "-m",
      "fhir4ds.cli",
      "dev",
      "/mnt/d/fhir4ds/examples/demo-workspace",
      "--port",
      "19176",
      "--no-open",
    ],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
  await waitHealthy(DEMO_BASE);
});

test.afterAll(async () => {
  for (const s of [server, demoServer]) {
    if (s?.pid) {
      try {
        process.kill(s.pid);
        await new Promise((r) => setTimeout(r, 300));
      } catch {
        /* already gone */
      }
    }
  }
  if (dir) await rm(dir, { recursive: true, force: true });
});

test("S22a-1: demo workspace is a real directory — serves its own libraries", async ({ request }) => {
  const r = await request.get(`${DEMO_BASE}/api/workspace`);
  const body = (await r.json()) as {
    workspace?: { libraries?: { name: string }[] };
    data?: { libraries?: { name: string }[] };
  };
  const libs = (body.workspace ?? body.data)?.libraries ?? [];
  expect(libs.length).toBeGreaterThan(0);
  // The demo library is a DISK file in the demo workspace (not the
  // in-browser CleanroomDemo default).
  expect(libs.map((l) => l.name)).toContain("CleanroomDemo");
});

test("S22a-2: /api/mode names the workspace and the picker lists it", async ({ page, request }) => {
  await page.goto(BASE);
  await expect(page.locator(".version-badge")).toBeVisible({ timeout: 60_000 });

  // The mode handshake names the ACTIVE workspace directory.
  const mode = (await (
    await request.get(`${BASE}/api/mode`)
  ).json()) as {
    data?: { workspace?: string };
    workspace?: string;
  };
  const wsName = (mode.data ?? mode)?.workspace ?? "";
  expect(wsName).toBeTruthy();

  // The header picker exists, opens, and lists the active workspace.
  await page.locator('[data-testid="workspace-picker"]').click();
  const menu = page.locator('[data-testid="workspace-menu"]');
  await expect(menu).toBeVisible();
  await expect(menu.locator('[data-testid="workspace-option"]').filter({ hasText: wsName })).toHaveCount(1);
});

test("S22a-3: connected boot shows ONLY the selected workspace's files — no ghost demo", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  // Engine boot + restore + connected-boot purity (first disk library
  // replaces the CleanroomDemo scratch default) settle within 15s.
  await page.waitForTimeout(15000);

  // The editor opens on the workspace's OWN library, never the in-browser
  // CleanroomDemo default state (which would carry the demo dataset).
  await expect(page.getByRole("tab", { name: /ProjLib/i })).toBeVisible({ timeout: 30_000 });

  // The Libraries drawer lists the disk library (via nav).
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("ProjLib");

  // The demo dataset patients (p1 Ann / p2 Bob / p3 of the old in-browser
  // demo store) must NOT appear in the tests/dataset roster.
  await page.locator('[data-testid="nav-toggle-tests"]').click();
  await expect(panel).not.toContainText("Ann");
  await expect(panel).not.toContainText("Bob");
});
