import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PORT = 19041;
const WORKTREE = "/mnt/d/fhir4ds-vsac-cleanroom-20261008";

let server: ChildProcess | null = null;
let dir: string | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "vd43-"));
  await writeFile(
    join(dir, "Demographics.cql.placeholder"), "",
  );
  const { mkdir, writeFile: wf } = await import("node:fs/promises");
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "valuesets"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await mkdir(join(dir, "views"), { recursive: true });
  await wf(
    join(dir, "cql", "Demographics.cql"),
    `library Demographics version '1.0.0'
using FHIR version '4.0.1'

valueset "BPVS": 'http://example.com/bp'

context Patient

// # %% [name: InIp]
define InIp: true

// # %% [name: HasBp]
define HasBp: exists([Observation] O where O.code in "BPVS")
`,
  );
  await wf(
    join(dir, "valuesets", "vs1.json"),
    JSON.stringify({
      resourceType: "ValueSet",
      id: "vs1",
      url: "http://example.com/bp",
      compose: { include: [{ system: "http://loinc.org", concept: [{ code: "8480-6" }] }] },
    }),
  );
  const lines: string[] = [];
  for (let i = 1; i <= 6; i++) {
    lines.push(JSON.stringify({ resourceType: "Patient", id: `p${i}`, gender: i % 2 ? "male" : "female" }));
    if (i % 2) {
      lines.push(
        JSON.stringify({
          resourceType: "Observation",
          id: `o${i}`,
          status: "final",
          code: { coding: [{ system: "http://loinc.org", code: "8480-6" }] },
          subject: { reference: `Patient/p${i}` },
        }),
      );
    }
  }
  await wf(join(dir, "data", "patients.ndjson"), lines.join("\n") + "\n");
  await wf(
    join(dir, "views", "pxdemo.json"),
    JSON.stringify({
      resource: "Patient",
      name: "PxDemo",
      select: [{ column: [{ name: "id", path: "id" }, { name: "gender", path: "gender" }] }],
    }),
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", String(PORT), "--no-open"],
    { cwd: dir, env: { PYTHONPATH: WORKTREE, PATH: process.env.PATH ?? "" }, stdio: "ignore" },
  );
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      await fetch(`http://127.0.0.1:${PORT}/health`);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid, "SIGKILL");
    } catch {
      /* already gone */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
});

test("constants editor is the writer and paths assist opens", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}`);
  await page.locator(".dev-lib.small", { hasText: "pxdemo" }).first().click();
  const pane = page.locator(".dev-vdpane");
  await expect(pane).toBeVisible();

  // constants table visible w/ add button; add one and verify JSON gets the constant
  await pane.locator(".dev-vdconst-add").click();
  await pane.locator(".dev-vdconst-name").fill("tag");
  await pane.locator(".dev-vdconst-value").fill("demo");
  await expect(pane.locator(".dev-vddirty")).toBeVisible();
  // The table is the writer: the row persists w/ the typed values (the JSON
  // buffer is re-serialized underneath; Monaco virtualization hides tail
  // lines from .view-lines, so the end-to-end constant flow is pinned by
  // the API test instead).
  await expect(pane.locator(".dev-vdconst-name")).toHaveValue("tag");
  await expect(pane.locator(".dev-vdconst-value")).toHaveValue("demo");

  // path assist opens and lists Patient schema paths
  await pane.locator(".dev-vdpathbtn").click();
  await expect(pane.locator(".dev-vdpaths")).toBeVisible();
  await expect(pane.locator(".dev-vdpathitem").first()).toBeVisible();
});

test("run-against toggle: measure output disables Run until a measure ran", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}`);
  await page.locator(".dev-lib.small", { hasText: "pxdemo" }).first().click();
  const pane = page.locator(".dev-vdpane");
  await expect(pane).toBeVisible();

  const runBtn = pane.locator(".dev-vdrun");
  await expect(runBtn).toBeEnabled(); // dataset mode fine
  await pane.locator(".dev-vdagainst").selectOption("measure");
  await expect(runBtn).toBeDisabled(); // no measure output yet
  await pane.locator(".dev-vdagainst").selectOption("dataset");
  await expect(runBtn).toBeEnabled();
});
