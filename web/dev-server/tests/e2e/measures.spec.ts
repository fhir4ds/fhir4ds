import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let server = null;
let dir = "";

test.beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "v3msr-"));
  mkdirSync(join(dir, "cql"), { recursive: true });
  mkdirSync(join(dir, "valuesets"), { recursive: true });
  mkdirSync(join(dir, "data"), { recursive: true });
  writeFileSync(
    join(dir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "",
      'valueset "BPVS": \'http://example.com/bp\'',
      "",
      "// # %% [name: InIp]",
      "define InIp: true",
      "",
      "// # %% [name: HasBp]",
      'define HasBp: exists([Observation] O where O.code in "BPVS")',
      "",
    ].join("\n"),
  );
  writeFileSync(
    join(dir, "valuesets", "vs1.json"),
    JSON.stringify(
      {
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
      },
      null,
      2,
    ),
  );
  const resources = [];
  for (let i = 1; i <= 6; i++) {
    resources.push(
      JSON.stringify({
        resourceType: "Patient",
        id: "p" + i,
        gender: i % 2 === 1 ? "male" : "female",
        birthDate: i % 2 === 1 ? "1974-12-25" : "1990-01-01",
      }),
    );
    if (i % 2 === 1) {
      resources.push(
        JSON.stringify({
          resourceType: "Observation",
          id: "obs" + i,
          status: "final",
          code: {
            coding: [{ system: "http://loinc.org", code: "8480-6" }],
          },
          subject: { reference: "Patient/p" + i },
        }),
      );
    }
  }
  writeFileSync(join(dir, "data", "patients.ndjson"), resources.join("\n") + "\n");

  server = spawn("/usr/bin/python3", ["-m", "fhir4ds.cli", "dev", dir, "--port", "18971", "--no-open"], {
    env: {
      PYTHONPATH: "/mnt/d/fhir4ds-devserver-v3-20261005",
      PATH: process.env.PATH ?? "",
    },
    stdio: "ignore",
    cwd: dir,
  });
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch("http://127.0.0.1:18971/health");
      if (r.ok) break;
    } catch {
      /* retry */
    }
    await new Promise((res) => setTimeout(res, 500));
  }
}, 120000);

test.afterAll(async () => {
  if (server) {
    server.kill("SIGKILL");
    await new Promise<void>((resolve) => {
      if (server.exitCode !== null) return resolve();
      server.once("exit", () => resolve());
      setTimeout(resolve, 5000);
    });
  }
  try {
    if (dir) rmSync(dir, { recursive: true, force: true });
  } catch {
    /* ignore */
  }
});

test.beforeEach(async ({ page }) => {
  await page.goto("http://127.0.0.1:18971/");
});

test("measure pane: Run disabled until scoring + initial-population mapped", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected", { hasText: "Demographics" })).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: /^▸ measure$/ }).click();
  const pane = page.locator(".dev-mspane");
  await expect(pane).toBeVisible();
  const run = pane.getByRole("button", { name: "▶ Run measure" });
  await expect(run).toBeDisabled();
  // Set scoring but leave initial-population unmapped — still disabled.
  await pane.locator("select").first().selectOption("proportion");
  await expect(run).toBeDisabled();
});

test("measure pane: scaffold → map → run shows counts", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected", { hasText: "Demographics" })).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: /^▸ measure$/ }).click();
  const pane = page.locator(".dev-mspane");
  await expect(pane).toBeVisible();

  await pane.locator("select").first().selectOption("proportion");
  // Mapping selects inside the grid rows: grid row 1 = initial-population.
  await pane.locator(".dev-msgrid tbody tr").nth(0).locator("select").selectOption("InIp");
  await pane.locator(".dev-msgrid tbody tr").nth(4).locator("select").selectOption("HasBp");

  await pane.getByRole("button", { name: "Scaffold preview" }).click();
  await expect(pane.locator(".dev-mspreview")).toBeVisible();
  await expect(pane.locator(".dev-mspreview-head")).toContainText("2 populations mapped");

  const run = pane.getByRole("button", { name: "▶ Run measure" });
  await expect(run).toBeEnabled();
  await run.click();
  await expect(pane.locator(".dev-mssummary.pass")).toBeVisible({ timeout: 30000 });
  await expect(pane.locator(".dev-mssummary.pass")).toContainText("initial_population: 6");
  await expect(pane.locator(".dev-mssummary.pass")).toContainText("numerator: 3");
  await expect(pane.locator(".dev-mssummary.pass")).toContainText("6 MeasureReports");
});
