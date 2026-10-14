import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// Hotfix QA-002 e2e pin: a workspace whose data/ holds BOTH a.ndjson and
// b.json (bundle) side by side must BOOT the server (previously crashed at
// Kernel construction — DatasetSpec rejected combined ndjson_paths +
// bundle_paths), load patients from the ndjson AND bundle resources, and
// report both via /api/dataset-stats.

const BASE = "http://127.0.0.1:19059";
let dir: string | null = null;
let server: ChildProcess | null = null;

const LIB = [
  "library MixedBoot version '1.0.0'",
  "using FHIR version '4.0.1'",
  "",
  "define \"HasData\": Patient.gender.exists()",
  "",
].join("\n");

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "qa002-mixed-"));
  await Promise.all([
    mkdir(join(dir, "cql")),
    mkdir(join(dir, "data")),
  ]);
  await writeFile(join(dir, "cql", "MixedBoot.cql"), LIB);
  // .ndjson patient (direct)
  await writeFile(
    join(dir, "data", "a.ndjson"),
    JSON.stringify({ resourceType: "Patient", id: "nd-p1", gender: "male" }) + "\n"
  );
  // .json bundle patient (side by side — the crash shape)
  await writeFile(
    join(dir, "data", "b.json"),
    JSON.stringify({
      resourceType: "Bundle",
      type: "collection",
      entry: [
        { resource: { resourceType: "Patient", id: "bu-p1", gender: "female" } },
      ],
    })
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
  throw new Error("dev server did not become healthy (mixed-data boot failed)");
});

function spawnServer(workspaceDir: string): ChildProcess {
  // Conductor-verified fix: spawn cwd MUST be the WORKTREE — python resolves
  // fhir4ds from cwd-on-sys.path (beating PYTHONPATH/site-packages), and
  // spawning from the /tmp workspace picked the INSTALLED wheel (no `dev`).
  const proc = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", workspaceDir, "--port", "19059", "--no-open"],
    {
      cwd: "/mnt/d/fhir4ds-wasm-bolton",
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

test("mixed .ndjson + .json workspace boots and loads both kinds", async ({ request }) => {
  // Boot itself is the pin: before the fix the server never became healthy.
  const health = await request.get(`${BASE}/health`);
  expect(health.ok()).toBeTruthy();
  const body = (await health.json()) as any;
  expect(body?.ok ?? body?.data?.ok ?? true).toBeTruthy();

  // Both patients countable via /api/dataset-stats.
  const stats = await request.get(`${BASE}/api/dataset-stats`);
  expect(stats.ok()).toBeTruthy();
  const payload = (await stats.json()) as any;
  const data = payload?.data ?? payload;
  expect(data?.ok).toBe(true);
  expect(data?.total).toBeGreaterThanOrEqual(2);
  const patientStat = data?.by_type?.find((s: any) => s.resourceType === "Patient");
  expect(patientStat?.count).toBeGreaterThanOrEqual(2);
});
