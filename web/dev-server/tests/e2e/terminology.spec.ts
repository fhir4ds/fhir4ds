import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PORT = 19021;
const BASE = `http://127.0.0.1:${PORT}`;
const WORKTREE = "/mnt/d/fhir4ds-vsac-cleanroom-20261008";

let server: ChildProcess | null = null;
let dir = "";

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "vsc-e2e-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "valuesets"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });

  await writeFile(
    join(dir, "fhir4ds.toml"),
    '[terminology]\nprovider = "vsac"\napi_key_env = "UMLS_API_KEY_TEST"\n',
  );

  const cql = [
    "library Demographics version '1.0.0'",
    "using FHIR version '4.0.1'",
    "",
    "valueset \"BPVS\": 'http://example.com/bp'",
    "valueset \"Remote\": 'http://example.com/remote'",
    "",
    "// # %% [name: IsMale]",
    "define IsMale: Patient.gender = 'male'",
    "",
  ].join("\n");
  await writeFile(join(dir, "cql", "Demographics.cql"), cql);

  const vs = {
    resourceType: "ValueSet",
    id: "vs1",
    url: "http://example.com/bp",
    compose: {
      include: [
        {
          system: "http://loinc.org",
          concept: [{ code: "8480-6", display: "BP" }],
        },
      ],
    },
  };
  await writeFile(join(dir, "valuesets", "vs1.json"), JSON.stringify(vs, null, 2));

  const patients = [
    { resourceType: "Patient", id: "p1", gender: "male", birthDate: "1974-12-25" },
    { resourceType: "Patient", id: "p2", gender: "female", birthDate: "1990-01-01" },
  ]
    .map((r) => JSON.stringify(r))
    .join("\n");
  await writeFile(join(dir, "data", "patients.ndjson"), patients + "\n");

  server = spawn("/usr/bin/python3", ["-m", "fhir4ds.cli", "dev", dir, "--port", String(PORT), "--no-open"], {
    cwd: dir,
    env: {
      PYTHONPATH: WORKTREE,
      PATH: process.env.PATH ?? "",
      UMLS_API_KEY_TEST: "e2e-dummy-key",
    },
    stdio: "ignore",
  });

  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/health`);
      if (res.ok) break;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
});

test.afterAll(async () => {
  if (server?.pid) {
    process.kill(server.pid, "SIGKILL");
    await new Promise((r) => setTimeout(r, 300));
  }
});

test("terminology status pill shows provider", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-termpill")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".dev-termpill")).toContainText("VSAC connected");
  await expect(page.locator(".dev-termdot-connected")).toHaveCount(1);
});

test("import flow: preview then import with stale banner", async ({ page }) => {
  await page.route("**/api/terminology/preview", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        ok: true,
        url: "http://example.com/remote",
        concepts: [
          { system: "http://loinc.org", code: "99213-9" },
          { system: "http://loinc.org", code: "99214-9" },
          { system: "http://snomed.info/sct", code: "1234-5" },
        ],
        count: 3,
      }),
    }),
  );
  await page.route("**/api/terminology/import", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        ok: true,
        path: "valuesets/imported.json",
        url: "http://example.com/remote",
        code_count: 3,
        stale: true,
      }),
    }),
  );
  await page.route("**/api/terminology/resolution", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        ok: true,
        resolutions: [
          { library: "Demographics", id: "BPVS", url: "http://example.com/bp", resolved: "local" },
          { library: "Demographics", id: "Remote", url: "http://example.com/remote", resolved: "VSAC" },
        ],
      }),
    }),
  );

  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "vs1" }).click();
  await expect(page.locator(".dev-vspane")).toBeVisible({ timeout: 20_000 });

  await page.locator(".dev-vsurlinput").fill("http://example.com/remote");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.locator(".dev-vspreview-head")).toContainText("3 codes", { timeout: 10_000 });
  await expect(page.locator(".dev-vsprov")).toContainText("3 concepts from VSAC", { timeout: 10_000 });
  await expect(page.locator(".dev-vsprov")).toContainText("OID remote");

  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.locator(".dev-vsimportmsg")).toContainText("Saved imported.json", {
    timeout: 10_000,
  });
  await expect(page.locator(".dev-vsimportmsg")).toContainText("click Insert");
  await expect(page.locator(".dev-stale").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".dev-vsdecl-attn")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".dev-vsprov")).toContainText("3 concepts from VSAC");
});

test("resolution chips render in used-by footer", async ({ page }) => {
  await page.route("**/api/terminology/resolution", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        ok: true,
        resolutions: [
          { library: "Demographics", id: "BPVS", url: "http://example.com/bp", resolved: "local" },
          { library: "Demographics", id: "Remote", url: "http://example.com/remote", resolved: "VSAC" },
        ],
      }),
    }),
  );

  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "vs1" }).click();
  await expect(page.locator(".dev-vspane")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".dev-reschip-local").first()).toContainText("local", { timeout: 10_000 });
  // Remote has no LOCAL used_by chip in this pane (url mismatch) — its resolution
  // is surfaced via the workspace-wide resolution map instead; pin that the
  // mock response feeds at least the matching local chip and that no
  // unresolvable chip leaks in.
  await expect(page.locator(".dev-reschip-unresolved")).toHaveCount(0);
});
