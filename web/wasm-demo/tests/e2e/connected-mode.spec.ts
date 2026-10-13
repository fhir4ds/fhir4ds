import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-wasm-bolton S1: connected-mode handshake e2e. `fhir4ds dev --ui wasm`
// serves the wasm product build; the app handshakes /api/mode and mounts
// ServerTransport — surfaced as the engine badge (server vX.Y) + workspace
// name in the status bar. Standalone behavior (static hosting → wasm badge)
// is covered by the existing playground/web-component suites.

const BASE = "http://127.0.0.1:19061";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "bolton-s1-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await writeFile(
    join(dir, "cql", "Demo.cql"),
    ["library Demo version '1.0.0'", "using FHIR version '4.0.1'", "", "define \"OK\": 1 = 1", ""].join("\n"),
  );

  server = spawnServer(dir);
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

function spawnServer(cwd: string): ChildProcess {
  const proc = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", cwd, "--port", "19061", "--ui", "wasm", "--no-open"],
    {
      cwd,
      env: {
        ...process.env,
        PYTHONPATH: "/mnt/d/fhir4ds-wasm-bolton",
        PATH: process.env.PATH ?? "",
      },
      stdio: "ignore",
    },
  );
  return proc;
}

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

test("/api/mode handshake carries server identity + nonce + documented range", async ({ request }) => {
  const res = await request.get(`${BASE}/api/mode`);
  expect(res.ok()).toBeTruthy();
  const payload = (await res.json()) as any;
  const d = payload?.data ?? payload;
  expect(d.server).toBe(true);
  expect(d.version).toMatch(/^\d+\.\d+\.\d+/);
  expect(d.server_range).toMatch(/^>=/); // documented semver range, not magic
  expect(typeof d.nonce).toBe("string");
  expect(d.nonce.length).toBeGreaterThanOrEqual(8);
  expect(d.ui).toBe("wasm");
});

test("connected mode shows engine badge + workspace name (handshake resolved)", async ({ page }) => {
  await page.goto(BASE);
  // Engine badge: "server vX.Y.Z" once the handshake resolves.
  const badge = page.locator(".status-engine");
  await expect(badge).toContainText(/server \d+\.\d+\.\d+/, { timeout: 20000 });
  // Workspace name (config root dir name) renders beside it.
  const ws = page.locator(".status-workspace");
  await expect(ws).toBeVisible();
  // No version-pin banner: served server is inside its own documented range.
  await expect(page.locator(".version-pin-banner")).toHaveCount(0);
});
